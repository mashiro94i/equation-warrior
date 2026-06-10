"""從 kenny_assets 依 GID 規則載入 Kenney 圖塊貼圖。"""
from __future__ import annotations

from pathlib import Path

import pygame

from .constants import KENNEY_TILE_BASE
from .kenney import asset_packs, sheet_palette
from .paths import KENNEY_ASSETS_ROOT

_PACK_STRIDE = asset_packs.PACK_STRIDE
_CACHE: dict[tuple[int, int], pygame.Surface | None] = {}
_PAGE_STATES: dict[int, object] = {}
_PACK_DIRS: list[Path] | None = None


def _ensure_packs() -> list[Path]:
    global _PACK_DIRS
    if _PACK_DIRS is not None:
        return _PACK_DIRS
    _PACK_DIRS = asset_packs.list_pack_dirs(KENNEY_ASSETS_ROOT)
    return _PACK_DIRS


def _get_page_state(page_index: int):
    if page_index in _PAGE_STATES:
        return _PAGE_STATES[page_index]
    packs = _ensure_packs()
    if not packs:
        return None
    pi = page_index % len(packs)
    st = sheet_palette.load_page_state(packs[pi])
    _PAGE_STATES[page_index] = st
    return st


def surface_for_gid(gid: int, size: int) -> pygame.Surface | None:
    """依 GID 從 Kenney 包取出 PNG；失敗回傳 None。"""
    if gid < KENNEY_TILE_BASE:
        return None
    key = (gid, size)
    if key in _CACHE:
        return _CACHE[key]

    rel = gid - KENNEY_TILE_BASE
    page = rel // _PACK_STRIDE
    loc = rel % _PACK_STRIDE
    st = _get_page_state(page)
    if st is None or loc >= st.cell_count():
        _CACHE[key] = None
        return None

    row, col = divmod(loc, st.ncols)
    try:
        surf = sheet_palette.extract_tile_surface(st, col, row, size)
        _CACHE[key] = surf
        return surf
    except pygame.error:
        _CACHE[key] = None
        return None


def clear_kenney_cache() -> None:
    _CACHE.clear()
    _PAGE_STATES.clear()
