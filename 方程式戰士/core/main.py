"""主迴圈 + state machine + 關卡切換"""
import math
import sys

import pygame

from .area_entity import (
    build_area_bodies_from_circle,
    build_area_bodies_from_polygon,
    pick_stationary_area_at,
)
from .csv_map_area_cells import spawn_area_bodies_for_gid65796
from . import game_audio
from . import settings_io
from .assets import (
    draw_control_hint_strip,
    draw_playing_cursor,
    get_ui_button_background,
)
from .background import draw_parallax_background
from .brush import BrushManager
from .calculus_blocks import (
    CalculusBlock,
    add_calculus_block_with_limit,
    resolve_algebra_block_interactions,
    resolve_calculus_block_interactions,
)
from .constants import (
    AREA_THROW_RELEASE_MIN_DIST, AREA_THROW_RELEASE_SPEED_MULT,
    BRUSH_MAX_TOTAL_LENGTH_PX,
    CALC_DERIVATIVE_EVICT_OLDEST_WHEN_FULL,
    CALC_INTEGRAL_EVICT_OLDEST_WHEN_FULL,
    DERIVATIVE_BLOCKS_MAX,
    DOUBLE_B_AREA_MOVE_MS,
    FPS,
    GOLD,
    INTEGRAL_BLOCKS_MAX,
    MAX_LEVEL,
    PINK,
    RED,
    SQRT_BLOCKS_MAX, SQUARE_BLOCKS_MAX,
    SCREEN_HEIGHT, SCREEN_WIDTH, SCROLL_THRESH, SIGMA_CHARGE_MAX, SIGMA_CHARGE_STEP_MS,
    SIGMA_CHARGE_STEP_VALUE,
    TILE_SIZE,
    SIGMA_FIRE_INTERVAL_MS, SIGMA_ZERO_BURST_COUNT, SKY, WHITE, BLACK, YELLOW,
    SPIKE_DAMAGE_INTERVAL_MS,
)
from .controller import EquationController, EquationDisplay
from .enums import ActionTypes, GameState, IntegralAxis, PlayerMode
from .fonts import get_font
from .gameplay import build_sigma_shot_schedule, placement_zone_around_player, point_in_placement_zone
from .interactions import (
    try_integral_xy_on_brush,
    try_integral_xy_on_enemy_bullet,
    try_sigmoid_on_enemy_bullet,
)
from .calculus_blocks import count_player_placed_calculus
from .level_modes import (
    derivative_requires_world_unlock,
    derivative_switch_key,
    get_level_mode_config,
)
from .map_tile_loader import surface_for_gid
from .mode_cooldowns import ModeCooldowns
from .projectile import NumericProjectile
from .enemy_archetypes import create_enemy
from . import enemy_special
from .enemy_special import blit_enemy_head_label
from .soldier import Enemy, Player
from .tile_animations import DERIVATIVE_UNLOCK_GIDS, UNDERWATER_AMBIENT_GIDS
from .tile_types import GID_KEY
from .ui import HealthBar, ScreenFade, TextButton
from .world import Decoration, Exit, HealthBox, HeartPickup, KeyPickup, KenneyVisualTile, Water, World


def init_level(
    level,
    projectile_group,
    enemy_bullet_group,
    enemy_group,
    water_group,
    decoration_group,
    exit_group,
    health_box_group,
    heart_group,
    key_pickup_group,
    derivative_group,
    integral_group,
    square_group,
    sqrt_group,
    area_group,
    numeric_group,
    brush_manager,
):
    for g in (
        projectile_group,
        enemy_bullet_group,
        enemy_group,
        water_group,
        decoration_group,
        exit_group,
        health_box_group,
        heart_group,
        key_pickup_group,
        derivative_group,
        integral_group,
        square_group,
        sqrt_group,
        area_group,
        numeric_group,
    ):
        g.empty()
    brush_manager.strokes.clear()
    brush_manager.current = None
    brush_manager.total_length = 0.0

    world = World()
    world.process_csv(level)
    spawn_area_bodies_for_gid65796(world.grid_data, TILE_SIZE, SCREEN_HEIGHT, world, area_group)
    for x, y, v in world.water_tiles:
        water_group.add(Water(x, y, v))
    for x, y, v in world.decorations:
        decoration_group.add(Decoration(x, y, v))
    for ex, ey, tid in world.exit_tiles:
        exit_group.add(Exit(ex, ey, tid))
    for x, y in world.health_box_positions:
        health_box_group.add(HealthBox(x, y))
    for hx, hy, tid in world.heart_pickups:
        heart_group.add(HeartPickup(hx, hy, tid))
    for kx, ky, tid in world.key_pickups:
        key_pickup_group.add(KeyPickup(kx, ky, tid))
    for vx, vy, vid, flip_x in world.kenney_visual_tiles:
        decoration_group.add(KenneyVisualTile(vx, vy, vid, flip_x=flip_x))
    for ex, ey, egid in world.enemy_spawns:
        enemy_group.add(create_enemy(ex, ey, egid))
    for cx, cy in world.calculus_derivative_spawns:
        derivative_group.add(CalculusBlock((cx, cy), "derivative", map_spawned=True))
    for cx, cy, axis in world.calculus_integral_spawns:
        integral_group.add(CalculusBlock((cx, cy), "integral", axis=axis, map_spawned=True))
    player = Player(*world.player_spawn)
    return world, player


_LEVEL_CSV_WARMED: set[int] = set()


def warm_level_csv(level: int) -> None:
    """預先解析關卡 CSV 並暖 Kenney 貼圖快取，減少首次選關卡頓。"""
    lv = int(level)
    if lv in _LEVEL_CSV_WARMED:
        return
    w = World()
    w.process_csv(lv)
    _LEVEL_CSV_WARMED.add(lv)


