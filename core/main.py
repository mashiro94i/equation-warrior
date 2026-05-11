"""主迴圈 + state machine + 關卡切換"""
import math
import sys
import pygame

from .area_entity import build_area_bodies_from_polygon, pick_stationary_area_at
from .brush import BrushManager
from .calculus_blocks import CalculusBlock, resolve_calculus_block_interactions
from .constants import (
    BRUSH_MAX_TOTAL_LENGTH_PX, DERIVATIVE_BLOCKS_MAX, DOUBLE_B_AREA_MOVE_MS, FPS, GOLD,
    INTEGRAL_BLOCKS_MAX, MAX_LEVEL, PINK,
    SCREEN_HEIGHT, SCREEN_WIDTH, SIGMA_CHARGE_MAX, SIGMA_CHARGE_STEP_MS, SIGMA_CHARGE_STEP_VALUE,
    SIGMA_FIRE_INTERVAL_MS, SIGMA_ZERO_BURST_COUNT, SKY, WHITE, BLACK, YELLOW,
)
from .controller import EquationController, EquationDisplay
from .enums import ActionTypes, GameState, IntegralAxis, PlayerMode
from .fonts import get_font
from .gameplay import build_sigma_shot_schedule, placement_zone_left_third, point_in_placement_zone
from .interactions import (
    try_integral_xy_on_brush,
    try_integral_xy_on_enemy_bullet,
    try_sigmoid_on_enemy_bullet,
)
from .mode_cooldowns import ModeCooldowns
from .projectile import NumericProjectile
from .soldier import Enemy, Player
from .ui import HealthBar, ScreenFade, TextButton
from .world import Decoration, Exit, HealthBox, Water, World


def init_level(
    level,
    projectile_group,
    enemy_bullet_group,
    enemy_group,
    water_group,
    decoration_group,
    exit_group,
    health_box_group,
    derivative_group,
    integral_group,
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
        derivative_group,
        integral_group,
        area_group,
        numeric_group,
    ):
        g.empty()
    brush_manager.strokes.clear()
    brush_manager.current = None
    brush_manager.total_length = 0.0

    world = World()
    world.process_csv(level)
    for x, y in world.water_tiles:
        water_group.add(Water(x, y))
    for x, y in world.decorations:
        decoration_group.add(Decoration(x, y))
    if world.exit_pos:
        exit_group.add(Exit(*world.exit_pos))
    for x, y in world.health_box_positions:
        health_box_group.add(HealthBox(x, y))
    for ex, ey in world.enemy_spawns:
        enemy_group.add(Enemy(ex, ey))
    player = Player(*world.player_spawn)
    return world, player


