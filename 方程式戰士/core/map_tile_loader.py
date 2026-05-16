"""關卡 CSV 用數字圖塊：與 map_editor 相同編號，PNG 放 `assets/img/tile/<id>.png`。"""
from __future__ import annotations

from pathlib import Path

import pygame

_CACHE: dict[tuple[int, int], pygame.Surface | None] = {}


def _tile_png_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "img" / "tile"


def surface_for_csv_tile(tile_id: int, size: int) -> pygame.Surface | None:
    """有 `assets/img/tile/<id>.png` 則載入並縮放；無則回傳 None（沿用 assets 內建圖）。"""
    if tile_id < 0:
        return None
    key = (tile_id, size)
    if key in _CACHE:
        return _CACHE[key]
    path = _tile_png_dir() / f"{tile_id}.png"
    if not path.is_file():
        _CACHE[key] = None
        return None
    try:
        img = pygame.image.load(str(path)).convert_alpha()
        s = pygame.transform.scale(img, (size, size))
        _CACHE[key] = s
        return s
    except pygame.error:
        _CACHE[key] = None
        return None


def clear_tile_png_cache() -> None:
    _CACHE.clear()


def make_colored_stub(size: int, rgb: tuple[int, int, int]) -> pygame.Surface:
    s = pygame.Surface((size, size))
    s.fill(rgb)
    pygame.draw.rect(s, (30, 30, 30), s.get_rect(), 2)
    return s


def make_kenney_pack_stub(size: int) -> pygame.Surface:
    """地圖含 Kenney 大編號時，主遊戲以簡單色塊當障礙顯示。"""
    return make_colored_stub(size, (88, 92, 104))


def surface_for_gid(tile_id: int, size: int, fallback_rgb: tuple[int, int, int] | None = None) -> pygame.Surface | None:
    """assets/img/tile → Kenney 包 → 語意色佔位；皆無則 None（空氣）。"""
    s = surface_for_csv_tile(tile_id, size)
    if s is not None:
        return s
    from . import kenney_tiles

    s = kenney_tiles.surface_for_gid(tile_id, size)
    if s is not None:
        return s
    if fallback_rgb is not None:
        return make_colored_stub(size, fallback_rgb)
    return None
