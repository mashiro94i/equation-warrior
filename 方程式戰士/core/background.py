"""視差背景（與 practice/game.py 相同捲動倍率）。"""
from __future__ import annotations

from pathlib import Path

import pygame

from .constants import SCREEN_HEIGHT, SCREEN_WIDTH, SKY

_BG_DIR = Path(__file__).resolve().parent.parent / "assets" / "background"
_LAYER_FILES = (
    ("sky_cloud", "sky_cloud.png", 0.5),
    ("mountain", "mountain.png", 0.6),
    ("pine1", "pine1.png", 0.7),
    ("pine2", "pine2.png", 0.8),
)
_layers: dict[str, pygame.Surface] = {}
_loaded = False


def _load_layers() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    for key, filename, _ in _LAYER_FILES:
        path = _BG_DIR / filename
        if path.is_file():
            try:
                _layers[key] = pygame.image.load(str(path)).convert_alpha()
            except pygame.error:
                pass


def draw_parallax_background(surface: pygame.Surface, background_scroll: float) -> None:
    """依 background_scroll 繪製多層視差背景。"""
    _load_layers()
    surface.fill(SKY)
    if not _layers:
        return
    scroll = float(background_scroll)
    sky = _layers.get("sky_cloud")
    if sky is not None:
        width = sky.get_width()
        for i in range(5):
            surface.blit(sky, (int(i * width - scroll * 0.5), 0))
    mountain = _layers.get("mountain")
    if mountain is not None:
        width = mountain.get_width()
        y = SCREEN_HEIGHT - mountain.get_height() - 300
        for i in range(5):
            surface.blit(mountain, (int(i * width - scroll * 0.6), y))
    pine1 = _layers.get("pine1")
    if pine1 is not None:
        width = pine1.get_width()
        y = SCREEN_HEIGHT - pine1.get_height() - 150
        for i in range(5):
            surface.blit(pine1, (int(i * width - scroll * 0.7), y))
    pine2 = _layers.get("pine2")
    if pine2 is not None:
        width = pine2.get_width()
        y = SCREEN_HEIGHT - pine2.get_height()
        for i in range(5):
            surface.blit(pine2, (int(i * width - scroll * 0.8), y))
