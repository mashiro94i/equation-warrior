"""專案路徑：地圖目錄、Kenney 素材等。"""
from __future__ import annotations

from pathlib import Path

# 方程式戰士/ → 遊戲程式設計/
_WORKSPACE = Path(__file__).resolve().parent.parent.parent
_GAME_ROOT = Path(__file__).resolve().parent.parent

MAP_EDITOR_MAP_DIR = _WORKSPACE / "map_editor" / "map"
GAME_MAP_DIR = _GAME_ROOT / "map"
KENNEY_ASSETS_ROOT = _WORKSPACE / "kenny_assets"
PLAYER_KENNEY_TILE = KENNEY_ASSETS_ROOT / "kenney_tiny-dungeon" / "Tiles" / "tile_0084.png"


def map_search_dirs() -> list[Path]:
    """地圖搜尋順序：map_editor/map → 方程式戰士/map。"""
    out: list[Path] = []
    if MAP_EDITOR_MAP_DIR.is_dir():
        out.append(MAP_EDITOR_MAP_DIR)
    if GAME_MAP_DIR.is_dir():
        out.append(GAME_MAP_DIR)
    return out


def find_map_dir_for_level(level: int) -> Path:
    """回傳含 level{N}.csv 或 level{N}_data.csv 的目錄；皆無則優先 map_editor/map。"""
    names = (f"level{level}.csv", f"level{level}_data.csv")
    for d in map_search_dirs():
        for name in names:
            if (d / name).is_file():
                return d
    if MAP_EDITOR_MAP_DIR.is_dir():
        return MAP_EDITOR_MAP_DIR
    return GAME_MAP_DIR
