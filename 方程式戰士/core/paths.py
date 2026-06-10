"""專案路徑：地圖、素材、Kenney 包等。"""
from __future__ import annotations

from pathlib import Path

# 方程式戰士/ → 遊戲程式設計/
_WORKSPACE = Path(__file__).resolve().parent.parent.parent
_GAME_ROOT = Path(__file__).resolve().parent.parent

GAME_ROOT = _GAME_ROOT
ASSETS_ROOT = _GAME_ROOT / "assets"
ASSETS_IMG = ASSETS_ROOT / "img"
ASSETS_AUDIO = ASSETS_ROOT / "audio"
ASSETS_BACKGROUND = ASSETS_ROOT / "background"
ASSETS_TILE = ASSETS_IMG / "tile"
GAME_MAP_DIR = _GAME_ROOT / "map"

# 地圖編輯器產出（存檔時會同步鏡像至 GAME_MAP_DIR）
MAP_EDITOR_MAP_DIR = _WORKSPACE / "map_editor" / "map"
KENNEY_ASSETS_ROOT = _WORKSPACE / "kenny_assets"
PLAYER_KENNEY_TILE = KENNEY_ASSETS_ROOT / "kenney_tiny-dungeon" / "Tiles" / "tile_0084.png"
SCIENTIST_PIPELINE_DIR = _GAME_ROOT / "tools" / "scientist_pipeline"


def map_search_dirs() -> list[Path]:
    """地圖搜尋順序：map_editor/map（主）→ 方程式戰士/map（鏡像）。"""
    out: list[Path] = []
    if MAP_EDITOR_MAP_DIR.is_dir():
        out.append(MAP_EDITOR_MAP_DIR)
    if GAME_MAP_DIR.is_dir():
        out.append(GAME_MAP_DIR)
    return out


def find_map_dir_for_level(level: int) -> Path:
    """回傳含 level{N}.csv 或 level{N}_data.csv 的目錄。"""
    names = (f"level{level}.csv", f"level{level}_data.csv")
    for d in map_search_dirs():
        for name in names:
            if (d / name).is_file():
                return d
    return MAP_EDITOR_MAP_DIR if MAP_EDITOR_MAP_DIR.is_dir() else GAME_MAP_DIR
