"""從 workspace 同層的 `kenny_assets`（或備援 `新增資料夾`）讀取 Kenney 等素材包。"""
from __future__ import annotations

from pathlib import Path

PACK_STRIDE = 65536
# 與 map_editor.tile_loader 語意 id（0–20）錯開；自訂素材格從此值起編號。
KENNEY_TILE_BASE = 256


def workspace_root(map_editor_file: Path) -> Path:
    """map_editor 的上一層（例如 遊戲程式設計）。"""
    return map_editor_file.resolve().parent.parent


def new_assets_root(map_editor_file: Path) -> Path:
    """與 map_editor 同層的 Kenney 素材根：優先 `kenny_assets`，否則 `新增資料夾`。"""
    ws = workspace_root(map_editor_file)
    ka = ws / "kenny_assets"
    if ka.is_dir():
        return ka
    return ws / "新增資料夾"


def list_pack_dirs(map_editor_file: Path) -> list[Path]:
    root = new_assets_root(map_editor_file)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir())


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
