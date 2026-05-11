"""Sprite 載入 helper + 幾何 fallback"""
import os
import pygame

from .constants import (
    BLACK, BLUE, DARK_GRAY, GOLD, GRAY, GREEN,
    PURPLE, RED, TILE_SIZE, WATER_BLUE, WHITE,
)


def load_or_geometry(asset_path, fallback_fn):
    """assets/.png 存在就讀，否則用 fallback_fn 畫 placeholder"""
    if os.path.exists(asset_path):
        try:
            return pygame.image.load(asset_path).convert_alpha()
        except pygame.error:
            return fallback_fn()
    return fallback_fn()


def fallback_player_frame(scale=1.0):
    size = int(36 * scale)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(surf, BLUE, (size // 2, size // 2), size // 2)
    pygame.draw.circle(surf, WHITE, (size // 2, size // 2), size // 2, 2)
    return surf


def fallback_enemy_frame(scale=1.0):
    size = int(34 * scale)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(surf, PURPLE, (0, 0, size, size))
    pygame.draw.rect(surf, BLACK, (0, 0, size, size), 2)
    return surf


def fallback_tile_dirt():
    surf = pygame.Surface((TILE_SIZE, TILE_SIZE))
    surf.fill(GRAY)
    pygame.draw.rect(surf, DARK_GRAY, surf.get_rect(), 1)
    return surf


def fallback_tile_water():
    surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    surf.fill(WATER_BLUE)
    return surf


def fallback_tile_decoration():
    surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    pygame.draw.polygon(
        surf,
        GREEN,
        [(TILE_SIZE // 2, 4), (TILE_SIZE - 4, TILE_SIZE - 4), (4, TILE_SIZE - 4)],
    )
    return surf


def fallback_tile_exit():
    surf = pygame.Surface((TILE_SIZE, TILE_SIZE))
    surf.fill(GOLD)
    pygame.draw.rect(surf, WHITE, (0, 0, TILE_SIZE, TILE_SIZE), 3)
    return surf


def fallback_tile_health_box():
    surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    surf.fill((220, 220, 220))
    pygame.draw.rect(surf, RED, (8, TILE_SIZE // 2 - 6, TILE_SIZE - 16, 12))
    pygame.draw.rect(surf, RED, (TILE_SIZE // 2 - 6, 8, 12, TILE_SIZE - 16))
    pygame.draw.rect(surf, BLACK, surf.get_rect(), 2)
    return surf
