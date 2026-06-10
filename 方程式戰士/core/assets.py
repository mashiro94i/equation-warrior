"""Sprite 與 UI：預設程式繪製；可選擇在 `assets/img/` 放 PNG 覆寫（見各 load_* 介面）。"""
from __future__ import annotations

from pathlib import Path

import pygame

from .constants import (
    BLACK, BLUE, DARK_GRAY, GOLD, GRAY, GREEN,
    PURPLE, RED, TILE_SIZE, WATER_BLUE, WHITE,
)
from .constants import player_scientist_visual_scale
from .enums import IntegralAxis, PlayerMode
from .paths import ASSETS_IMG, ASSETS_TILE, GAME_ROOT, PLAYER_KENNEY_TILE, SCIENTIST_PIPELINE_DIR

# Kenney input-prompts-pixel（地圖編輯器 GID）
CURSOR_GID_CALC = 834
CURSOR_GID_AREA_IDLE = 837
CURSOR_GID_AREA_DRAG = 838

# ---------------------------------------------------------------------------
# `方程式戰士/assets/img/` — 唯一讀檔根目錄（不依賴執行時工作目錄）
# 執行期目錄（見 assets/README.md）：
#   img/player/scientist/<Action>/   玩家動畫
#   img/tile/<name>.png              磚覆寫（GID 或 obstacle.png 等）
#   img/ui/cursor_*.png              游標
# 敵人 Kenney GID → core/kenney + kenny_assets/
# 素材管線 → tools/scientist_pipeline/
# ---------------------------------------------------------------------------
_ASSETS_IMG_ROOT = ASSETS_IMG

_tile_cache: dict[str, pygame.Surface] = {}
_player_kenney_cache: dict[float, pygame.Surface] = {}
_hint_icons: dict[str, pygame.Surface] | None = None
_btn_bg_cache: dict[tuple[int, int], pygame.Surface] = {}
_cursor_custom: pygame.Surface | None = None
_cursor_custom_checked = False
_cursor_calc: pygame.Surface | None = None
_cursor_calc_checked = False
_cursor_area_idle: pygame.Surface | None = None
_cursor_area_idle_checked = False
_cursor_area_drag: pygame.Surface | None = None
_cursor_area_drag_checked = False
_cursor_brush: pygame.Surface | None = None
_cursor_brush_checked = False
_cursor_calc_flipped: pygame.Surface | None = None
_cursor_calc_flipped_checked = False
_brush_cursor_tip: tuple[pygame.Surface, int, int] | None = None

_CURSOR_PX = 32
_CURSOR_CALC_MODES = frozenset({
    PlayerMode.DERIVATIVE_BLOCK,
    PlayerMode.INTEGRAL_BLOCK,
    PlayerMode.INTEGRAL_XY,
    PlayerMode.SQUARE_BLOCK,
    PlayerMode.SQRT_BLOCK,
})

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
        surf = pygame.image.load(str(path))
        try:
            return surf.convert_alpha()
        except pygame.error:
            return surf.convert()
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


def scientist_pipeline_root() -> Path:
    return SCIENTIST_PIPELINE_DIR


def player_scientist_root() -> Path:
    return _ASSETS_IMG_ROOT / "player" / "scientist"


def _sprite_body_pixel_count(surf: pygame.Surface | None) -> int:
    if surf is None:
        return 0
    try:
        rect = surf.get_bounding_rect(min_alpha=32)
    except TypeError:
        rect = surf.get_bounding_rect()
    if rect is None or rect.width <= 0 or rect.height <= 0:
        return 0
    return int(rect.width) * int(rect.height)


def scientist_sprites_available() -> bool:
    idle_dir = player_scientist_root() / "Idle"
    return idle_dir.is_dir() and any(idle_dir.glob("*.png"))


def _load_scientist_dir_frames(action_name: str, scale: float) -> list:
    dir_path = player_scientist_root() / str(action_name)
    frames: list = []
    if not dir_path.is_dir():
        return frames
    for p in sorted(dir_path.glob("*.png")):
        try:
            rel = p.relative_to(_ASSETS_IMG_ROOT).as_posix()
        except ValueError:
            continue
        surf = load_img_png_scaled(rel, scale)
        if surf is not None:
            frames.append(surf)
    return frames


