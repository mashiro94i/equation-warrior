"""Sprite 與 UI：預設程式繪製；可選擇在 `assets/img/` 放 PNG 覆寫（見各 load_* 介面）。"""
from __future__ import annotations

from pathlib import Path

import pygame

from .constants import (
    BLACK, BLUE, DARK_GRAY, GOLD, GRAY, GREEN,
    PURPLE, RED, TILE_SIZE, WATER_BLUE, WHITE,
)
from .paths import PLAYER_KENNEY_TILE

# ---------------------------------------------------------------------------
# `方程式戰士/assets/img/` — 唯一讀檔根目錄（不依賴執行時工作目錄）
# 建議目錄：
#   img/player/<Action>/   *.png  角色動畫
#   img/enemy/<Action>/    *.png
#   img/tiles/obstacle.png, water_0.png, …  關卡磚（可選）
#   img/ui/cursor.png, hint_move.png, button_bg.png  介面（可選）
# ---------------------------------------------------------------------------
_ASSETS_IMG_ROOT = Path(__file__).resolve().parent.parent / "assets" / "img"

_tile_cache: dict[str, pygame.Surface] = {}
_player_kenney_cache: dict[float, pygame.Surface] = {}
_hint_icons: dict[str, pygame.Surface] | None = None
_cursor_custom: pygame.Surface | None = None
_cursor_custom_checked = False

CONTROL_HINT_KEYS = ("move", "jump", "shoot", "grenade")
_HINT_ICON_COLORS = {
    "move": (70, 130, 210),
    "jump": (80, 200, 110),
    "shoot": (220, 180, 60),
    "grenade": (200, 90, 90),
}


def assets_img_root() -> Path:
    """回傳 `方程式戰士/assets/img` 絕對路徑。"""
    return _ASSETS_IMG_ROOT


def load_img_png(relative_under_img: str) -> pygame.Surface | None:
    """
    讀取 `assets/img/<relative_under_img>` 單一 PNG（相對路徑用 `/`）。
    檔案不存在或載入失敗回傳 None。
    """
    path = _ASSETS_IMG_ROOT / Path(relative_under_img)
    if not path.is_file():
        return None
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except pygame.error:
        return None


def load_img_png_scaled(relative_under_img: str, scale: float) -> pygame.Surface | None:
    """讀 PNG 並依 scale 縮放；失敗回傳 None。"""
    surf = load_img_png(relative_under_img)
    if surf is None:
        return None
    w, h = surf.get_width(), surf.get_height()
    return pygame.transform.scale(
        surf,
        (max(1, int(w * scale)), max(1, int(h * scale))),
    )


def load_player_kenney_frame(scale: float) -> pygame.Surface | None:
    """玩家：Kenney tiny-dungeon `tile_0084.png`（巫師）。"""
    if scale in _player_kenney_cache:
        return _player_kenney_cache[scale]
    if not PLAYER_KENNEY_TILE.is_file():
        return None
    try:
        img = pygame.image.load(str(PLAYER_KENNEY_TILE)).convert_alpha()
        w, h = img.get_width(), img.get_height()
        surf = pygame.transform.scale(
            img,
            (max(1, int(w * scale)), max(1, int(h * scale))),
        )
        _player_kenney_cache[scale] = surf
        return surf
    except pygame.error:
        return None


def load_soldier_action_frames(char_key: str, action_name: str, scale: float, *, is_player: bool) -> list:
    """
    讀 `assets/img/<char_key>/<action_name>/*.png`（依檔名排序）。
    若沒有任何有效影格，回傳單一幾何 fallback 列表。

    char_key: 通常為 `CharacterTypes.value`（\"player\" / \"enemy\"）
    action_name: `ActionTypes.value`（\"Idle\", \"Run\", …）
    """
    if is_player:
        kenney = load_player_kenney_frame(scale)
        if kenney is not None:
            return [kenney]
    dir_path = _ASSETS_IMG_ROOT / char_key / str(action_name)
    frames: list = []
    if dir_path.is_dir():
        for p in sorted(dir_path.glob("*.png")):
            try:
                rel = p.relative_to(_ASSETS_IMG_ROOT).as_posix()
            except ValueError:
                continue
            surf = load_img_png_scaled(rel, scale)
            if surf is not None:
                frames.append(surf)
    if not frames:
        fb = fallback_player_frame if is_player else fallback_enemy_frame
        return [fb(scale)]
    return frames


