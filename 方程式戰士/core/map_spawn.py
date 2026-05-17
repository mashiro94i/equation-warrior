"""地圖格座標 → 世界座標（出生／敵人標記格對齊腳底）。"""
from __future__ import annotations

import pygame

from .constants import ENEMY_VISUAL_SCALE, PLAYER_VISUAL_SCALE, TILE_SIZE


def normalize_map_gid(gid: int) -> int:
    """僅轉換已知語意別名（勿把裝飾格 66040 當成敵人）。"""
    return int(gid)


def _stand_top_in_cell(
    gx: int,
    gy: int,
    wall_obstacles: list,
    animated_wall_entries: list,
) -> int | None:
    """該格內可踩表面的最高 top（世界 y）。"""
    cell = pygame.Rect(gx * TILE_SIZE, gy * TILE_SIZE, TILE_SIZE, TILE_SIZE)
    best: int | None = None
    for _img, rect in wall_obstacles:
        if cell.colliderect(rect):
            top = int(rect.top)
            if best is None or top < best:
                best = top
    for entry in animated_wall_entries:
        rect = entry["rect"]
        if cell.colliderect(rect):
            top = int(rect.top)
            if best is None or top < best:
                best = top
    return best


def marker_center_on_ground(
    gx: int,
    gy: int,
    level_rows: int,
    wall_obstacles: list,
    animated_wall_entries: list,
    *,
    body_height: int,
) -> tuple[int, int]:
    """標記格 (gx, gy) 正下方（含同格）找地面；水平維持欄中心。"""
    cx = gx * TILE_SIZE + TILE_SIZE // 2
    for try_gy in range(gy, min(gy + 4, level_rows)):
        top = _stand_top_in_cell(gx, try_gy, wall_obstacles, animated_wall_entries)
        if top is not None:
            cy = int(top) - max(body_height // 2, 6)
            return cx, cy
    cy = gy * TILE_SIZE + TILE_SIZE // 2
    return cx, cy


def player_spawn_center(
    wall_obstacles: list,
    animated_wall_entries: list,
    gx: int,
    gy: int,
    level_rows: int,
) -> tuple[int, int]:
    h = max(24, int(34 * PLAYER_VISUAL_SCALE))
    return marker_center_on_ground(
        gx, gy, level_rows, wall_obstacles, animated_wall_entries, body_height=h,
    )


def enemy_spawn_center(
    wall_obstacles: list,
    animated_wall_entries: list,
    gx: int,
    gy: int,
    level_rows: int,
) -> tuple[int, int]:
    h = max(16, int(34 * ENEMY_VISUAL_SCALE))
    return marker_center_on_ground(
        gx, gy, level_rows, wall_obstacles, animated_wall_entries, body_height=h,
    )
