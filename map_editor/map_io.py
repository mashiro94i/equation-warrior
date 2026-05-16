"""
Map CSV save/load (tile grid + flip state).
"""
import csv
import os
from pathlib import Path

# ----- File format -----
ENCODING = "utf-8"
DELIMITER = ","
FLIP_SUFFIX = "_flip"


def get_map_dir() -> str:
    """地圖 CSV 目錄：`map_editor/map/`（與主遊戲讀檔路徑分離時可再整合）。"""
    editor_root = Path(__file__).resolve().parent
    return str(editor_root / "map")


def _flip_path(path: str) -> str:
    """e.g. map/level1.csv -> map/level1_flip.csv"""
    base, ext = os.path.splitext(path)
    return base + FLIP_SUFFIX + ext


def save_csv(path: str, grid: list, flip_x_grid: list) -> None:
    """Save grid as CSV and flip state to separate _flip.csv."""
    with open(path, "w", newline="", encoding=ENCODING) as f:
        w = csv.writer(f, delimiter=DELIMITER)
        for row in grid:
            w.writerow(row)
    flip_path = _flip_path(path)
    with open(flip_path, "w", newline="", encoding=ENCODING) as f:
        w = csv.writer(f, delimiter=DELIMITER)
        for row in flip_x_grid:
            w.writerow([1 if cell else 0 for cell in row])


def load_csv(path: str) -> list | None:
    """Load grid from CSV. Returns None if file missing."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", newline="", encoding=ENCODING) as f:
        rows = list(csv.reader(f))
    return [[int(x) for x in row] for row in rows]


def load_flip_csv(path: str) -> list | None:
    """Load flip grid (0/1) from _flip.csv. Returns None if file missing."""
    fp = _flip_path(path)
    if not os.path.isfile(fp):
        return None
    with open(fp, "r", newline="", encoding=ENCODING) as f:
        rows = list(csv.reader(f))
    return [[int(x) != 0 for x in row] for row in rows]
