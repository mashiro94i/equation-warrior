#!/usr/bin/env python3
"""Re-split 1x4 horizontal raw strips with full-body crop + uniform height + feet align."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

GAME_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GAME_ROOT / "tools"))
from generate2dsprite import (  # noqa: E402
    compose_sheet,
    remove_bg_magenta,
    save_transparent_gif,
    trim_border,
)

PIPELINE = GAME_ROOT / "assets" / "img" / "player" / "scientist" / "_pipeline"
DELIVER = GAME_ROOT / "assets" / "img" / "player" / "scientist"
CELL = 128
FIT = 0.85
THRESH = 100
EDGE = 150


def extract_cells(raw: Path, cols: int = 4) -> list[Image.Image]:
    img = remove_bg_magenta(Image.open(raw).convert("RGBA"), THRESH, EDGE)
    w, h = img.size
    cw = w // cols
    cells: list[Image.Image] = []
    for c in range(cols):
        cell = img.crop((c * cw, 0, (c + 1) * cw, h))
        cell = trim_border(cell, px=2)
        bbox = cell.getbbox()
        if bbox:
            cell = cell.crop(bbox)
        cells.append(cell)
    return cells


def pack_frames(
    crops: list[Image.Image],
    prefix: str,
    *,
    ref_index: int | None = None,
    max_width_ratio: float = 1.12,
) -> list[Image.Image]:
    if not crops:
        return []
    max_h = max(im.size[1] for im in crops)
    ref = crops[ref_index] if ref_index is not None and 0 <= ref_index < len(crops) else None
    ref_h = ref.size[1] if ref is not None else max_h
    ref_w = ref.size[0] if ref is not None else max(im.size[0] for im in crops)
    normed: list[Image.Image] = []
    for im in crops:
        if im.size[1] == 0:
            continue
        scale = ref_h / im.size[1]
        nw = max(1, int(im.size[0] * scale))
        nh = ref_h
        if nw > max(1, int(ref_w * max_width_ratio)):
            scale = (ref_w * max_width_ratio) / im.size[0]
            nw = max(1, int(im.size[0] * scale))
            nh = max(1, int(im.size[1] * scale))
        normed.append(im.resize((nw, nh), Image.Resampling.LANCZOS))
    max_h = max(im.size[1] for im in normed)
    max_w = max(im.size[0] for im in normed)
    scale = min(CELL / max_w, CELL / max_h) * FIT
    pad = max(0, int(CELL * (1 - FIT) * 0.5))
    out: list[Image.Image] = []
    for im in normed:
        nw = max(1, int(im.size[0] * scale))
        nh = max(1, int(im.size[1] * scale))
        scaled = im.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
        px = (CELL - nw) // 2
        py = CELL - nh - pad
        canvas.paste(scaled, (px, py))
        out.append(canvas)
    return out


def write_action(
    folder: str,
    prefix: str,
    frames: list[Image.Image],
    *,
    deliver_indices: list[int] | None = None,
) -> None:
    pdir = PIPELINE / folder
    pdir.mkdir(parents=True, exist_ok=True)
    labels = [f"{prefix}-{i + 1}" for i in range(len(frames))]
    for label, frame in zip(labels, frames):
        frame.save(pdir / f"{label}.png")
    compose_sheet(frames, 1, len(frames), CELL).save(pdir / "sheet-transparent.png")
    save_transparent_gif(frames, pdir / "animation.gif", 200)
    meta = {"rows": 1, "cols": len(frames), "labels": labels, "layout": "1x4_strip"}
    (pdir / "pipeline-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    ddir = DELIVER / folder
    ddir.mkdir(parents=True, exist_ok=True)
    idxs = deliver_indices if deliver_indices is not None else list(range(len(frames)))
    for out_i, src_i in enumerate(idxs):
        if 0 <= src_i < len(frames):
            frames[src_i].save(ddir / f"{out_i:02d}.png")


def regif_without(folder: str, prefix: str, skip: int) -> None:
    """Rebuild GIF/sheet from existing PNGs, skipping one bad index (1-based)."""
    pdir = PIPELINE / folder
    frames: list[Image.Image] = []
    for i in range(1, 20):
        if i == skip:
            continue
        p = pdir / f"{prefix}-{i}.png"
        if not p.is_file():
            break
        frames.append(Image.open(p).convert("RGBA"))
    if not frames:
        return
    compose_sheet(frames, 1, len(frames), CELL).save(pdir / "sheet-transparent.png")
    save_transparent_gif(frames, pdir / "animation.gif", 200)
    ddir = DELIVER / folder
    ddir.mkdir(parents=True, exist_ok=True)
    for i, frame in enumerate(frames):
        frame.save(ddir / f"{i:02d}.png")


def reprocess_run_strip(raw_src: Path | None = None) -> None:
    """Run：1x4 橫列 raw（#FF00FF），與 Idle 切格方式相同。"""
    raw = raw_src or (PIPELINE / "Run" / "raw-sheet.png")
    if not raw.is_file():
        print("skip Run: no raw-sheet")
        return
    crops = extract_cells(raw, 4)
    frames = pack_frames(crops, "run", ref_index=0)
    write_action("Run", "run", frames)
    print(f"ok Run: 1x4 strip -> {len(frames)} frames")


def sync_run_from_idle() -> None:
    """備援：Run raw 壞掉時從 Idle 複製跑步格。"""
    idle_p = PIPELINE / "Idle"
    run_p = PIPELINE / "Run"
    run_p.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    for i in range(1, 5):
        src = idle_p / f"idle-{i}.png"
        if not src.is_file():
            break
        im = Image.open(src).convert("RGBA")
        im.save(run_p / f"run-{i}.png")
        frames.append(im)
    if not frames:
        print("skip Run: no idle frames")
        return
    compose_sheet(frames, 1, len(frames), CELL).save(run_p / "sheet-transparent.png")
    save_transparent_gif(frames, run_p / "animation.gif", 200)
    ddir = DELIVER / "Run"
    ddir.mkdir(parents=True, exist_ok=True)
    for i, im in enumerate(frames):
        im.save(ddir / f"{i:02d}.png")
    print(f"ok Run: copied {len(frames)} frames from Idle walk cycle")


def main() -> None:
    for folder, prefix, ref_i in (("Idle", "idle", None), ("Jump", "jump", 1)):
        raw = PIPELINE / folder / "raw-sheet.png"
        if not raw.is_file():
            print(f"skip missing {raw}")
            continue
        crops = extract_cells(raw, 4)
        frames = pack_frames(crops, prefix, ref_index=ref_i)
        deliver = [0, 1] if folder == "Jump" and len(frames) >= 2 else None
        write_action(folder, prefix, frames, deliver_indices=deliver)
        print(f"ok {folder}: 1x4 -> {len(frames)} frames")

    if (PIPELINE / "Run" / "raw-sheet.png").is_file():
        reprocess_run_strip()
    else:
        sync_run_from_idle()

    for folder, prefix, skip in (("Hurt", "hurt", 2), ("projectile", "projectile", 1)):
        bad = PIPELINE / folder / f"{prefix}-{skip}.png"
        if bad.is_file():
            bad.unlink()
            print(f"deleted {bad}")
        regif_without(folder, prefix, skip=skip)
        print(f"ok {folder}: regif without {prefix}-{skip}")


if __name__ == "__main__":
    main()
