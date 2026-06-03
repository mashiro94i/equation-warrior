#!/usr/bin/env python3
"""Copy generate2dsprite labeled frames to 00.png, 01.png, ... in delivery folders."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parent.parent
PIPELINE = GAME_ROOT / "assets" / "img" / "player" / "scientist" / "_pipeline"
DELIVER = GAME_ROOT / "assets" / "img" / "player" / "scientist"

ACTIONS = {
    "Idle": (r"idle-(\d+)", 4),
    "Run": (r"run-(\d+)", 4),
    "Cast": (r"cast-(\d+)", 6),
    "Jump": (r"jump-(\d+)", 4),
    "Hurt": (r"hurt-(\d+)", 4),
    "Death": (r"death-(\d+)", 6),
    "projectile": (r"projectile-(\d+)", 4),
}


def main() -> None:
    for folder, (pattern, count) in ACTIONS.items():
        src_dir = PIPELINE / folder
        dst_dir = DELIVER / folder
        if not src_dir.is_dir():
            print(f"skip missing: {src_dir}")
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)
        rx = re.compile(pattern + r"\.png$", re.I)
        matched = []
        for p in src_dir.glob("*.png"):
            m = rx.match(p.name)
            if m:
                matched.append((int(m.group(1)), p))
        matched.sort(key=lambda x: x[0])
        if len(matched) < count:
            print(f"warn {folder}: expected {count}, got {len(matched)}")
        for i, (_, src) in enumerate(matched[:count]):
            dst = dst_dir / f"{i:02d}.png"
            shutil.copy2(src, dst)
            print(f"{src.name} -> {dst.relative_to(GAME_ROOT)}")


if __name__ == "__main__":
    main()