def main():
    pygame.init()
    saved = settings_io.load_settings()
    bgm_volume = float(saved.get("bgm_volume", 0.5))
    sfx_volume = float(saved.get("sfx_volume", 0.5))
    res = saved.get("resolution", [1600, 900])
    if not (isinstance(res, (list, tuple)) and len(res) == 2):
        res = [1600, 900]
    init_res = (int(res[0]), int(res[1]))
    window = pygame.display.set_mode(init_res)
    screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("方程式戰士 - Math Equation Warrior")
    clock = pygame.time.Clock()
    display_w, display_h = window.get_size()
    scale = min(display_w / SCREEN_WIDTH, display_h / SCREEN_HEIGHT)
    view_w = int(SCREEN_WIDTH * scale)
    view_h = int(SCREEN_HEIGHT * scale)
    view_x = (display_w - view_w) // 2
    view_y = (display_h - view_h) // 2

    font_large = get_font(48, bold=True)
    font_med = get_font(24, bold=True)

    def present_screen(*, flatten_focus: bool = False) -> None:
        window.fill((0, 0, 0))
        if (
            flatten_focus
            and player is not None
            and player_is_flattened
            and state in (GameState.PLAYING, GameState.DEATH)
        ):
            z = FLATTEN_VIEW_ZOOM
            sw = max(view_w + 1, int(view_w * z))
            sh = max(view_h + 1, int(view_h * z))
            big = pygame.transform.smoothscale(screen, (sw, sh))
            prx = player.rect.centerx / SCREEN_WIDTH
            pry = player.rect.centery / SCREEN_HEIGHT
            bx = int(prx * sw)
            by = int(pry * sh)
            src_x = max(0, min(bx - view_w // 2, sw - view_w))
            src_y = max(0, min(by - view_h // 2, sh - view_h))
            window.blit(big, (view_x, view_y), pygame.Rect(src_x, src_y, view_w, view_h))
        else:
            scaled = pygame.transform.smoothscale(screen, (view_w, view_h))
            window.blit(scaled, (view_x, view_y))
        pygame.display.update()

    def pump_boot_events() -> bool:
        """處理啟動階段事件；QUIT 時回傳 False。"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
        return True

    def draw_menu_boot_frame(subtitle: str | None = None) -> bool:
        screen.fill(SKY)
        title = font_large.render("方程式戰士", True, WHITE)
        screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50)))
        if subtitle:
            sub = font_med.render(subtitle, True, WHITE)
            screen.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30)))
        present_screen()
        return pump_boot_events()

    if not draw_menu_boot_frame():
        pygame.quit()
        sys.exit()

    font_small = get_font(18, bold=True)
    font_eq = get_font(22, bold=True)

    projectile_group = pygame.sprite.Group()
    enemy_bullet_group = pygame.sprite.Group()
    enemy_group = pygame.sprite.Group()
    water_group = pygame.sprite.Group()
    decoration_group = pygame.sprite.Group()
    exit_group = pygame.sprite.Group()
    health_box_group = pygame.sprite.Group()
    heart_group = pygame.sprite.Group()
    key_pickup_group = pygame.sprite.Group()
    derivative_group = pygame.sprite.Group()
    integral_group = pygame.sprite.Group()
    square_group = pygame.sprite.Group()
    sqrt_group = pygame.sprite.Group()
    area_group = pygame.sprite.Group()
    numeric_group = pygame.sprite.Group()

    brush_manager = BrushManager()
    mode_cd = ModeCooldowns()
    sigma_schedule = []
    sigma_mouse_down_ms = None
    last_b_key_ms = -10**9
    area_drag_target = None
    area_drag_dx = 0
    area_drag_dy = 0
    area_fling_mouse_end_mx = 0.0
    area_fling_mouse_end_my = 0.0
    area_drag_fling_anchor_mx = 0.0
    area_drag_fling_anchor_my = 0.0
    player_is_flattened = False
    player_crush_kill_at_ms = 0
    FLATTEN_VIEW_ZOOM = 1.38

    state = GameState.MENU
    level = 1
    world = None
    player = None
    health_bar = None
    controller = None
    last_spike_damage_ms = 0
    eq_display = EquationDisplay(font_eq)
    opening_fade = ScreenFade(BLACK, 16)
    death_fade = ScreenFade(PINK, 14)
    is_opening = False

    btn_w, btn_h = 220, 60
    cx = SCREEN_WIDTH // 2 - btn_w // 2
    btn_panel = get_ui_button_background(btn_w, btn_h)
    back_panel = get_ui_button_background(120, 44)
    start_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 120, "START", font_med, btn_w, btn_h, bg_surface=btn_panel)
    guide_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 30, "玩法介紹", font_med, btn_w, btn_h, bg_surface=btn_panel)
    settings_btn = TextButton(cx, SCREEN_HEIGHT // 2 + 60, "設置", font_med, btn_w, btn_h, bg_surface=btn_panel)
    exit_btn = TextButton(cx, SCREEN_HEIGHT // 2 + 150, "EXIT", font_med, btn_w, btn_h, bg_surface=btn_panel)
    lvl_bw, lvl_bh = 168, 52
    lvl_panel_btn = get_ui_button_background(lvl_bw, lvl_bh)
    lvl_gap = 20
    lvl_row_w = 3 * lvl_bw + 2 * lvl_gap
    lvl_x0 = SCREEN_WIDTH // 2 - lvl_row_w // 2
    lvl_y_pick = SCREEN_HEIGHT // 2 - 36
    level_pick_btn_1 = TextButton(
        lvl_x0, lvl_y_pick, "關卡 1", font_med, lvl_bw, lvl_bh, bg_surface=lvl_panel_btn
    )
    level_pick_btn_2 = TextButton(
        lvl_x0 + lvl_bw + lvl_gap, lvl_y_pick, "關卡 2", font_med, lvl_bw, lvl_bh, bg_surface=lvl_panel_btn
    )
    level_pick_btn_3 = TextButton(
        lvl_x0 + 2 * (lvl_bw + lvl_gap), lvl_y_pick, "關卡 3", font_med, lvl_bw, lvl_bh, bg_surface=lvl_panel_btn
    )
    level_select_back_btn = TextButton(
        SCREEN_WIDTH // 2 - 80, lvl_y_pick + lvl_bh + 28, "返回", font_med, 160, 48, bg_surface=back_panel
    )
    restart_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 40, "RESTART", font_med, btn_w, btn_h, bg_surface=btn_panel)
    revive_btn = TextButton(cx, SCREEN_HEIGHT // 2 + 10, "復活", font_med, btn_w, btn_h, bg_surface=btn_panel)
    pause_continue_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 100, "繼續", font_med, btn_w, btn_h, bg_surface=btn_panel)
    pause_settings_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 20, "設定", font_med, btn_w, btn_h, bg_surface=btn_panel)
    pause_exit_btn = TextButton(cx, SCREEN_HEIGHT // 2 + 60, "退出", font_med, btn_w, btn_h, bg_surface=btn_panel)
    back_btn = TextButton(20, 20, "返回", font_small, 120, 44, bg_surface=back_panel)
    guide_prev_btn = TextButton(180, SCREEN_HEIGHT - 90, "上一頁", font_small, 140, 44, bg_surface=back_panel)
    guide_next_btn = TextButton(SCREEN_WIDTH - 320, SCREEN_HEIGHT - 90, "下一頁", font_small, 140, 44, bg_surface=back_panel)

    is_left = False
    is_right = False
    running = True
    background_scroll = 0
    is_paused = False
    pause_page = "main"
    pause_snapshot = None
    pause_click_lock = False
    death_prompt_ready = False
    death_click_lock = False
    if not draw_menu_boot_frame("載入資源…"):
        pygame.quit()
        sys.exit()
    game_audio.init_audio()
    game_audio.set_sfx_volume(sfx_volume)
    try:
        game_audio.set_bgm_volume(float(bgm_volume))
    except pygame.error:
        pass
    if not draw_menu_boot_frame():
        pygame.quit()
        sys.exit()
    for lv in range(1, MAX_LEVEL + 1):
        if not draw_menu_boot_frame(f"預載關卡 {lv}…"):
            pygame.quit()
            sys.exit()
        warm_level_csv(lv)
    resolution_options = [(1280, 720), (1366, 768), (1440, 810), (1600, 900), (1920, 1080)]
    selected_resolution = init_res
    menu_page = "main"
    guide_page_idx = 0
    menu_click_lock = False
    level_preload_queue: list[int] = []

    def reset_area_drag():
        nonlocal area_drag_target, area_fling_mouse_end_mx, area_fling_mouse_end_my
        area_drag_target = None
        area_fling_mouse_end_mx = 0.0
        area_fling_mouse_end_my = 0.0

    def persist_settings():
        settings_io.save_settings(
            {
                "bgm_volume": float(bgm_volume),
                "sfx_volume": float(sfx_volume),
                "resolution": [int(selected_resolution[0]), int(selected_resolution[1])],
            }
        )

    def quit_game():
        nonlocal running
        persist_settings()
        game_audio.stop_bgm()
        running = False

    def align_camera_to_world_x(world_x: int) -> None:
        """將鏡頭對準世界 X：捲動背景並把地圖與玩家一起換成螢幕座標系。

        關卡載入時玩家仍在「世界 X」（CSV 像素）；走動捲屏時則維持在螢幕上。
        此處須與 player.move 的捲動一致：shift_world 後玩家也要減去 delta。
        """
        nonlocal background_scroll
        scroll_max = world.scroll_max_px(SCREEN_WIDTH)
        if scroll_max <= 0:
            background_scroll = 0
            return
        target = max(0, int(world_x) - SCROLL_THRESH)
        desired = min(target, scroll_max)
        delta = desired - background_scroll
        if delta != 0:
            shift_world(-delta)
            player.rect.x -= delta
        background_scroll = desired

    def align_camera_to_player():
        """開局／換關／重載後，讓玩家出現在螢幕上對應捲動位置。"""
        align_camera_to_world_x(player.rect.centerx)

    def align_camera_center_player() -> None:
        """壓扁時：玩家維持在畫面水平中央。"""
        if world is None or player is None:
            return
        scroll_max = world.scroll_max_px(SCREEN_WIDTH)
        desired = int(player.rect.centerx) - SCREEN_WIDTH // 2
        desired = max(0, min(desired, scroll_max))
        delta = desired - background_scroll
        if delta != 0:
            shift_world(-delta)
            player.rect.x -= delta
        background_scroll = desired

    def reset_player_crush_state() -> None:
        nonlocal player_is_flattened, player_crush_kill_at_ms
        player_is_flattened = False
        player_crush_kill_at_ms = 0

    def underwater_ambient_visible() -> bool:
        view = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        for deco in decoration_group:
            if not isinstance(deco, KenneyVisualTile):
                continue
            if deco.source_gid not in UNDERWATER_AMBIENT_GIDS:
                continue
            if view.colliderect(deco.rect):
                return True
        return False

    def respawn_player_after_death():
        nonlocal state, death_prompt_ready, death_click_lock, is_left, is_right
        reload_current_level()
        death_prompt_ready = False
        death_click_lock = False
        death_fade.reset()
        state = GameState.PLAYING
        is_left = is_right = False

    def normalize_player_for_level():
        cfg = get_level_mode_config(level)
        player.heal_sigmoid_active = False
        player.integral_only_lock = False
        if not cfg.mode_allowed(player.game_mode):
            if cfg.allow_brush_b:
                player.game_mode = PlayerMode.BRUSH
            else:
                player.game_mode = PlayerMode.FUNCTION
        elif cfg.allow_brush_b and level == 2:
            player.game_mode = PlayerMode.BRUSH
        controller.force_idle()
        brush_manager.end_stroke()
        reset_area_drag()

    def switch_mode(new_mode: PlayerMode):
        nonlocal player
        if getattr(player, "integral_only_lock", False) and new_mode != PlayerMode.INTEGRAL_BLOCK:
            return
        cfg = get_level_mode_config(level)
        allowed = cfg.mode_allowed(new_mode)
        if (
            new_mode == PlayerMode.DERIVATIVE_BLOCK
            and derivative_requires_world_unlock(level)
            and not getattr(player, "derivative_round_unlocked", False)
        ):
            return
        if (
            new_mode == PlayerMode.DERIVATIVE_BLOCK
            and derivative_requires_world_unlock(level)
        ):
            allowed = True
        if not allowed:
            return
        now_ms = pygame.time.get_ticks()
        if player.game_mode == new_mode:
            return
        if not mode_cd.can_use(new_mode, now_ms):
            return
        mode_cd.on_leave(player.game_mode, now_ms)
        controller.force_idle()
        brush_manager.end_stroke()
        reset_area_drag()
        player.game_mode = new_mode

    def apply_resolution(res):
        nonlocal window, display_w, display_h, scale, view_w, view_h, view_x, view_y, selected_resolution
        selected_resolution = tuple(res)
        window = pygame.display.set_mode(selected_resolution)
        display_w, display_h = window.get_size()
        scale = min(display_w / SCREEN_WIDTH, display_h / SCREEN_HEIGHT)
        view_w = int(SCREEN_WIDTH * scale)
        view_h = int(SCREEN_HEIGHT * scale)
        view_x = (display_w - view_w) // 2
        view_y = (display_h - view_h) // 2

    def mouse_to_game(pos):
        mx, my = pos
        gx = (mx - view_x) / scale
        gy = (my - view_y) / scale
        gx = max(0, min(SCREEN_WIDTH - 1, gx))
        gy = max(0, min(SCREEN_HEIGHT - 1, gy))
        return int(gx), int(gy)

    def game_mouse_pos():
        return mouse_to_game(pygame.mouse.get_pos())

    def game_to_window(gx, gy):
        """邏輯座標 → 視窗像素（供 clamp 游標）；gx,gy 先夾在邏輯螢幕內。"""
        gx = max(0.0, min(float(SCREEN_WIDTH - 1), float(gx)))
        gy = max(0.0, min(float(SCREEN_HEIGHT - 1), float(gy)))
        wx = int(round(view_x + gx * scale))
        wy = int(round(view_y + gy * scale))
        dw, dh = window.get_size()
        return max(0, min(dw - 1, wx)), max(0, min(dh - 1, wy))

    def sigma_upper_by_hold(now_ms: int) -> float:
        if sigma_mouse_down_ms is None:
            return 0.0
        elapsed = max(0, now_ms - sigma_mouse_down_ms)
        upper = (elapsed // SIGMA_CHARGE_STEP_MS) * SIGMA_CHARGE_STEP_VALUE
        return min(SIGMA_CHARGE_MAX, float(upper))

    def shift_world(dx: int):
        if dx == 0:
            return
        for _img, rect in world._wall_obstacles:
            rect.x += dx
        for entry in world._animated_wall_entries:
            entry["wx"] += dx
            entry["rect"].x += dx
        for sp in world._spike_obstacles:
            sp["rect"].x += dx
        for _img, switch_rect in world._spike_switch_tiles:
            switch_rect.x += dx
        if world.respawn_point is not None:
            world.respawn_point = (world.respawn_point[0] + dx, world.respawn_point[1])
        from .projectile import MathProjectile

        for g in (enemy_group, enemy_bullet_group, projectile_group, numeric_group,
                  derivative_group, integral_group, square_group, sqrt_group, area_group,
                  water_group, decoration_group, exit_group, health_box_group,
                  heart_group, key_pickup_group):
            for s in g:
                if isinstance(s, MathProjectile):
                    s.origin = (s.origin[0] + dx, s.origin[1])
                    s.rect.x += dx
                elif isinstance(s, KenneyVisualTile):
                    s.world_x += dx
                    s.rect.x += dx
                elif hasattr(s, "base_rect"):
                    s.base_rect.x += dx
                    if hasattr(s, "shape_points") and s.shape_points:
                        s.shape_points = [(x + dx, y) for x, y in s.shape_points]
                    sp = getattr(s, "source_points", None)
                    if sp:
                        s.source_points = [(float(x) + dx, float(y)) for x, y in sp]
                    if hasattr(s, "motion_path") and s.motion_path:
                        s.motion_path = [(x + dx, y) for x, y in s.motion_path]
                    s.rect.topleft = s.base_rect.topleft
                else:
                    s.rect.x += dx
        for stroke in brush_manager.strokes:
            stroke.points = [(px + dx, py) for px, py in stroke.points]

    def reload_current_level():
        nonlocal world, player, health_bar, controller, last_spike_damage_ms, background_scroll
        background_scroll = 0
        world, player = init_level(
            level,
            projectile_group,
            enemy_bullet_group,
            enemy_group,
            water_group,
            decoration_group,
            exit_group,
            health_box_group,
            heart_group,
            key_pickup_group,
            derivative_group,
            integral_group,
            square_group,
            sqrt_group,
            area_group,
            numeric_group,
            brush_manager,
        )
        reset_area_drag()
        health_bar = HealthBar(10, 10, player.max_health)
        controller = EquationController(player, projectile_group)
        sigma_schedule.clear()
        game_audio.stop_all_sfx()
        last_spike_damage_ms = 0
        normalize_player_for_level()
        reset_player_crush_state()
        align_camera_to_player()

    def begin_playing_at(selected_level: int):
        nonlocal world, player, health_bar, controller, last_spike_damage_ms, level, state
        nonlocal is_opening, is_left, is_right, menu_page, menu_click_lock, background_scroll
        level = int(selected_level)
        background_scroll = 0
        if not draw_menu_boot_frame(f"載入關卡 {level}…"):
            pygame.quit()
            sys.exit()
        warm_level_csv(level)
        world, player = init_level(
            level,
            projectile_group,
            enemy_bullet_group,
            enemy_group,
            water_group,
            decoration_group,
            exit_group,
            health_box_group,
            heart_group,
            key_pickup_group,
            derivative_group,
            integral_group,
            square_group,
            sqrt_group,
            area_group,
            numeric_group,
            brush_manager,
        )
        reset_area_drag()
        health_bar = HealthBar(10, 10, player.max_health)
        controller = EquationController(player, projectile_group)
        sigma_schedule.clear()
        game_audio.stop_all_sfx()
        last_spike_damage_ms = 0
        normalize_player_for_level()
        state = GameState.PLAYING
        game_audio.start_bgm_loop(bgm_volume)
        is_opening = True
        opening_fade.reset()
        is_left = is_right = False
        menu_page = "main"
        menu_click_lock = True
        reset_player_crush_state()
        align_camera_to_player()

    while running:
        clock.tick(FPS)
        if state == GameState.PLAYING and not is_paused:
            pygame.mouse.set_visible(False)
        else:
            pygame.mouse.set_visible(True)

        if state != GameState.PLAYING:
            screen.fill(SKY)
        now_ms = pygame.time.get_ticks()

        if state == GameState.MENU:
            mpos = game_mouse_pos()
            pressed = pygame.mouse.get_pressed()[0]
            can_click = pressed and not menu_click_lock
            if not pressed:
                menu_click_lock = False
            guide_pages = [
                (
                    "1 函數圖形 (FUNCTION)",
                    [
                        "按住 1 進入瞄準，放開後發射數學彈。",
                        "0~3 次方由微分/積分塊碰自己調整（-1 / +1）。",
                        "0 次方只觸發啵聲請求，不會產生子彈。",
                        "1 次方是直線彈道，朝滑鼠方向飛行。",
                        "2 次方是拋物線，滑鼠位置作為頂點。",
                        "3 次方目前為 TODO，會顯示提示訊息。",
                    ],
                ),
                (
                    "2 微分塊 (DERIVATIVE_BLOCK)",
                    [
                        "模式 2 可在左側可放置區放置 d/dx 塊。",
                        "碰到自己：次方 -1；碰敵人：讓敵人定身。",
                        "碰敵彈：微分塊與敵彈互相消失。",
                        "碰積分塊：兩種塊互消。",
                        "碰畫筆：該色整筆刪除；碰靜止面積可還原成線。",
                        "離開模式後有 1 秒冷卻才可再進入。",
                    ],
                ),
                (
                    "3 積分模式 (INTEGRAL_BLOCK)",
                    [
                        "模式 3 左鍵有優先序：先作用敵彈/畫筆，最後才放積分塊。",
                        "滾輪可切換 ∫x 與 ∫y 軸向。",
                        "對敵彈：可做 ∫x/∫y 加長處理。",
                        "對畫筆：可延長、閉環成面積、或轉為面積互動。",
                        "積分塊碰自己：次方 +1；碰微分塊：互消。",
                        "積分塊碰我方子彈：放大增傷且獲得穿敵效果。",
                    ],
                ),
                (
                    "4 Sigmoid (SIGMOID)",
                    [
                        "模式 4 開啟時，游標附近持續嘗試轉化敵彈。",
                        "成功後敵彈變成綠色治療彈。",
                        "治療量依 sigmoid 公式由原傷害換算。",
                        "適合在彈幕密集時邊走位邊回復血量。",
                        "離開模式後有 10 秒冷卻才可再進入。",
                    ],
                ),
                (
                    "5 Sigma (SIGMA)",
                    [
                        "模式 5 按住左鍵蓄力，每 500ms 上界 +1（最高 10）。",
                        "放開後會排程發射 0~n 的數字彈序列。",
                        "每發之間有固定間隔，屬於連續輸出模式。",
                        "若最終 n=0，會觸發 10 發 0 傷害彩蛋連射。",
                        "離開模式後有 15 秒冷卻才可再進入。",
                    ],
                ),
                (
                    "B 畫筆 (BRUSH)",
                    [
                        "按 B 可在左側可放置區開始繪製筆觸。",
                        "全場最多 5 色筆觸，總長度上限 1800px。",
                        "形成閉環時會自動轉成面積體；點一下（短筆觸）變小圓面積。",
                        "微分/積分塊碰到筆觸時，會整色整筆清除。",
                        "積分互動可把非閉環筆觸轉成可碰撞面積。",
                    ],
                ),
                (
                    "雙 B 面積拖曳 (AREA_MOVE)",
                    [
                        "450ms 內連按兩次 B 進入面積拖曳模式。",
                        "左鍵點靜止面積後按住拖移位置。",
                        "放開左鍵結束拖移：若游標與上一幀位置位移夠大，會沿該方向甩出；否則面積留在原地。",
                        "滑行撞到敵人會造成傷害。",
                        "拖動時會做地圖阻擋解析；若拖動會讓玩家出畫面則還原。",
                    ],
                ),
            ]
            guide_title, guide_lines = guide_pages[guide_page_idx]
            guide_page_text = f"{guide_page_idx + 1}/{len(guide_pages)}"
            if menu_page == "main":
                title = font_large.render("方程式戰士", True, WHITE)
                screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 130)))
                start_btn.draw(screen)
                guide_btn.draw(screen)
                settings_btn.draw(screen)
                exit_btn.draw(screen)
                if can_click and start_btn.rect.collidepoint(mpos):
                    menu_page = "level_select"
                    level_preload_queue.clear()
                    level_preload_queue.extend(
                        lv for lv in range(1, MAX_LEVEL + 1) if lv not in _LEVEL_CSV_WARMED
                    )
                    menu_click_lock = True
                elif can_click and settings_btn.rect.collidepoint(mpos):
                    menu_page = "settings"
                    menu_click_lock = True
                elif can_click and guide_btn.rect.collidepoint(mpos):
                    guide_page_idx = 0
                    menu_page = "guide"
                    menu_click_lock = True
                elif can_click and exit_btn.rect.collidepoint(mpos):
                    quit_game()
            elif menu_page == "level_select":
                if level_preload_queue:
                    warm_level_csv(level_preload_queue.pop(0))
                title = font_large.render("方程式戰士", True, WHITE)
                screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 120)))
                sub = font_med.render("選擇關卡", True, WHITE)
                screen.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 175)))
                level_pick_btn_1.draw(screen)
                level_pick_btn_2.draw(screen)
                level_pick_btn_3.draw(screen)
                level_select_back_btn.draw(screen)
                if can_click and level_pick_btn_1.rect.collidepoint(mpos):
                    begin_playing_at(1)
                elif can_click and level_pick_btn_2.rect.collidepoint(mpos):
                    begin_playing_at(2)
                elif can_click and level_pick_btn_3.rect.collidepoint(mpos):
                    begin_playing_at(3)
                elif can_click and level_select_back_btn.rect.collidepoint(mpos):
                    menu_page = "main"
                    menu_click_lock = True
            elif menu_page == "settings":
                base_title = font_large.render("方程式戰士", True, WHITE)
                screen.blit(base_title, base_title.get_rect(center=(SCREEN_WIDTH // 2, 130)))
                start_btn.draw(screen)
                settings_btn.draw(screen)
                exit_btn.draw(screen)
                small = pygame.transform.smoothscale(screen, (max(1, SCREEN_WIDTH // 8), max(1, SCREEN_HEIGHT // 8)))
                blur = pygame.transform.smoothscale(small, (SCREEN_WIDTH, SCREEN_HEIGHT))
                screen.blit(blur, (0, 0))
                shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 120))
                screen.blit(shade, (0, 0))
                title = font_large.render("設置", True, WHITE)
                screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 100)))
                back_btn.draw(screen)
                if can_click and back_btn.rect.collidepoint(mpos):
                    menu_page = "main"
                    menu_click_lock = True
                sub1 = font_med.render("解析度", True, WHITE)
                screen.blit(sub1, (140, 170))
                y0 = 220
                for i, (rw, rh) in enumerate(resolution_options):
                    rect = pygame.Rect(140, y0 + i * 62, 420, 48)
                    active = selected_resolution == (rw, rh)
                    color = (140, 220, 60) if active else (40, 40, 40)
                    pygame.draw.rect(screen, color, rect, border_radius=18)
                    pygame.draw.rect(screen, WHITE, rect, 2, border_radius=18)
                    label = font_med.render(f"{rw}x{rh}", True, BLACK if active else WHITE)
                    screen.blit(label, label.get_rect(center=rect.center))
                    if can_click and rect.collidepoint(mpos):
                        apply_resolution((rw, rh))
                        menu_click_lock = True
                sub2 = font_med.render("聲音設置", True, WHITE)
                screen.blit(sub2, (760, 170))
                bgm_bar = pygame.Rect(760, 240, 520, 14)
                sfx_bar = pygame.Rect(760, 340, 520, 14)
                for bar, val, text in ((bgm_bar, bgm_volume, "BGM"), (sfx_bar, sfx_volume, "音效")):
                    pygame.draw.rect(screen, (180, 180, 180), bar, border_radius=8)
                    fill = pygame.Rect(bar.x, bar.y, int(bar.w * val), bar.h)
                    pygame.draw.rect(screen, (120, 220, 120), fill, border_radius=8)
                    knob_x = bar.x + int(bar.w * val)
                    pygame.draw.circle(screen, WHITE, (knob_x, bar.centery), 12)
                    t = font_small.render(f"{text}: {int(val * 100)}%", True, WHITE)
                    screen.blit(t, (bar.x, bar.y - 30))
                if pressed:
                    mx, my = mpos
                    if abs(my - bgm_bar.centery) <= 16 and bgm_bar.x <= mx <= bgm_bar.right:
                        bgm_volume = (mx - bgm_bar.x) / bgm_bar.w
                    if abs(my - sfx_bar.centery) <= 16 and sfx_bar.x <= mx <= sfx_bar.right:
                        sfx_volume = (mx - sfx_bar.x) / sfx_bar.w
                        game_audio.set_sfx_volume(sfx_volume)
                    try:
                        game_audio.set_bgm_volume(float(bgm_volume))
                    except pygame.error:
                        pass
            else:
                base_title = font_large.render("方程式戰士", True, WHITE)
                screen.blit(base_title, base_title.get_rect(center=(SCREEN_WIDTH // 2, 130)))
                start_btn.draw(screen)
                guide_btn.draw(screen)
                settings_btn.draw(screen)
                exit_btn.draw(screen)
                small = pygame.transform.smoothscale(screen, (max(1, SCREEN_WIDTH // 8), max(1, SCREEN_HEIGHT // 8)))
                blur = pygame.transform.smoothscale(small, (SCREEN_WIDTH, SCREEN_HEIGHT))
                screen.blit(blur, (0, 0))
                shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 120))
                screen.blit(shade, (0, 0))
                title = font_large.render("玩法介紹", True, WHITE)
                screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 88)))
                page_title = font_med.render(guide_title, True, WHITE)
                screen.blit(page_title, page_title.get_rect(center=(SCREEN_WIDTH // 2, 140)))
                page_idx_img = font_small.render(guide_page_text, True, WHITE)
                screen.blit(page_idx_img, page_idx_img.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 68)))
                back_btn.draw(screen)
                guide_prev_btn.draw(screen)
                guide_next_btn.draw(screen)
                if can_click and back_btn.rect.collidepoint(mpos):
                    menu_page = "main"
                    menu_click_lock = True
                elif can_click and guide_prev_btn.rect.collidepoint(mpos):
                    guide_page_idx = (guide_page_idx - 1) % len(guide_pages)
                    menu_click_lock = True
                elif can_click and guide_next_btn.rect.collidepoint(mpos):
                    guide_page_idx = (guide_page_idx + 1) % len(guide_pages)
                    menu_click_lock = True
                for idx, msg in enumerate(guide_lines):
                    txt = font_small.render(f"- {msg}", True, WHITE)
                    screen.blit(txt, txt.get_rect(center=(SCREEN_WIDTH // 2, 210 + idx * 48)))

        elif state == GameState.PLAYING and is_paused:
            game_audio.set_underwater_bubbles_active(False)
            if pause_snapshot is None:
                pause_snapshot = screen.copy()
            small = pygame.transform.smoothscale(pause_snapshot, (max(1, SCREEN_WIDTH // 8), max(1, SCREEN_HEIGHT // 8)))
            blur = pygame.transform.smoothscale(small, (SCREEN_WIDTH, SCREEN_HEIGHT))
            screen.blit(blur, (0, 0))
            shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 120))
            screen.blit(shade, (0, 0))

            pressed = pygame.mouse.get_pressed()[0]
            mpos = game_mouse_pos()
            can_click = pressed and not pause_click_lock
            if not pressed:
                pause_click_lock = False

            if pause_page == "main":
                title = font_large.render("暫停", True, WHITE)
                screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 170)))
                back_btn.draw(screen)
                pause_continue_btn.draw(screen)
                pause_settings_btn.draw(screen)
                pause_exit_btn.draw(screen)

                if can_click and (pause_continue_btn.rect.collidepoint(mpos) or back_btn.rect.collidepoint(mpos)):
                    is_paused = False
                    pause_snapshot = None
                    pause_click_lock = True
                elif can_click and pause_settings_btn.rect.collidepoint(mpos):
                    pause_page = "settings"
                    pause_click_lock = True
                elif can_click and pause_exit_btn.rect.collidepoint(mpos):
                    is_paused = False
                    pause_snapshot = None
                    state = GameState.MENU
                    game_audio.stop_bgm()
                    persist_settings()
                    pause_click_lock = True
            else:
                title = font_large.render("設定", True, WHITE)
                screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 100)))
                back_btn.draw(screen)
                if can_click and back_btn.rect.collidepoint(mpos):
                    pause_page = "main"
                    pause_click_lock = True

                sub1 = font_med.render("解析度", True, WHITE)
                screen.blit(sub1, (140, 170))
                y0 = 220
                for i, (rw, rh) in enumerate(resolution_options):
                    rect = pygame.Rect(140, y0 + i * 62, 420, 48)
                    active = selected_resolution == (rw, rh)
                    color = (140, 220, 60) if active else (40, 40, 40)
                    pygame.draw.rect(screen, color, rect, border_radius=18)
                    pygame.draw.rect(screen, WHITE, rect, 2, border_radius=18)
                    label = font_med.render(f"{rw}x{rh}", True, BLACK if active else WHITE)
                    screen.blit(label, label.get_rect(center=rect.center))
                    if can_click and rect.collidepoint(mpos):
                        apply_resolution((rw, rh))
                        pause_click_lock = True

                sub2 = font_med.render("聲音設置", True, WHITE)
                screen.blit(sub2, (760, 170))
                bgm_bar = pygame.Rect(760, 240, 520, 14)
                sfx_bar = pygame.Rect(760, 340, 520, 14)
                for bar, val, text in ((bgm_bar, bgm_volume, "BGM"), (sfx_bar, sfx_volume, "音效")):
                    pygame.draw.rect(screen, (180, 180, 180), bar, border_radius=8)
                    fill = pygame.Rect(bar.x, bar.y, int(bar.w * val), bar.h)
                    pygame.draw.rect(screen, (120, 220, 120), fill, border_radius=8)
                    knob_x = bar.x + int(bar.w * val)
                    pygame.draw.circle(screen, WHITE, (knob_x, bar.centery), 12)
                    t = font_small.render(f"{text}: {int(val * 100)}%", True, WHITE)
                    screen.blit(t, (bar.x, bar.y - 30))
                if pressed:
                    mx, my = mpos
                    if abs(my - bgm_bar.centery) <= 16 and bgm_bar.x <= mx <= bgm_bar.right:
                        bgm_volume = (mx - bgm_bar.x) / bgm_bar.w
                    if abs(my - sfx_bar.centery) <= 16 and sfx_bar.x <= mx <= sfx_bar.right:
                        sfx_volume = (mx - sfx_bar.x) / sfx_bar.w
                        game_audio.set_sfx_volume(sfx_volume)
                    try:
                        game_audio.set_bgm_volume(float(bgm_volume))
                    except pygame.error:
                        pass

        elif state == GameState.PLAYING:
            if player_is_flattened:
                align_camera_center_player()
                is_left = is_right = False
            draw_parallax_background(screen, background_scroll)
            world.update_animated_tiles(now_ms)
            world.draw_obstacles(screen)
            world.draw_spikes(screen)
            world.draw_spike_switches(screen)
            water_group.draw(screen)
            for deco in decoration_group:
                if isinstance(deco, KenneyVisualTile):
                    deco.update_visual(now_ms)
            decoration_group.draw(screen)
            exit_group.draw(screen)
            health_box_group.draw(screen)
            heart_group.draw(screen)
            key_pickup_group.draw(screen)
            if player.is_alive:
                brush_manager.set_zone_center_x(player.rect.centerx)
            if player.game_mode in (
                PlayerMode.DERIVATIVE_BLOCK,
                PlayerMode.INTEGRAL_BLOCK,
                PlayerMode.SQUARE_BLOCK,
                PlayerMode.SQRT_BLOCK,
                PlayerMode.BRUSH,
            ):
                _zx, _zy, zone_w, zone_h = placement_zone_around_player(
                    player.rect.centerx, SCREEN_WIDTH, SCREEN_HEIGHT,
                )
                zone_overlay = pygame.Surface((zone_w, zone_h), pygame.SRCALPHA)
                zone_overlay.fill((255, 255, 255, 35))
                screen.blit(zone_overlay, (_zx, _zy))
                pygame.draw.rect(screen, (255, 255, 255), (_zx, _zy, zone_w, zone_h), 2)

            if player.is_alive:
                if player_is_flattened:
                    is_left = is_right = False
                if player_crush_kill_at_ms and now_ms >= player_crush_kill_at_ms:
                    player.health = 0.0
                    player_crush_kill_at_ms = 0
                for enemy in list(enemy_group):
                    if enemy_special.try_exp_flyer_player_touch(player, enemy):
                        game_audio.play_power_up(at_rect=player.rect)
                        player.integral_only_lock = True
                        player.game_mode = PlayerMode.INTEGRAL_BLOCK
                        Player.show_center_notice(
                            player,
                            "你被詛咒了！只能使用積分模式",
                            now_ms,
                            duration_ms=3000,
                        )
                        controller.force_idle()
                        brush_manager.end_stroke()
                        reset_area_drag()
                        break
                screen_scroll = player.move(
                    is_left,
                    is_right,
                    world,
                    area_group,
                    enemy_group=enemy_group,
                    background_scroll=background_scroll,
                )
                if screen_scroll:
                    shift_world(screen_scroll)
                    background_scroll -= screen_scroll
                scroll_max = world.scroll_max_px(SCREEN_WIDTH)
                if background_scroll > scroll_max:
                    excess = background_scroll - scroll_max
                    shift_world(excess)
                    player.rect.x -= excess
                    background_scroll = scroll_max
                elif background_scroll < 0:
                    shift_world(background_scroll)
                    player.rect.x -= background_scroll
                    background_scroll = 0
                player.tick_cast_hold_release()
                if player.hurt_animation_busy():
                    player.update_action(ActionTypes.HURT)
                    player.is_x_flip = player.facing == -1
                elif player.cast_animation_busy():
                    player.update_action(ActionTypes.CAST)
                    player.is_x_flip = player.facing == -1
                elif player.is_in_air:
                    player.update_action(ActionTypes.JUMP)
                elif is_left or is_right:
                    player.update_action(ActionTypes.RUN)
                else:
                    player.update_action(ActionTypes.IDLE)
            else:
                if player.action != ActionTypes.DEATH:
                    player.update_action(ActionTypes.DEATH)

            for deco in decoration_group:
                if not isinstance(deco, KenneyVisualTile):
                    continue
                if deco.source_gid not in DERIVATIVE_UNLOCK_GIDS:
                    continue
                if player.rect.colliderect(deco.rect):
                    if not player.derivative_round_unlocked:
                        player.derivative_round_unlocked = True
                        if derivative_requires_world_unlock(level):
                            dkey = derivative_switch_key(level)
                            dname = pygame.key.name(dkey).upper() if dkey is not None else "?"
                            Player.show_center_notice(
                                player,
                                f"微分模式已解鎖！按 {dname}",
                                now_ms,
                                duration_ms=3000,
                            )
                    deco.kill()

            for enemy in enemy_group:
                if getattr(enemy, "pending_crush_player", False):
                    zone = enemy.rect.inflate(TILE_SIZE * 2, TILE_SIZE)
                    if player.rect.colliderect(zone):
                        player_is_flattened = True
                        player_crush_kill_at_ms = now_ms + 2500
                        controller.force_idle()
                        brush_manager.end_stroke()
                        reset_area_drag()
                    enemy.pending_crush_player = False
                enemy._nearby_derivative_blocks = tuple(derivative_group.sprites())
                enemy._nearby_integral_blocks = tuple(integral_group.sprites())
                enemy.ai(player, world, enemy_bullet_group, area_group, enemy_group)
                enemy.update_cooldowns()
                enemy.check_alive()
                if (
                    enemy.drops_key_on_death
                    and not enemy._key_drop_spawned
                    and not enemy.is_alive
                ):
                    key_pickup_group.add(
                        KeyPickup(
                            enemy.rect.centerx - TILE_SIZE // 2,
                            enemy.rect.centery - TILE_SIZE // 2,
                        )
                    )
                    enemy._key_drop_spawned = True

            for enemy in list(enemy_group):
                if not enemy.is_alive:
                    if enemy.frame_index >= len(enemy.animation_list[ActionTypes.DEATH]) - 1:
                        enemy.kill()

            for b in enemy_bullet_group:
                b.update(world, player, area_group)

            controller.update(mouse_pos=game_mouse_pos())
            if getattr(player, "pop_sound_requests", 0) > 0:
                player.pop_sound_requests = 0
                if not game_audio.is_bubble_repeat_active():
                    game_audio.play_bubble_pop(at_rect=player.rect)

            for proj in projectile_group:
                proj.update(world, enemy_group, player, area_group)

            for nb in numeric_group:
                nb.update(world, enemy_group, area_group)

            for d in list(derivative_group):
                if d.alive():
                    d.update_physics(world, derivative_group, integral_group)
            for i in list(integral_group):
                if i.alive():
                    i.update_physics(world, integral_group, derivative_group)
            for s in list(square_group):
                if s.alive():
                    s.update_physics(world, square_group, sqrt_group)
            for r in list(sqrt_group):
                if r.alive():
                    r.update_physics(world, sqrt_group, square_group)

            for d in list(derivative_group):
                resolve_calculus_block_interactions(
                    d,
                    player,
                    enemy_group,
                    enemy_bullet_group,
                    brush_manager,
                    area_group,
                    world,
                    projectile_group,
                )
            for i in list(integral_group):
                resolve_calculus_block_interactions(
                    i,
                    player,
                    enemy_group,
                    enemy_bullet_group,
                    brush_manager,
                    area_group,
                    world,
                    projectile_group,
                )
            for s in list(square_group):
                resolve_algebra_block_interactions(s, player, projectile_group, enemy_group)
            for r in list(sqrt_group):
                resolve_algebra_block_interactions(r, player, projectile_group, enemy_group)

            ref_r = max(1.0, float(player.rect.width) * 2.0)
            for center, ci in brush_manager.drain_tap_circles():
                for body in build_area_bodies_from_circle(
                    center,
                    radius=max(4.0, player.rect.width * 0.5),
                    world=world,
                    source_color_index=ci,
                    damage_ref_radius=ref_r,
                ):
                    area_group.add(body)
            for pts, ci in brush_manager.drain_closed_loop_areas():
                if len(pts) >= 3:
                    for body in build_area_bodies_from_polygon(
                        pts,
                        world,
                        source_points=pts,
                        source_color_index=ci,
                        damage_ref_radius=ref_r,
                    ):
                        area_group.add(body)

            for ar in list(area_group):
                ar.update(world, enemy_group, player)

            if player.game_mode == PlayerMode.AREA_MOVE and area_drag_target is not None:
                tgt = area_drag_target
                if not tgt.alive():
                    reset_area_drag()
                else:
                    area_drag_fling_anchor_mx = area_fling_mouse_end_mx
                    area_drag_fling_anchor_my = area_fling_mouse_end_my
                    mx, my = game_mouse_pos()
                    if pygame.mouse.get_pressed()[0]:
                        pre_dx = area_drag_dx
                        pre_dy = area_drag_dy
                        tcx = int(mx - pre_dx)
                        tcy = int(my - pre_dy)
                        dx = tcx - tgt.rect.centerx
                        dy = tcy - tgt.rect.centery
                        old_cx = tgt.rect.centerx
                        old_cy = tgt.rect.centery
                        snap = tgt.snapshot_pose()
                        tgt.try_offset_resolve_obstacles(dx, dy, world)
                        dcx = tgt.rect.centerx - old_cx
                        dcy = tgt.rect.centery - old_cy
                        if (dcx != 0 or dcy != 0) and tgt.intersects_rect(player.rect):
                            pr = player.rect.move(dcx, dcy)
                            if (
                                pr.top < 0
                                or pr.bottom > SCREEN_HEIGHT
                                or pr.left < 0
                                or pr.right > SCREEN_WIDTH
                            ):
                                tgt.restore_pose(snap)
                        acx = tgt.rect.centerx
                        acy = tgt.rect.centery
                        mx_clamped, my_clamped = mx, my
                        if acx != tcx:
                            mx_clamped = int(max(0, min(SCREEN_WIDTH - 1, round(acx + pre_dx))))
                        if acy != tcy:
                            my_clamped = int(max(0, min(SCREEN_HEIGHT - 1, round(acy + pre_dy))))
                        if mx_clamped != mx or my_clamped != my:
                            pygame.mouse.set_pos(game_to_window(mx_clamped, my_clamped))
                        area_drag_dx = mx_clamped - acx
                        area_drag_dy = my_clamped - acy
                    mx2, my2 = game_mouse_pos()
                    area_fling_mouse_end_mx = float(mx2)
                    area_fling_mouse_end_my = float(my2)

            while sigma_schedule and sigma_schedule[0][0] <= now_ms:
                _, val = sigma_schedule.pop(0)
                mx, my = game_mouse_pos()
                px, py = player.rect.center
                dxw = mx - px
                dyw = -(my - py)
                norm = math.hypot(dxw, dyw) or 1.0
                numeric_group.add(
                    NumericProjectile((px, py), dxw / norm, dyw / norm, val),
                )
                if val != 0:
                    game_audio.play_shot(at_rect=player.rect)
            if not sigma_schedule and game_audio.is_bubble_repeat_active():
                game_audio.stop_bubble_repeat()

            if (
                get_level_mode_config(level).mode_allowed(PlayerMode.SIGMOID)
                and player.game_mode == PlayerMode.SIGMOID
            ):
                mx, my = game_mouse_pos()
                try_sigmoid_on_enemy_bullet(mx, my, enemy_bullet_group)

            if pygame.sprite.spritecollide(player, water_group, False) and player.is_alive:
                player.health = 0.0

            for box in list(health_box_group):
                box.update(player)

            for heart in list(heart_group):
                heart.update(player)

            for key_pk in list(key_pickup_group):
                key_pk.update(player)

            if player.is_alive:
                world.update_spike_flip_on_player_contact(player.rect)
                world.try_toggle_spike_switch(
                    player.rect, area_group, integral_group, derivative_group,
                )
                world.try_consume_key_for_doors(player)
                if world.spikes_extended:
                    spike_rects = world.spike_damage_rects()
                    feet = player._feet_rect_for_spike()
                    on_spike = any(feet.colliderect(sr) for sr in spike_rects)
                    if on_spike and now_ms - last_spike_damage_ms >= SPIKE_DAMAGE_INTERVAL_MS:
                        player.take_damage(player.max_health / 10.0)
                        game_audio.play_spike_hit(at_rect=player.rect)
                        last_spike_damage_ms = now_ms
                    for enemy in enemy_group:
                        if not enemy.is_alive:
                            continue
                        if not enemy.feet_on_spike_damage(world):
                            continue
                        if enemy_special.is_calc_tank_enemy(enemy):
                            enemy_special.calc_tank_kill(enemy)
                            continue
                        if now_ms - enemy._last_spike_damage_ms < SPIKE_DAMAGE_INTERVAL_MS:
                            continue
                        enemy.take_damage(max(enemy.max_health / 10.0, 1.0))
                        game_audio.play_spike_hit(at_rect=enemy.rect)
                        enemy._last_spike_damage_ms = now_ms
                        enemy.check_alive()

            if player.is_alive and pygame.sprite.spritecollide(player, exit_group, False):
                level += 1
                if level > MAX_LEVEL:
                    state = GameState.WIN
                else:
                    world, player = init_level(
                        level,
                        projectile_group,
                        enemy_bullet_group,
                        enemy_group,
                        water_group,
                        decoration_group,
                        exit_group,
                        health_box_group,
                        heart_group,
                        key_pickup_group,
                        derivative_group,
                        integral_group,
                        square_group,
                        sqrt_group,
                        area_group,
                        numeric_group,
                        brush_manager,
                    )
                    reset_area_drag()
                    health_bar = HealthBar(10, 10, player.max_health)
                    controller = EquationController(player, projectile_group)
                    sigma_schedule.clear()
                    game_audio.stop_all_sfx()
                    last_spike_damage_ms = 0
                    normalize_player_for_level()
                    is_opening = True
                    opening_fade.reset()
                    background_scroll = 0
                    is_left = is_right = False
                    align_camera_to_player()
                    continue

            player.update_animation()
            for enemy in enemy_group:
                enemy.update_animation()

            brush_manager.draw(screen)

            for enemy in enemy_group:
                enemy.draw(screen)
                if enemy.is_alive:
                    blit_enemy_head_label(screen, font_small, enemy, WHITE)
            if player_is_flattened:
                flat = player.image.copy()
                fw = max(4, int(flat.get_width()))
                fh = max(2, int(flat.get_height() * 0.22))
                flat = pygame.transform.smoothscale(flat, (fw, fh))
                fr = flat.get_rect(midbottom=player.rect.midbottom)
                screen.blit(flat, fr)
            else:
                player.draw(screen)
            if player.heal_sigmoid_active:
                s_head = font_med.render("S", True, RED)
                screen.blit(
                    s_head,
                    s_head.get_rect(midbottom=(player.rect.centerx, player.rect.top - 4)),
                )
            enemy_bullet_group.draw(screen)
            projectile_group.draw(screen)
            numeric_group.draw(screen)
            area_group.draw(screen)
            derivative_group.draw(screen)
            integral_group.draw(screen)
            square_group.draw(screen)
            sqrt_group.draw(screen)

            controller.draw_preview(screen, world)

            health_bar.draw(screen, player.health)
            screen.blit(font_small.render(f"Level {level}/{MAX_LEVEL}", True, BLACK), (10, 38))
            hp_txt = font_small.render(
                f"HP {player.health:.2f}/{player.max_health:.2f}",
                True,
                BLACK,
            )
            screen.blit(hp_txt, (10, 60))
            key_icon = surface_for_gid(GID_KEY, TILE_SIZE, fallback_rgb=(230, 200, 80))
            if key_icon is not None:
                ks = pygame.transform.smoothscale(key_icon, (22, 22))
                screen.blit(ks, (10, 78))
            screen.blit(
                font_small.render(f"鑰匙 × {player.key_count}", True, BLACK),
                (36, 80),
            )
            lvl_cfg_hud = get_level_mode_config(level)
            cd_lines = list(lvl_cfg_hud.cooldown_hud)
            hud_y = 102
            for idx, (mode, label) in enumerate(cd_lines):
                total_ms = mode_cd.total_ms(mode)
                rem_ms = mode_cd.remaining_ms(mode, now_ms)
                txt = f"{label} CD {rem_ms / 1000:.1f}s/{total_ms / 1000:.1f}s"
                locked = bool(getattr(player, "integral_only_lock", False)) and mode != PlayerMode.INTEGRAL_BLOCK
                if (
                    mode == PlayerMode.DERIVATIVE_BLOCK
                    and derivative_requires_world_unlock(level)
                    and not getattr(player, "derivative_round_unlocked", False)
                ):
                    locked = True
                if locked:
                    txt = f"{txt} ×"
                color = (200, 60, 60) if locked else BLACK
                screen.blit(font_small.render(txt, True, color), (10, hud_y + idx * 20))
            hud_y += len(cd_lines) * 20
            if (
                derivative_requires_world_unlock(level)
                and getattr(player, "derivative_round_unlocked", False)
            ):
                dkey = derivative_switch_key(level)
                dname = pygame.key.name(dkey).upper() if dkey is not None else "?"
                screen.blit(
                    font_small.render(f"微分已解鎖 [{dname}]", True, (40, 180, 80)),
                    (10, hud_y),
                )
                hud_y += 20

            controller.draw_polynomial_center_msg(screen, font_med)
            if int(getattr(player, "center_notice_until_ms", 0)) > now_ms:
                notice = font_med.render(str(player.center_notice_text), True, YELLOW)
                nr = notice.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 100))
                nb = pygame.Surface((nr.width + 24, nr.height + 10), pygame.SRCALPHA)
                nb.fill((0, 0, 0, 190))
                screen.blit(nb, (nr.x - 12, nr.y - 5))
                screen.blit(notice, nr)

            if (
                get_level_mode_config(level).mode_allowed(PlayerMode.SIGMOID)
                and player.game_mode == PlayerMode.SIGMOID
            ):
                mx, my = game_mouse_pos()
                s_txt = font_large.render("S", True, GOLD)
                screen.blit(s_txt, s_txt.get_rect(center=(mx, my)))
            elif player.game_mode == PlayerMode.SIGMA:
                mx, my = game_mouse_pos()
                sigma_txt = font_med.render("Σx", True, YELLOW)
                screen.blit(sigma_txt, sigma_txt.get_rect(center=(mx, my)))
            elif player.game_mode == PlayerMode.AREA_MOVE:
                mx, my = game_mouse_pos()
                pygame.draw.line(screen, (240, 220, 80), (mx - 14, my), (mx + 14, my), 2)
                pygame.draw.line(screen, (240, 220, 80), (mx, my - 14), (mx, my + 14), 2)
            status_rect = pygame.Rect(0, SCREEN_HEIGHT - 34, SCREEN_WIDTH, 34)
            pygame.draw.rect(screen, (20, 20, 20), status_rect)
            mode_msg = ""
            if player.game_mode == PlayerMode.FUNCTION:
                mode_msg = f"函數模式：目前次方 {player.polynomial_degree}"
            elif player.game_mode == PlayerMode.DERIVATIVE_BLOCK:
                mode_msg = (
                    f"微分模式：d/dx 塊 "
                    f"{count_player_placed_calculus(derivative_group)}/{DERIVATIVE_BLOCKS_MAX}"
                )
            elif player.game_mode == PlayerMode.INTEGRAL_BLOCK:
                mode_msg = (
                    f"積分模式：∫{player.integral_axis.value} | 積分塊 "
                    f"{count_player_placed_calculus(integral_group)}/{INTEGRAL_BLOCKS_MAX}"
                )
            elif player.game_mode == PlayerMode.SIGMOID:
                mode_msg = "S 模式：游標碰到敵彈會轉綠並變治療彈"
            elif player.game_mode == PlayerMode.SIGMA:
                upper_now = sigma_upper_by_hold(now_ms)
                mode_msg = f"Sigma：0~{int(math.floor(upper_now))}（按住左鍵蓄力）"
            elif player.game_mode == PlayerMode.BRUSH:
                remain = max(0, int(BRUSH_MAX_TOTAL_LENGTH_PX - brush_manager.total_length))
                mode_msg = f"畫筆：剩餘可畫長度 {remain}"
            elif player.game_mode == PlayerMode.AREA_MOVE:
                mode_msg = "面積拖曳：左鍵拖移；快放左鍵且位移夠大時甩出"
            elif player.game_mode == PlayerMode.SQUARE_BLOCK:
                mode_msg = f"平方模式：x² 塊 {len(square_group)}/{SQUARE_BLOCKS_MAX}"
            elif player.game_mode == PlayerMode.SQRT_BLOCK:
                mode_msg = f"根號模式：√x 塊 {len(sqrt_group)}/{SQRT_BLOCKS_MAX}"
            if player.heal_sigmoid_active:
                mode_msg = (mode_msg + "｜治療 S：攻擊回復敵人 1 HP") if mode_msg else "治療 S：攻擊回復敵人 1 HP"
            mode_img = font_small.render(mode_msg, True, WHITE)
            screen.blit(mode_img, mode_img.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 18)))

            player.check_alive()
            if not player.is_alive:
                state = GameState.DEATH
                death_fade.reset()
                death_prompt_ready = False
                death_click_lock = True
                game_audio.stop_all_sfx()
                game_audio.play_player_death(at_rect=player.rect)

            if is_opening:
                if opening_fade.fade_in(screen):
                    is_opening = False

            game_audio.set_underwater_bubbles_active(underwater_ambient_visible())
            draw_control_hint_strip(screen)
            area_dragging = (
                player.game_mode == PlayerMode.AREA_MOVE
                and area_drag_target is not None
                and pygame.mouse.get_pressed()[0]
            )
            draw_playing_cursor(
                screen,
                game_mouse_pos(),
                player.game_mode,
                area_dragging=area_dragging,
                integral_axis=getattr(player, "integral_axis", None),
            )

        elif state == GameState.DEATH:
            player.update_animation()
            game_audio.set_underwater_bubbles_active(False)
            draw_parallax_background(screen, background_scroll)
            world.draw_obstacles(screen)
            world.draw_spikes(screen)
            world.draw_spike_switches(screen)
            water_group.draw(screen)
            heart_group.draw(screen)
            for enemy in enemy_group:
                enemy.draw(screen)
            if player_is_flattened:
                flat = player.image.copy()
                fw = max(4, int(flat.get_width()))
                fh = max(2, int(flat.get_height() * 0.22))
                flat = pygame.transform.smoothscale(flat, (fw, fh))
                fr = flat.get_rect(midbottom=player.rect.midbottom)
                screen.blit(flat, fr)
            else:
                player.draw(screen)
            health_bar.draw(screen, 0)
            done = death_fade.fade_out(screen)
            if done:
                death_prompt_ready = True
                msg = font_large.render("YOU DIED", True, WHITE)
                screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 120)))
                revive_btn.draw(screen)
                pressed = pygame.mouse.get_pressed()[0]
                mpos = game_mouse_pos()
                can_click = pressed and not death_click_lock
                if not pressed:
                    death_click_lock = False
                if can_click and revive_btn.rect.collidepoint(mpos):
                    respawn_player_after_death()

        elif state == GameState.WIN:
            win_text = font_large.render("YOU WIN!", True, GOLD)
            screen.blit(win_text, win_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50)))
            restart_btn.draw(screen)
            if restart_btn.is_click(mouse_pos=game_mouse_pos(), pressed=pygame.mouse.get_pressed()[0]):
                game_audio.stop_bgm()
                persist_settings()
                state = GameState.MENU

        for event in pygame.event.get():
            if event.type == game_audio.BGM_END_EVENT:
                game_audio.handle_bgm_end_event()
            if event.type == pygame.QUIT:
                quit_game()
            if state == GameState.DEATH and death_prompt_ready:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = game_mouse_pos()
                    if revive_btn.rect.collidepoint(mx, my):
                        respawn_player_after_death()
            if state == GameState.MENU:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if menu_page in ("settings", "guide", "level_select"):
                        menu_page = "main"
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    if menu_page in ("settings", "guide", "level_select"):
                        menu_page = "main"
            if state == GameState.PLAYING and player.is_alive:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    reload_current_level()
                    is_opening = True
                    opening_fade.reset()
                    is_left = is_right = False
                    if is_paused:
                        is_paused = False
                        pause_snapshot = None
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if is_paused:
                        is_paused = False
                        pause_snapshot = None
                    else:
                        is_paused = True
                        game_audio.stop_all_sfx()
                        pause_page = "main"
                        pause_snapshot = screen.copy()
                        is_left = is_right = False
                        brush_manager.end_stroke()
                        reset_area_drag()
                    continue
                if is_paused:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                        if pause_page == "settings":
                            pause_page = "main"
                        else:
                            is_paused = False
                            pause_snapshot = None
                    continue
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_a:
                        is_left = True
                    elif event.key == pygame.K_d:
                        is_right = True
                    elif event.key == pygame.K_w:
                        if not player_is_flattened and not player.is_in_air:
                            player.is_jump = True
                    else:
                        lvl_cfg = get_level_mode_config(level)
                        if getattr(player, "integral_only_lock", False):
                            if event.key in lvl_cfg.key_to_mode:
                                new_mode = lvl_cfg.key_to_mode[event.key]
                                if new_mode == PlayerMode.INTEGRAL_BLOCK:
                                    switch_mode(new_mode)
                        elif (
                            derivative_requires_world_unlock(level)
                            and getattr(player, "derivative_round_unlocked", False)
                            and event.key == derivative_switch_key(level)
                        ):
                            switch_mode(PlayerMode.DERIVATIVE_BLOCK)
                        elif event.key in lvl_cfg.key_to_mode:
                            new_mode = lvl_cfg.key_to_mode[event.key]
                            switch_mode(new_mode)
                            if new_mode == PlayerMode.FUNCTION:
                                controller.on_keydown(event.key)
                        elif (
                            lvl_cfg.toggle_heal_sigmoid_key is not None
                            and event.key == lvl_cfg.toggle_heal_sigmoid_key
                        ):
                            player.heal_sigmoid_active = not player.heal_sigmoid_active
                            game_audio.play_power_up(at_rect=player.rect)
                            if player.heal_sigmoid_active:
                                Player.show_center_notice(
                                    player, "Sigmoid 治療模式", now_ms, duration_ms=2500,
                                )
                            else:
                                Player.show_center_notice(
                                    player, "一般模式", now_ms, duration_ms=2500,
                                )
                        elif (
                            not getattr(player, "integral_only_lock", False)
                            and event.key == pygame.K_b
                            and lvl_cfg.allow_brush_b
                        ):
                            t_b = pygame.time.get_ticks()
                            if (
                                lvl_cfg.allow_double_b_area
                                and t_b - last_b_key_ms <= DOUBLE_B_AREA_MOVE_MS
                            ):
                                switch_mode(PlayerMode.AREA_MOVE)
                            else:
                                switch_mode(PlayerMode.BRUSH)
                            last_b_key_ms = t_b
                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_a:
                        is_left = False
                    elif event.key == pygame.K_d:
                        is_right = False
                    elif event.key == pygame.K_1:
                        controller.on_keyup(event.key)
                if event.type == pygame.MOUSEWHEEL:
                    if (
                        get_level_mode_config(level).mode_allowed(PlayerMode.INTEGRAL_BLOCK)
                        and player.game_mode == PlayerMode.INTEGRAL_BLOCK
                    ):
                        if player.integral_axis == IntegralAxis.X:
                            player.integral_axis = IntegralAxis.Y
                        else:
                            player.integral_axis = IntegralAxis.X
                    else:
                        controller.on_mousewheel(event.y)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = mouse_to_game(event.pos)
                    if player.game_mode == PlayerMode.DERIVATIVE_BLOCK:
                        if point_in_placement_zone(
                            mx, my, player.rect.centerx, SCREEN_WIDTH, SCREEN_HEIGHT,
                        ):
                            if add_calculus_block_with_limit(
                                derivative_group,
                                CalculusBlock((mx, my), "derivative"),
                                DERIVATIVE_BLOCKS_MAX,
                                evict_oldest=CALC_DERIVATIVE_EVICT_OLDEST_WHEN_FULL,
                            ):
                                game_audio.play_calculus_place(
                                    at_rect=pygame.Rect(mx, my, TILE_SIZE, TILE_SIZE),
                                )
                    elif player.game_mode == PlayerMode.INTEGRAL_BLOCK:
                        acted = try_integral_xy_on_enemy_bullet(
                            mx, my, player.integral_axis, enemy_bullet_group,
                        )
                        if not acted:
                            acted = try_integral_xy_on_brush(
                                mx, my, player.integral_axis, player, brush_manager, area_group, world,
                            )
                        if not acted and point_in_placement_zone(
                            mx, my, player.rect.centerx, SCREEN_WIDTH, SCREEN_HEIGHT,
                        ):
                            if add_calculus_block_with_limit(
                                integral_group,
                                CalculusBlock(
                                    (mx, my), "integral", axis=player.integral_axis.value,
                                ),
                                INTEGRAL_BLOCKS_MAX,
                                evict_oldest=CALC_INTEGRAL_EVICT_OLDEST_WHEN_FULL,
                            ):
                                game_audio.play_calculus_place(
                                    at_rect=pygame.Rect(mx, my, TILE_SIZE, TILE_SIZE),
                                )
                    elif player.game_mode == PlayerMode.INTEGRAL_XY:
                        if not try_integral_xy_on_enemy_bullet(mx, my, player.integral_axis, enemy_bullet_group):
                            try_integral_xy_on_brush(
                                mx, my, player.integral_axis, player, brush_manager, area_group, world,
                            )
                    elif player.game_mode == PlayerMode.SQUARE_BLOCK:
                        if point_in_placement_zone(
                            mx, my, player.rect.centerx, SCREEN_WIDTH, SCREEN_HEIGHT,
                        ):
                            if len(square_group) >= SQUARE_BLOCKS_MAX:
                                square_group.sprites()[0].kill()
                            square_group.add(CalculusBlock((mx, my), "square"))
                            game_audio.play_calculus_place(
                                at_rect=pygame.Rect(mx, my, TILE_SIZE, TILE_SIZE),
                            )
                    elif player.game_mode == PlayerMode.SQRT_BLOCK:
                        if point_in_placement_zone(
                            mx, my, player.rect.centerx, SCREEN_WIDTH, SCREEN_HEIGHT,
                        ):
                            if len(sqrt_group) >= SQRT_BLOCKS_MAX:
                                sqrt_group.sprites()[0].kill()
                            sqrt_group.add(CalculusBlock((mx, my), "sqrt"))
                            game_audio.play_calculus_place(
                                at_rect=pygame.Rect(mx, my, TILE_SIZE, TILE_SIZE),
                            )
                    elif player.game_mode == PlayerMode.SIGMOID:
                        try_sigmoid_on_enemy_bullet(mx, my, enemy_bullet_group)
                    elif player.game_mode == PlayerMode.SIGMA:
                        sigma_mouse_down_ms = pygame.time.get_ticks()
                    elif player.game_mode == PlayerMode.BRUSH:
                        brush_manager.start_stroke(mx, my)
                    elif player.game_mode == PlayerMode.AREA_MOVE:
                        a = pick_stationary_area_at(area_group, mx, my)
                        if a is not None:
                            area_drag_target = a
                            area_drag_dx = mx - a.rect.centerx
                            area_drag_dy = my - a.rect.centery
                            area_fling_mouse_end_mx = float(mx)
                            area_fling_mouse_end_my = float(my)
                            area_drag_fling_anchor_mx = float(mx)
                            area_drag_fling_anchor_my = float(my)
                        else:
                            reset_area_drag()
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if player.game_mode == PlayerMode.AREA_MOVE and area_drag_target is not None:
                        rx, ry = mouse_to_game(event.pos)
                        ddx = float(rx) - area_drag_fling_anchor_mx
                        ddy = float(ry) - area_drag_fling_anchor_my
                        if math.hypot(ddx, ddy) >= AREA_THROW_RELEASE_MIN_DIST:
                            tgt = area_drag_target
                            if tgt.alive():
                                tgt.apply_throw_velocity(
                                    ddx * AREA_THROW_RELEASE_SPEED_MULT,
                                    ddy * AREA_THROW_RELEASE_SPEED_MULT,
                                )
                        reset_area_drag()
                    elif not (player.game_mode == PlayerMode.AREA_MOVE and area_drag_target is not None):
                        reset_area_drag()
                    up_ms = pygame.time.get_ticks()
                    if player.game_mode == PlayerMode.SIGMA and sigma_mouse_down_ms is not None:
                        upper = sigma_upper_by_hold(up_ms)
                        n = int(math.floor(upper))
                        sigma_schedule.extend(
                            build_sigma_shot_schedule(
                                n,
                                up_ms + 40,
                                SIGMA_FIRE_INTERVAL_MS,
                                SIGMA_ZERO_BURST_COUNT,
                            ),
                        )
                        if n == 0:
                            game_audio.start_bubble_repeat(at_rect=player.rect)
                        sigma_mouse_down_ms = None
                    if player.game_mode == PlayerMode.BRUSH:
                        mx_b, my_b = mouse_to_game(event.pos)
                        brush_manager.end_stroke(mx_b, my_b, player.rect.width)
                    else:
                        brush_manager.end_stroke()
                elif event.type == pygame.MOUSEMOTION:
                    if player.game_mode == PlayerMode.BRUSH:
                        brush_manager.extend_stroke(*mouse_to_game(event.pos))

        present_screen(flatten_focus=True)

    persist_settings()
    pygame.quit()
    sys.exit()