def _try_tile_png(filename: str) -> pygame.Surface | None:
    surf = load_img_png(f"tiles/{filename}")
    if surf is None:
        return None
    return pygame.transform.scale(surf, (TILE_SIZE, TILE_SIZE))


def _get_cached_tile(key: str, loader):
    if key not in _tile_cache:
        _tile_cache[key] = loader()
    return _tile_cache[key]


def tile_obstacle():
    def load():
        img = _try_tile_png("obstacle.png")
        return img if img is not None else fallback_tile_dirt()

    return _get_cached_tile("obstacle", load)


def tile_water(variant: int = 0):
    def load():
        img = _try_tile_png(f"water_{variant}.png")
        return img if img is not None else fallback_tile_water()

    return _get_cached_tile(f"water_{variant}", load)


def tile_decoration(variant: int):
    def load():
        img = _try_tile_png(f"decoration_{variant}.png")
        return img if img is not None else fallback_tile_decoration()

    return _get_cached_tile(f"decoration_{variant}", load)


def tile_exit():
    def load():
        img = _try_tile_png("exit.png")
        return img if img is not None else fallback_tile_exit()

    return _get_cached_tile("exit", load)


def tile_health_pickup():
    def load():
        img = _try_tile_png("health_pickup.png")
        return img if img is not None else fallback_tile_health_box()

    return _get_cached_tile("health_pickup", load)


def get_ui_button_background(width: int, height: int) -> pygame.Surface:
    img = load_img_png("ui/button_bg.png")
    if img is not None:
        try:
            return pygame.transform.scale(img, (width, height))
        except pygame.error:
            pass
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    surf.fill((52, 56, 72, 245))
    pygame.draw.rect(surf, (170, 185, 205), surf.get_rect(), 2)
    return surf


def _ensure_hint_icons():
    global _hint_icons
    if _hint_icons is None:
        _hint_icons = {}
        for key in CONTROL_HINT_KEYS:
            ic = load_img_png(f"ui/hint_{key}.png")
            if ic is not None:
                try:
                    _hint_icons[key] = pygame.transform.scale(ic, (36, 36))
                except pygame.error:
                    ic = None
            if key not in _hint_icons:
                s = pygame.Surface((36, 36), pygame.SRCALPHA)
                c = _HINT_ICON_COLORS.get(key, (100, 100, 100))
                s.fill(c)
                pygame.draw.rect(s, WHITE, s.get_rect(), 2)
                _hint_icons[key] = s
    return _hint_icons


def _ensure_playing_cursor_surface():
    global _cursor_custom, _cursor_custom_checked
    if not _cursor_custom_checked:
        _cursor_custom_checked = True
        c = load_img_png("ui/cursor.png")
        if c is not None:
            try:
                _cursor_custom = pygame.transform.scale(c, (32, 32))
            except pygame.error:
                _cursor_custom = None
    return _cursor_custom


def draw_playing_cursor(screen: pygame.Surface, game_xy):
    """邏輯座標：有 `assets/img/ui/cursor.png` 則貼圖，否則畫十字。"""
    x, y = int(game_xy[0]), int(game_xy[1])
    surf = _ensure_playing_cursor_surface()
    if surf is not None:
        screen.blit(surf, (x - surf.get_width() // 2, y - surf.get_height() // 2))
        return
    r = 14
    pygame.draw.circle(screen, WHITE, (x, y), r, 2)
    pygame.draw.line(screen, WHITE, (x - 9, y), (x + 9, y), 2)
    pygame.draw.line(screen, WHITE, (x, y - 9), (x, y + 9), 2)


def draw_control_hint_strip(screen: pygame.Surface):
    """畫面下方：有 `assets/img/ui/hint_<key>.png` 則用圖，否則色塊。"""
    icons = _ensure_hint_icons()
    if not icons:
        return
    from .constants import SCREEN_HEIGHT

    base_y = SCREEN_HEIGHT - 68
    pad = 12
    x = pad
    for key in CONTROL_HINT_KEYS:
        img = icons.get(key)
        if img is not None:
            screen.blit(img, (x, base_y))
            x += img.get_width() + 8


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
