"""輕量效能輔助（視野裁切、障礙物掃描）。"""
from __future__ import annotations

import pygame

from .constants import SCREEN_HEIGHT, SCREEN_WIDTH


def rect_in_play_view(rect: pygame.Rect, *, margin: int = 96) -> bool:
    """實體是否在邏輯螢幕附近（含邊界外緩衝）。"""
    view = pygame.Rect(-margin, -margin, SCREEN_WIDTH + margin * 2, SCREEN_HEIGHT + margin * 2)
    return view.colliderect(rect)


def iter_obstacles_in_probe(
    obstacle_list: list[tuple[pygame.Surface, pygame.Rect]],
    probe: pygame.Rect,
    *,
    foot_x: int | None = None,
):
    """僅掃描與 probe 相交的磚；可選 foot_x 先過濾水平距離。"""
    fx_lo = fx_hi = None
    if foot_x is not None:
        fx_lo = int(foot_x) - 12
        fx_hi = int(foot_x) + 12
    for pair in obstacle_list:
        rect = pair[1]
        if fx_lo is not None and (rect.right < fx_lo or rect.left > fx_hi):
            continue
        if rect.colliderect(probe):
            yield pair
