"""
Map CSV save/load (tile grid + flip state).

存檔時同時寫入 `map_editor/map/` 與 `方程式戰士/map/`（主遊戲讀檔用）。
"""
import csv
import os
import shutil
from pathlib import Path

ENCODING = "utf-8"
DELIMITER = ","
FLIP_SUFFIX = "_flip"


def get_map_dir() -> str:
    """地圖編輯器主目錄：`map_editor/map/`。"""
    editor_root = Path(__file__).resolve().parent
    return str(editor_root / "map")


def get_game_map_dir() -> Path:
    """主遊戲鏡像目錄：`方程式戰士/map/`。"""
    editor_root = Path(__file__).resolve().parent
    return editor_root.parent / "方程式戰士" / "map"


def _flip_path(path: str | Path) -> Path:
    base = Path(path)
    return base.with_name(base.stem + FLIP_SUFFIX + base.suffix)


def _write_level_pair(path: Path, grid: list, flip_x_grid: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding=ENCODING) as f:
        w = csv.writer(f, delimiter=DELIMITER)
        for row in grid:
            w.writerow(row)
    flip_path = _flip_path(path)
    with open(flip_path, "w", newline="", encoding=ENCODING) as f:
        w = csv.writer(f, delimiter=DELIMITER)
        for row in flip_x_grid:
            w.writerow([1 if cell else 0 for cell in row])


def save_csv(path: str, grid: list, flip_x_grid: list) -> None:
    """Save grid + flip to editor map dir and mirror to 方程式戰士/map/."""
    src = Path(path)
    _write_level_pair(src, grid, flip_x_grid)
    mirror = get_game_map_dir() / src.name
    _write_level_pair(mirror, grid, flip_x_grid)


def sync_all_maps_to_game() -> int:
    """將 map_editor/map 內所有 level*.csv 與 _flip.csv 複製到 方程式戰士/map/。"""
    editor_map = Path(get_map_dir())
    game_map = get_game_map_dir()
    game_map.mkdir(parents=True, exist_ok=True)
    count = 0
    if not editor_map.is_dir():
        return 0
    for src in sorted(editor_map.glob("level*.csv")):
        shutil.copy2(src, game_map / src.name)
        count += 1
        flip = _flip_path(src)
        if flip.is_file():
            shutil.copy2(flip, game_map / flip.name)
    return count


def load_csv(path: str) -> list | None:
    if not os.path.isfile(path):
        return None
    with open(path, "r", newline="", encoding=ENCODING) as f:
        rows = list(csv.reader(f))
    return [[int(x) for x in row] for row in rows]


def load_flip_csv(path: str) -> list | None:
    fp = _flip_path(path)
    if not fp.is_file():
        return None
    with open(fp, "r", newline="", encoding=ENCODING) as f:
        rows = list(csv.reader(f))
    return [[int(x) != 0 for x in row] for row in rows]
