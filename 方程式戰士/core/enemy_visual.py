"""特殊敵人 Kenney 貼圖載入與透明度。"""
from __future__ import annotations

import pygame

from .constants import ENEMY_VISUAL_SCALE, TILE_SIZE
from .enemy_archetypes import ALL_SPECIAL_ENEMY_GIDS
from .enums import ActionTypes
from .map_tile_loader import surface_for_gid
from .soldier import (
    ENEMY_KENNEY_TILE_RGB,
    ENEMY_KENNEY_WALK_PAIR_GIDS,
    ENEMY_KENNEY_WALK_SEQUENCE_GIDS,
)


def apply_enemy_appearance(enemy) -> None:
    """依 GID 載入 Kenney 貼圖（非僅 walk pair 動畫格）。"""
    if enemy.enemy_gid in ENEMY_KENNEY_WALK_PAIR_GIDS:
        enemy._apply_kenney_walk_pair_if_any()
        return
    if enemy.enemy_gid in ENEMY_KENNEY_WALK_SEQUENCE_GIDS:
        enemy._apply_kenney_walk_sequence_if_any()
        return
    scale = float(getattr(enemy, "scale_mult", 1.0))
    px = max(12, int(TILE_SIZE * ENEMY_VISUAL_SCALE * scale))
    rgb = ENEMY_KENNEY_TILE_RGB.get(enemy.enemy_gid, (200, 90, 100))
    img = surface_for_gid(enemy.enemy_gid, px, fallback_rgb=rgb)
    if img is None:
        return
    if pygame.display.get_init():
        try:
            img = img.convert_alpha()
        except pygame.error:
            pass
    frames = [img]
    for action in ActionTypes:
        enemy.animation_list[action] = frames if action != ActionTypes.DEATH else frames
    enemy.frame_index = 0
    enemy.image = img
    cx, cy = enemy.rect.center
    enemy.rect = enemy.image.get_rect(center=(cx, cy))
    enemy.width = enemy.rect.width
    enemy.height = enemy.rect.height


def refresh_enemy_alpha(enemy) -> None:
    """狀態改變透明度後重建貼圖（成對動畫格在 draw 時套用 alpha）。"""
    if enemy.enemy_gid in ENEMY_KENNEY_WALK_PAIR_GIDS:
        enemy._apply_kenney_walk_pair_if_any()
        return
    if enemy.enemy_gid in ENEMY_KENNEY_WALK_SEQUENCE_GIDS:
        return
    if enemy.enemy_gid in ALL_SPECIAL_ENEMY_GIDS or enemy.enemy_gid >= 256:
        apply_enemy_appearance(enemy)