def load_player_scientist_frames(action_name: str, scale: float) -> list:
    """讀 `assets/img/player/scientist/<Action>/`；Jump 僅 00=落地、01=空中。"""
    if action_name == "Jump":
        frames: list = []
        jump_dir = player_scientist_root() / "Jump"
        for rel in ("player/scientist/Jump/00.png", "player/scientist/Jump/01.png"):
            surf = load_img_png_scaled(rel, scale)
            if surf is not None:
                frames.append(surf)
        if len(frames) == 2:
            return frames
        pipe = scientist_pipeline_root() / "Jump"
        for fname in ("jump-1.png", "jump-2.png"):
            p = pipe / fname
            if p.is_file():
                try:
                    img = pygame.image.load(str(p)).convert_alpha()
                    w, h = img.get_width(), img.get_height()
                    frames.append(
                        pygame.transform.scale(img, (max(1, int(w * scale)), max(1, int(h * scale))))
                    )
                except pygame.error:
                    pass
        if frames:
            return frames

    if action_name == "Run":
        run_frames = _load_scientist_dir_frames("Run", scale)
        if run_frames and _sprite_body_pixel_count(run_frames[0]) >= 400:
            return run_frames
        idle_frames = _load_scientist_dir_frames("Idle", scale)
        if idle_frames:
            return idle_frames

    return _load_scientist_dir_frames(action_name, scale)


_potion_projectile_cache: dict[float, list] = {}


def load_potion_projectile_frames(scale: float = 1.0) -> list:
    """科學家藥瓶投射物（`projectile/`，跳過已刪的 -1）。"""
    if scale in _potion_projectile_cache:
        return _potion_projectile_cache[scale]
    frames: list = []
    deliver = player_scientist_root() / "projectile"
    if deliver.is_dir():
        for p in sorted(deliver.glob("*.png")):
            try:
                rel = p.relative_to(_ASSETS_IMG_ROOT).as_posix()
            except ValueError:
                continue
            surf = load_img_png_scaled(rel, scale)
            if surf is not None:
                frames.append(surf)
    if not frames:
        pipe = scientist_pipeline_root() / "projectile"
        for i in (3, 4):
            p = pipe / f"projectile-{i}.png"
            if p.is_file():
                try:
                    img = pygame.image.load(str(p)).convert_alpha()
                    w, h = img.get_width(), img.get_height()
                    frames.append(
                        pygame.transform.scale(img, (max(1, int(w * scale)), max(1, int(h * scale))))
                    )
                except pygame.error:
                    pass
    _potion_projectile_cache[scale] = frames
    return frames


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
    if is_player and scientist_sprites_available():
        sci = load_player_scientist_frames(action_name, player_scientist_visual_scale(scale))
        if sci:
            return sci
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
    path = ASSETS_TILE / filename
    if not path.is_file():
        return None
    try:
        surf = pygame.image.load(str(path))
        try:
            surf = surf.convert_alpha()
        except pygame.error:
            surf = surf.convert()
        return pygame.transform.scale(surf, (TILE_SIZE, TILE_SIZE))
    except pygame.error:
        return None


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
    key = (int(width), int(height))
    cached = _btn_bg_cache.get(key)
    if cached is not None:
        return cached
    img = load_img_png("ui/button_bg.png")
    if img is not None:
        try:
            surf = pygame.transform.scale(img, (width, height))
            _btn_bg_cache[key] = surf
            return surf
        except pygame.error:
            pass
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    surf.fill((52, 56, 72, 245))
    pygame.draw.rect(surf, (170, 185, 205), surf.get_rect(), 2)
    _btn_bg_cache[key] = surf
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


def _scale_cursor_surface(surf: pygame.Surface) -> pygame.Surface:
    if surf.get_width() == _CURSOR_PX and surf.get_height() == _CURSOR_PX:
        return surf
    return pygame.transform.scale(surf, (_CURSOR_PX, _CURSOR_PX))


def _load_ui_cursor_png_or_gid(rel_path: str, gid: int) -> pygame.Surface | None:
    c = load_img_png(rel_path)
    if c is not None:
        try:
            return _scale_cursor_surface(c)
        except pygame.error:
            pass
    from . import kenney_tiles

    return kenney_tiles.surface_for_gid(gid, _CURSOR_PX)


def _ensure_playing_cursor_surface():
    global _cursor_custom, _cursor_custom_checked
    if not _cursor_custom_checked:
        _cursor_custom_checked = True
        c = load_img_png("ui/cursor.png")
        if c is not None:
            try:
                _cursor_custom = _scale_cursor_surface(c)
            except pygame.error:
                _cursor_custom = None
    return _cursor_custom


def _ensure_cursor_calc():
    global _cursor_calc, _cursor_calc_checked
    if not _cursor_calc_checked:
        _cursor_calc_checked = True
        _cursor_calc = _load_ui_cursor_png_or_gid("ui/cursor_calc.png", CURSOR_GID_CALC)
    return _cursor_calc


def _ensure_cursor_calc_flipped():
    """微積分／平方／根號：Kenney 游標上下顛倒。"""
    global _cursor_calc_flipped, _cursor_calc_flipped_checked
    if not _cursor_calc_flipped_checked:
        _cursor_calc_flipped_checked = True
        base = _ensure_cursor_calc()
        if base is not None:
            _cursor_calc_flipped = pygame.transform.flip(base, False, True)
    return _cursor_calc_flipped


