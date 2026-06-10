"""Kenney 圖集合成與單格擷取。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygame

from .asset_packs import collect_pngs_in_pack


def _pack_slug(pack_dir: Path) -> str:
    return pack_dir.name.lower()


def _sorted_pngs_in_dir(d: Path) -> list[Path]:
    if not d.is_dir():
        return []
    return sorted(d.rglob("*.png"))


def _tiles_or_pack_pngs(pack_dir: Path) -> list[Path]:
    t = pack_dir / "Tiles"
    if t.is_dir():
        found = sorted(t.rglob("*.png"))
        if found:
            return found
    return sorted(pack_dir.rglob("*.png"))


def _chunk_to_rows(paths: list[Path], cols: int) -> list[list[Path]]:
    if cols < 1:
        cols = 1
    if not paths:
        return []
    rows: list[list[Path]] = []
    for i in range(0, len(paths), cols):
        rows.append(paths[i : i + cols])
    return rows


def _collect_double_pngs_in_color_dir(color_dir: Path) -> list[Path]:
    for sub in (
        "Double",
        "double",
        "Double2",
        "Double 2",
        "double2",
        "Double_2",
        "double_2",
    ):
        d = color_dir / sub
        if d.is_dir():
            return sorted(d.glob("*.png"))
    out: list[Path] = []
    for p in sorted(color_dir.glob("*.png")):
        stem_l = p.stem.lower()
        if "double" in stem_l and "2" in stem_l:
            out.append(p)
    return out


def collect_ui_space_double_rows_by_color(pack_dir: Path) -> list[list[Path]]:
    png_root = pack_dir / "PNG"
    if not png_root.is_dir():
        return []
    rows: list[list[Path]] = []
    for color_dir in sorted(png_root.iterdir()):
        if not color_dir.is_dir():
            continue
        row = _collect_double_pngs_in_color_dir(color_dir)
        if row:
            rows.append(row)
    return rows


def _pixel_platformer_tile_rows(pack_dir: Path) -> list[list[Path]]:
    tiles_root = pack_dir / "Tiles"
    if not tiles_root.is_dir():
        return []
    bg_dir = tiles_root / "Backgrounds"
    ch_dir = tiles_root / "Characters"
    bg = _sorted_pngs_in_dir(bg_dir)
    ch = _sorted_pngs_in_dir(ch_dir)
    bg_set = {p.resolve() for p in bg}
    ch_set = {p.resolve() for p in ch}
    rest: list[Path] = []
    for p in sorted(tiles_root.rglob("*.png")):
        try:
            rel = p.relative_to(tiles_root)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in ("Backgrounds", "Characters"):
            continue
        rp = p.resolve()
        if rp in bg_set or rp in ch_set:
            continue
        rest.append(p)
    rows: list[list[Path]] = []
    if bg:
        rows.append(bg)
    if ch:
        rows.append(ch)
    rows.extend(_chunk_to_rows(rest, 20))
    return rows


def _build_from_rows(rows: list[list[Path]], slot: int) -> PageState:
    if not rows:
        surf = pygame.Surface((slot, slot))
        surf.fill((48, 52, 62))
        return PageState("composite", surf, slot, 1, 1, [None])
    ncols = max(len(r) for r in rows)
    nrows = len(rows)
    padded: list[list[Path | None]] = [list(r) + [None] * (ncols - len(r)) for r in rows]
    cell_paths: list[Path | None] = [p for row in padded for p in row]
    w, h = ncols * slot, nrows * slot
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((40, 44, 54, 255))
    for ri, row in enumerate(padded):
        for ci, pth in enumerate(row):
            if pth is None or not pth.is_file():
                continue
            try:
                im = pygame.image.load(str(pth)).convert_alpha()
                im = pygame.transform.smoothscale(im, (max(1, slot - 4), max(1, slot - 4)))
                surf.blit(im, (ci * slot + 2, ri * slot + 2))
            except pygame.error:
                pass
    return PageState("composite", surf, slot, ncols, nrows, cell_paths)


def load_page_state(pack_dir: Path) -> PageState:
    slug = _pack_slug(pack_dir)
    if "input-prompts-pixel" in slug:
        paths = _tiles_or_pack_pngs(pack_dir)
        rows = _chunk_to_rows(paths, 34)
        return _build_from_rows(rows, slot=44)
    if "pixel-platformer" in slug:
        rows = _pixel_platformer_tile_rows(pack_dir)
        return _build_from_rows(rows, slot=56)
    if "tiny-dungeon" in slug:
        paths = _tiles_or_pack_pngs(pack_dir)
        rows = _chunk_to_rows(paths, 12)
        return _build_from_rows(rows, slot=56)
    if "ui-pack-space-expansion" in slug:
        color_rows = collect_ui_space_double_rows_by_color(pack_dir)
        return _build_from_rows(color_rows, slot=72)
    paths = collect_pngs_in_pack(pack_dir)
    rows = _chunk_to_rows(paths, 8)
    return _build_from_rows(rows, slot=64)


@dataclass
class PageState:
    kind: str
    surf: pygame.Surface
    cell_px: int
    ncols: int
    nrows: int
    cell_paths: list[Path | None]

    def cell_count(self) -> int:
        return self.ncols * self.nrows

    def set_cell_px_preview_only(self, cell_px: int) -> None:
        pass


def extract_tile_surface(state: PageState, col: int, row: int, out_px: int) -> pygame.Surface:
    if col < 0 or row < 0 or col >= state.ncols or row >= state.nrows:
        s = pygame.Surface((out_px, out_px))
        s.fill((55, 60, 70))
        return s
    idx = row * state.ncols + col
    cpx = state.cell_px
    rect = pygame.Rect(col * cpx, row * cpx, cpx, cpx)
    rect = rect.clip(state.surf.get_rect())
    pth = state.cell_paths[idx] if idx < len(state.cell_paths) else None
    if pth is not None and pth.is_file():
        try:
            img = pygame.image.load(str(pth)).convert_alpha()
            return pygame.transform.smoothscale(img, (out_px, out_px))
        except pygame.error:
            pass
    if rect.width < 1 or rect.height < 1:
        s = pygame.Surface((out_px, out_px))
        s.fill((55, 60, 70))
        return s
    sub = state.surf.subsurface(rect).copy()
    return pygame.transform.smoothscale(sub, (out_px, out_px))