def main():
    pygame.init()
    window = pygame.display.set_mode((1600, 900))
    screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("方程式戰士 - Math Equation Warrior")
    clock = pygame.time.Clock()
    display_w, display_h = window.get_size()
    scale = min(display_w / SCREEN_WIDTH, display_h / SCREEN_HEIGHT)
    view_w = int(SCREEN_WIDTH * scale)
    view_h = int(SCREEN_HEIGHT * scale)
    view_x = (display_w - view_w) // 2
    view_y = (display_h - view_h) // 2

    font_small = get_font(18, bold=True)
    font_med = get_font(24, bold=True)
    font_eq = get_font(22, bold=True)
    font_large = get_font(48, bold=True)

    projectile_group = pygame.sprite.Group()
    enemy_bullet_group = pygame.sprite.Group()
    enemy_group = pygame.sprite.Group()
    water_group = pygame.sprite.Group()
    decoration_group = pygame.sprite.Group()
    exit_group = pygame.sprite.Group()
    health_box_group = pygame.sprite.Group()
    derivative_group = pygame.sprite.Group()
    integral_group = pygame.sprite.Group()
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

    state = GameState.MENU
    level = 1
    world, player = init_level(
        level,
        projectile_group,
        enemy_bullet_group,
        enemy_group,
        water_group,
        decoration_group,
        exit_group,
        health_box_group,
        derivative_group,
        integral_group,
        area_group,
        numeric_group,
        brush_manager,
    )
    health_bar = HealthBar(10, 10, player.max_health)
    controller = EquationController(player, projectile_group)
    eq_display = EquationDisplay(font_eq)
    opening_fade = ScreenFade(BLACK, 16)
    death_fade = ScreenFade(PINK, 14)
    is_opening = False

    btn_w, btn_h = 220, 60
    cx = SCREEN_WIDTH // 2 - btn_w // 2
    start_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 80, "START", font_med, btn_w, btn_h)
    settings_btn = TextButton(cx, SCREEN_HEIGHT // 2 + 10, "設置", font_med, btn_w, btn_h)
    exit_btn = TextButton(cx, SCREEN_HEIGHT // 2 + 10, "EXIT", font_med, btn_w, btn_h)
    restart_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 40, "RESTART", font_med, btn_w, btn_h)
    pause_continue_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 100, "繼續", font_med, btn_w, btn_h)
    pause_settings_btn = TextButton(cx, SCREEN_HEIGHT // 2 - 20, "設定", font_med, btn_w, btn_h)
    pause_exit_btn = TextButton(cx, SCREEN_HEIGHT // 2 + 60, "退出", font_med, btn_w, btn_h)
    back_btn = TextButton(20, 20, "返回", font_small, 120, 44)

    is_left = False
    is_right = False
    running = True
    player_anchor_x = SCREEN_WIDTH // 4
    is_paused = False
    pause_page = "main"
    pause_snapshot = None
    pause_click_lock = False
    bgm_volume = 0.5
    sfx_volume = 0.5
    resolution_options = [(1280, 720), (1366, 768), (1440, 810), (1600, 900), (1920, 1080)]
    selected_resolution = (1600, 900)
    menu_page = "main"
    menu_click_lock = False

    def switch_mode(new_mode: PlayerMode):
        nonlocal player, area_drag_target
        now_ms = pygame.time.get_ticks()
        if player.game_mode == new_mode:
            return
        if not mode_cd.can_use(new_mode, now_ms):
            return
        mode_cd.on_leave(player.game_mode, now_ms)
        controller.force_idle()
        brush_manager.end_stroke()
        area_drag_target = None
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

    def sigma_upper_by_hold(now_ms: int) -> float:
        if sigma_mouse_down_ms is None:
            return 0.0
        elapsed = max(0, now_ms - sigma_mouse_down_ms)
        upper = (elapsed // SIGMA_CHARGE_STEP_MS) * SIGMA_CHARGE_STEP_VALUE
        return min(SIGMA_CHARGE_MAX, float(upper))

    def shift_world(dx: int):
        if dx == 0:
            return
        for _img, rect in world.obstacle_list:
            rect.x += dx
        for g in (enemy_group, enemy_bullet_group, projectile_group, numeric_group,
                  derivative_group, integral_group, area_group, water_group,
                  decoration_group, exit_group, health_box_group):
            for s in g:
                if hasattr(s, "base_rect"):
                    s.base_rect.x += dx
                    if hasattr(s, "shape_points") and s.shape_points:
                        s.shape_points = [(x + dx, y) for x, y in s.shape_points]
                    if hasattr(s, "motion_path") and s.motion_path:
                        s.motion_path = [(x + dx, y) for x, y in s.motion_path]
                    s.rect.topleft = s.base_rect.topleft
                else:
                    s.rect.x += dx
        for stroke in brush_manager.strokes:
            stroke.points = [(px + dx, py) for px, py in stroke.points]

    while running:
        clock.tick(FPS)
        screen.fill(SKY)
        now_ms = pygame.time.get_ticks()

        if state == GameState.MENU:
            mpos = game_mouse_pos()
            pressed = pygame.mouse.get_pressed()[0]
            can_click = pressed and not menu_click_lock
            if not pressed:
                menu_click_lock = False
            menu_tips = [
                "1函數：按住瞄準、放開發射（0次方只啵聲）",
                "2微分：放置 d/dx，降次方、凍結敵人、消敵彈",
                "3積分：∫x/∫y 作用 + 放置積分塊（滾輪切軸）",
                "4S：把敵彈變綠色治療彈；5Σ：按住蓄力後發射序列",
                "B畫筆：左側區域繪製，受總長度限制",
                "連按兩次 B：面積拖曳（靜止面積，左鍵拖曳，不可壓進地圖）",
            ]
            if menu_page == "main":
                title = font_large.render("方程式戰士", True, WHITE)
                screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 130)))
                for idx, msg in enumerate(menu_tips):
                    sub = font_small.render(msg, True, WHITE)
                    screen.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 160 + idx * 18)))
                start_btn.draw(screen)
                settings_btn.draw(screen)
                exit_btn.rect.y = SCREEN_HEIGHT // 2 + 100
                exit_btn.draw(screen)
                if can_click and start_btn.rect.collidepoint(mpos):
                    level = 1
                    world, player = init_level(
                        level,
                        projectile_group,
                        enemy_bullet_group,
                        enemy_group,
                        water_group,
                        decoration_group,
                        exit_group,
                        health_box_group,
                        derivative_group,
                        integral_group,
                        area_group,
                        numeric_group,
                        brush_manager,
                    )
                    area_drag_target = None
                    health_bar = HealthBar(10, 10, player.max_health)
                    controller = EquationController(player, projectile_group)
                    sigma_schedule.clear()
                    state = GameState.PLAYING
                    is_opening = True
                    opening_fade.reset()
                    is_left = is_right = False
                    menu_click_lock = True
                elif can_click and settings_btn.rect.collidepoint(mpos):
                    menu_page = "settings"
                    menu_click_lock = True
                elif can_click and exit_btn.rect.collidepoint(mpos):
                    running = False
            else:
                base_title = font_large.render("方程式戰士", True, WHITE)
                screen.blit(base_title, base_title.get_rect(center=(SCREEN_WIDTH // 2, 130)))
                for idx, msg in enumerate(menu_tips):
                    sub = font_small.render(msg, True, WHITE)
                    screen.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 160 + idx * 18)))
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
                    try:
                        pygame.mixer.music.set_volume(float(bgm_volume))
                    except pygame.error:
                        pass

        elif state == GameState.PLAYING and is_paused:
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
                    try:
                        pygame.mixer.music.set_volume(float(bgm_volume))
                    except pygame.error:
                        pass

        elif state == GameState.PLAYING:
            world.draw_obstacles(screen)
            water_group.draw(screen)
            decoration_group.draw(screen)
            exit_group.draw(screen)
            health_box_group.draw(screen)
            if player.game_mode in (PlayerMode.DERIVATIVE_BLOCK, PlayerMode.INTEGRAL_BLOCK, PlayerMode.BRUSH):
                _zx, _zy, zone_w, zone_h = placement_zone_left_third(SCREEN_WIDTH, SCREEN_HEIGHT)
                zone_overlay = pygame.Surface((zone_w, zone_h), pygame.SRCALPHA)
                zone_overlay.fill((255, 255, 255, 35))
                screen.blit(zone_overlay, (_zx, _zy))
                pygame.draw.rect(screen, (255, 255, 255), (_zx, _zy, zone_w, zone_h), 2)

            if player.is_alive:
                player.move(is_left, is_right, world, area_group, enemy_group=enemy_group)
                if player.rect.centerx != player_anchor_x:
                    cam_dx = player_anchor_x - player.rect.centerx
                    player.rect.centerx = player_anchor_x
                    shift_world(cam_dx)
                if player.is_in_air:
                    player.update_action(ActionTypes.JUMP)
                elif is_left or is_right:
                    player.update_action(ActionTypes.RUN)
                else:
                    player.update_action(ActionTypes.IDLE)
                if player.is_aiming:
                    player.is_x_flip = player.facing == -1

            for enemy in enemy_group:
                enemy.ai(player, world, enemy_bullet_group, area_group)
                enemy.update_cooldowns()
                enemy.check_alive()

            for enemy in list(enemy_group):
                if not enemy.is_alive:
                    if enemy.frame_index >= len(enemy.animation_list[ActionTypes.DEATH]) - 1:
                        enemy.kill()

            for b in enemy_bullet_group:
                b.update(world, player, area_group)

            controller.update(mouse_pos=game_mouse_pos())
            if getattr(player, "pop_sound_requests", 0) > 0:
                player.pop_sound_requests = 0

            for proj in projectile_group:
                proj.update(world, enemy_group, player, area_group)

            for nb in numeric_group:
                nb.update(world, enemy_group)

            for d in list(derivative_group):
                if d.alive():
                    d.update_physics(world, derivative_group, integral_group)
            for i in list(integral_group):
                if i.alive():
                    i.update_physics(world, integral_group, derivative_group)

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

            for pts, ci in brush_manager.drain_closed_loop_areas():
                if len(pts) >= 3:
                    ref_r = max(1.0, float(player.rect.width) * 2.0)
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
                if area_drag_target.alive() and pygame.mouse.get_pressed()[0]:
                    mx, my = game_mouse_pos()
                    tcx = int(mx - area_drag_dx)
                    tcy = int(my - area_drag_dy)
                    dx = tcx - area_drag_target.rect.centerx
                    dy = tcy - area_drag_target.rect.centery
                    old_cx = area_drag_target.rect.centerx
                    old_cy = area_drag_target.rect.centery
                    snap = area_drag_target.snapshot_pose()
                    area_drag_target.try_offset_resolve_obstacles(dx, dy, world)
                    dcx = area_drag_target.rect.centerx - old_cx
                    dcy = area_drag_target.rect.centery - old_cy
                    if (dcx != 0 or dcy != 0) and area_drag_target.intersects_rect(player.rect):
                        pr = player.rect.move(dcx, dcy)
                        if (
                            pr.top < 0
                            or pr.bottom > SCREEN_HEIGHT
                            or pr.left < 0
                            or pr.right > SCREEN_WIDTH
                        ):
                            area_drag_target.restore_pose(snap)
                else:
                    area_drag_target = None

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
                if val == 0:
                    player.request_pop_sound()

            if player.game_mode == PlayerMode.SIGMOID:
                mx, my = game_mouse_pos()
                try_sigmoid_on_enemy_bullet(mx, my, enemy_bullet_group)

            if pygame.sprite.spritecollide(player, water_group, False) and player.is_alive:
                player.health = 0.0

            for box in list(health_box_group):
                box.update(player)

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
                        derivative_group,
                        integral_group,
                        area_group,
                        numeric_group,
                        brush_manager,
                    )
                    area_drag_target = None
                    health_bar = HealthBar(10, 10, player.max_health)
                    controller = EquationController(player, projectile_group)
                    sigma_schedule.clear()
                    is_opening = True
                    opening_fade.reset()
                    is_left = is_right = False
                    continue

            player.update_animation()
            for enemy in enemy_group:
                enemy.update_animation()

            brush_manager.draw(screen)

            for enemy in enemy_group:
                enemy.draw(screen)
                if enemy.is_alive:
                    hp_img = font_small.render(f"HP: {enemy.health:.2f}", True, WHITE)
                    hp_rect = hp_img.get_rect(midbottom=(enemy.rect.centerx, enemy.rect.top - 6))
                    bg = pygame.Surface((hp_rect.width + 8, hp_rect.height + 4), pygame.SRCALPHA)
                    bg.fill((0, 0, 0, 140))
                    screen.blit(bg, (hp_rect.x - 4, hp_rect.y - 2))
                    screen.blit(hp_img, hp_rect)
            player.draw(screen)
            enemy_bullet_group.draw(screen)
            projectile_group.draw(screen)
            numeric_group.draw(screen)
            derivative_group.draw(screen)
            integral_group.draw(screen)
            area_group.draw(screen)

            controller.draw_preview(screen, world)

            health_bar.draw(screen, player.health)
            screen.blit(font_small.render(f"Level {level}/{MAX_LEVEL}", True, BLACK), (10, 38))
            hp_txt = font_small.render(
                f"HP {player.health:.2f}/{player.max_health:.2f}",
                True,
                BLACK,
            )
            screen.blit(hp_txt, (10, 60))
            cd_lines = [
                (PlayerMode.FUNCTION, "1:f(x)"),
                (PlayerMode.DERIVATIVE_BLOCK, "2:d/dx"),
                (PlayerMode.INTEGRAL_BLOCK, "3:∫"),
                (PlayerMode.SIGMOID, "4:S"),
                (PlayerMode.SIGMA, "5:Σ"),
            ]
            for idx, (mode, label) in enumerate(cd_lines):
                total_ms = mode_cd.total_ms(mode)
                rem_ms = mode_cd.remaining_ms(mode, now_ms)
                txt = f"{label} CD {rem_ms / 1000:.1f}s/{total_ms / 1000:.1f}s"
                screen.blit(font_small.render(txt, True, BLACK), (10, 82 + idx * 20))

            controller.draw_cubic_msg(screen, font_med)

            if player.game_mode == PlayerMode.SIGMOID:
                mx, my = game_mouse_pos()
                s_txt = font_large.render("S", True, GOLD)
                screen.blit(s_txt, s_txt.get_rect(center=(mx, my)))
            elif player.game_mode == PlayerMode.DERIVATIVE_BLOCK:
                mx, my = game_mouse_pos()
                d_up = font_small.render("d", True, YELLOW)
                d_dn = font_small.render("dx", True, YELLOW)
                screen.blit(d_up, d_up.get_rect(center=(mx, my - 9)))
                pygame.draw.line(screen, YELLOW, (mx - 11, my - 1), (mx + 11, my - 1), 2)
                screen.blit(d_dn, d_dn.get_rect(center=(mx, my + 9)))
            elif player.game_mode == PlayerMode.INTEGRAL_BLOCK:
                mx, my = game_mouse_pos()
                int_txt = font_med.render(f"∫{player.integral_axis.value}", True, YELLOW)
                screen.blit(int_txt, int_txt.get_rect(center=(mx, my)))
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
                mode_msg = f"微分模式：d/dx 塊 {len(derivative_group)}/{DERIVATIVE_BLOCKS_MAX}"
            elif player.game_mode == PlayerMode.INTEGRAL_BLOCK:
                mode_msg = (
                    f"積分模式：∫{player.integral_axis.value} | 積分塊 "
                    f"{len(integral_group)}/{INTEGRAL_BLOCKS_MAX}"
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
                mode_msg = "面積拖曳：左鍵點靜止面積後拖曳（貼地圖邊緣會卡住）"
            mode_img = font_small.render(mode_msg, True, WHITE)
            screen.blit(mode_img, mode_img.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 18)))

            player.check_alive()
            if not player.is_alive:
                state = GameState.DEATH
                death_fade.reset()

            if is_opening:
                if opening_fade.fade_in(screen):
                    is_opening = False

        elif state == GameState.DEATH:
            world.draw_obstacles(screen)
            water_group.draw(screen)
            for enemy in enemy_group:
                enemy.draw(screen)
            player.draw(screen)
            health_bar.draw(screen, 0)
            done = death_fade.fade_out(screen)
            if done:
                msg = font_large.render("YOU DIED", True, WHITE)
                screen.blit(msg, msg.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 120)))
                restart_btn.draw(screen)
                if restart_btn.is_click(mouse_pos=game_mouse_pos(), pressed=pygame.mouse.get_pressed()[0]):
                    level = 1
                    world, player = init_level(
                        level,
                        projectile_group,
                        enemy_bullet_group,
                        enemy_group,
                        water_group,
                        decoration_group,
                        exit_group,
                        health_box_group,
                        derivative_group,
                        integral_group,
                        area_group,
                        numeric_group,
                        brush_manager,
                    )
                    area_drag_target = None
                    health_bar = HealthBar(10, 10, player.max_health)
                    controller = EquationController(player, projectile_group)
                    sigma_schedule.clear()
                    state = GameState.PLAYING
                    is_opening = True
                    opening_fade.reset()
                    death_fade.reset()
                    is_left = is_right = False

        elif state == GameState.WIN:
            win_text = font_large.render("YOU WIN!", True, GOLD)
            screen.blit(win_text, win_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50)))
            restart_btn.draw(screen)
            if restart_btn.is_click(mouse_pos=game_mouse_pos(), pressed=pygame.mouse.get_pressed()[0]):
                state = GameState.MENU

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if state == GameState.MENU:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if menu_page == "settings":
                        menu_page = "main"
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    if menu_page == "settings":
                        menu_page = "main"
            if state == GameState.PLAYING and player.is_alive:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if is_paused:
                        is_paused = False
                        pause_snapshot = None
                    else:
                        is_paused = True
                        pause_page = "main"
                        pause_snapshot = screen.copy()
                        is_left = is_right = False
                        brush_manager.end_stroke()
                        area_drag_target = None
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
                        if not player.is_in_air:
                            player.is_jump = True
                    elif event.key == pygame.K_1:
                        switch_mode(PlayerMode.FUNCTION)
                        controller.on_keydown(event.key)
                    elif event.key == pygame.K_2:
                        switch_mode(PlayerMode.DERIVATIVE_BLOCK)
                    elif event.key == pygame.K_3:
                        switch_mode(PlayerMode.INTEGRAL_BLOCK)
                    elif event.key == pygame.K_4:
                        switch_mode(PlayerMode.SIGMOID)
                    elif event.key == pygame.K_5:
                        switch_mode(PlayerMode.SIGMA)
                    elif event.key == pygame.K_b:
                        t_b = pygame.time.get_ticks()
                        if t_b - last_b_key_ms <= DOUBLE_B_AREA_MOVE_MS:
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
                    if player.game_mode == PlayerMode.INTEGRAL_BLOCK:
                        if player.integral_axis == IntegralAxis.X:
                            player.integral_axis = IntegralAxis.Y
                        else:
                            player.integral_axis = IntegralAxis.X
                    else:
                        controller.on_mousewheel(event.y)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = mouse_to_game(event.pos)
                    if player.game_mode == PlayerMode.DERIVATIVE_BLOCK:
                        if point_in_placement_zone(mx, my, SCREEN_WIDTH, SCREEN_HEIGHT):
                            if len(derivative_group) >= DERIVATIVE_BLOCKS_MAX:
                                oldest = derivative_group.sprites()[0]
                                oldest.kill()
                            derivative_group.add(CalculusBlock((mx, my), "derivative"))
                    elif player.game_mode == PlayerMode.INTEGRAL_BLOCK:
                        acted = try_integral_xy_on_enemy_bullet(
                            mx, my, player.integral_axis, enemy_bullet_group,
                        )
                        if not acted:
                            acted = try_integral_xy_on_brush(
                                mx, my, player.integral_axis, player, brush_manager, area_group, world,
                            )
                        if not acted and point_in_placement_zone(mx, my, SCREEN_WIDTH, SCREEN_HEIGHT):
                            if len(integral_group) >= INTEGRAL_BLOCKS_MAX:
                                integral_group.sprites()[0].kill()
                            integral_group.add(
                                CalculusBlock((mx, my), "integral", axis=player.integral_axis.value),
                            )
                    elif player.game_mode == PlayerMode.INTEGRAL_XY:
                        if not try_integral_xy_on_enemy_bullet(mx, my, player.integral_axis, enemy_bullet_group):
                            try_integral_xy_on_brush(
                                mx, my, player.integral_axis, player, brush_manager, area_group, world,
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
                        else:
                            area_drag_target = None
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    area_drag_target = None
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
                        sigma_mouse_down_ms = None
                    brush_manager.end_stroke()
                elif event.type == pygame.MOUSEMOTION:
                    if player.game_mode == PlayerMode.BRUSH:
                        brush_manager.extend_stroke(*mouse_to_game(event.pos))

        window.fill((0, 0, 0))
        scaled = pygame.transform.smoothscale(screen, (view_w, view_h))
        window.blit(scaled, (view_x, view_y))
        pygame.display.update()

    pygame.quit()
    sys.exit()