def _ensure_cursor_area_idle():
    global _cursor_area_idle, _cursor_area_idle_checked
    if not _cursor_area_idle_checked:
        _cursor_area_idle_checked = True
        _cursor_area_idle = _load_ui_cursor_png_or_gid(
            "ui/cursor_area_idle.png", CURSOR_GID_AREA_IDLE,
        )
    return _cursor_area_idle


def _ensure_cursor_area_drag():
    global _cursor_area_drag, _cursor_area_drag_checked
    if not _cursor_area_drag_checked:
        _cursor_area_drag_checked = True
        _cursor_area_drag = _load_ui_cursor_png_or_gid(
            "ui/cursor_area_drag.png", CURSOR_GID_AREA_DRAG,
        )
    return _cursor_area_drag


def _ensure_cursor_brush():
    global _cursor_brush, _cursor_brush_checked
    if not _cursor_brush_checked:
        _cursor_brush_checked = True
        c = load_img_png("ui/cursor_brush.png")
        if c is not None:
            try:
                _cursor_brush = _scale_cursor_surface(c)
            except pygame.error:
                _cursor_brush = None
    return _cursor_brush


def _brush_cursor_fixed() -> tuple[pygame.Surface, int, int] | None:
    """上下+左右翻轉；鼠標對準翻轉後圖片的左下角。"""
    global _brush_cursor_tip
    if _brush_cursor_tip is not None:
        return _brush_cursor_tip
    base = _ensure_cursor_brush()
    if base is None:
        return None
    surf = pygame.transform.flip(base, True, True)
    w, h = surf.get_size()
    _brush_cursor_tip = (surf, 0, h - 1)
    return _brush_cursor_tip


def _block_kind_axis_for_mode(
    mode: PlayerMode,
    integral_axis: IntegralAxis | str | None,
) -> tuple[str, str] | None:
    if mode == PlayerMode.DERIVATIVE_BLOCK:
        return "derivative", "y"
    if mode in (PlayerMode.INTEGRAL_BLOCK, PlayerMode.INTEGRAL_XY):
        ax = integral_axis.value if isinstance(integral_axis, IntegralAxis) else str(integral_axis or "y")
        return "integral", ax.lower()
    if mode == PlayerMode.SQUARE_BLOCK:
        return "square", "y"
    if mode == PlayerMode.SQRT_BLOCK:
        return "sqrt", "y"
    return None


def _blit_cursor_centered(screen: pygame.Surface, surf: pygame.Surface, x: int, y: int) -> None:
    screen.blit(surf, (x - surf.get_width() // 2, y - surf.get_height() // 2))


def _draw_cursor_crosshair(screen: pygame.Surface, x: int, y: int) -> None:
    r = 14
    pygame.draw.circle(screen, WHITE, (x, y), r, 2)
    pygame.draw.line(screen, WHITE, (x - 9, y), (x + 9, y), 2)
    pygame.draw.line(screen, WHITE, (x, y - 9), (x, y + 9), 2)


def draw_playing_cursor(
    screen: pygame.Surface,
    game_xy,
    mode: PlayerMode | None = None,
    *,
    area_dragging: bool = False,
    integral_axis: IntegralAxis | str | None = None,
):
    """依 PlayerMode 繪製自訂游標（PLAYING 時系統游標已隱藏）。"""
    x, y = int(game_xy[0]), int(game_xy[1])
    if mode is None:
        mode = PlayerMode.FUNCTION

    if mode == PlayerMode.FUNCTION:
        surf = _ensure_playing_cursor_surface()
        if surf is not None:
            _blit_cursor_centered(screen, surf, x, y)
            return
        _draw_cursor_crosshair(screen, x, y)
        return

    block = _block_kind_axis_for_mode(mode, integral_axis)
    if block is not None:
        from .calculus_blocks import draw_carried_block_preview

        kind, axis = block
        draw_carried_block_preview(screen, x, y, kind, axis)
        cursor = _ensure_cursor_calc_flipped()
        if cursor is not None:
            _blit_cursor_centered(screen, cursor, x, y)
        else:
            _draw_cursor_crosshair(screen, x, y)
        return

    if mode == PlayerMode.BRUSH:
        variant = _brush_cursor_fixed()
        if variant is not None:
            surf, hx, hy = variant
            screen.blit(surf, (x - hx, y - hy))
            return
        _draw_cursor_crosshair(screen, x, y)
        return

    if mode == PlayerMode.AREA_MOVE:
        surf = _ensure_cursor_area_drag() if area_dragging else _ensure_cursor_area_idle()
        if surf is not None:
            _blit_cursor_centered(screen, surf, x, y)
            return
        _draw_cursor_crosshair(screen, x, y)
        return

    surf = _ensure_playing_cursor_surface()
    if surf is not None:
        _blit_cursor_centered(screen, surf, x, y)
        return
    _draw_cursor_crosshair(screen, x, y)


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
