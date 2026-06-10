"""從 workspace 同層 `kenny_assets` 讀取 Kenney 等素材包。"""
from __future__ import annotations

from pathlib import Path

PACK_STRIDE = 65536
KENNEY_TILE_BASE = 256


def list_pack_dirs(kenney_root: Path) -> list[Path]:
    if not kenney_root.is_dir():
        return []
    return sorted(p for p in kenney_root.iterdir() if p.is_dir())


def collect_pngs_in_pack(pack_dir: Path) -> list[Path]:
    """優先 Tiles，其次 PNG/Grey/Default，否則遞迴 *.png（依路徑排序）。"""
    if not pack_dir.is_dir():
        return []
    tiles_dir = pack_dir / "Tiles"
    if tiles_dir.is_dir():
        found = sorted(tiles_dir.glob("*.png"))
        if found:
            return found
    png_default = pack_dir / "PNG" / "Grey" / "Default"
    if png_default.is_dir():
        found = sorted(png_default.glob("*.png"))
        if found:
            return found
    return sorted(pack_dir.rglob("*.png"))


def gid_for(page_index: int, index_in_pack: int) -> int:
    return KENNEY_TILE_BASE + page_index * PACK_STRIDE + index_in_pack
