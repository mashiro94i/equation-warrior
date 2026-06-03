"""特殊敵人 AI、代數狀態、傷害過濾。"""
from __future__ import annotations

import math
import random

import pygame

from .constants import GRAVITY, SCREEN_HEIGHT, SCREEN_WIDTH, TILE_SIZE
from .enemy_archetypes import (
    GID_AREA_SPRAYER,
    GID_EXP_X,
    GID_GIANT_256,
    GID_KEY_TANK,
    GID_NEGATIVE_ONE,
    GID_SIN_WAVE,
    SIN_WAVE_GIDS,
    GID_TINY_FRACTION,
)
from .projectile import EnemyBullet

_SIN_LABELS = ("sin(x)", "cos(x)", "-sin(x)")
# 65822 暴走：降低每輪發數與頻率，避免彈幕過密卡頓
AREA_SPRAYER_RAMPAGE_BURST_MS = 120
AREA_SPRAYER_RAMPAGE_BULLETS = 6
SIN_LUNGE_TILES = 4
SIN_STUN_MS = 5000
SIN_STANDOFF_MIN_TILES = 2.0
SIN_STANDOFF_MAX_TILES = 3.0
SIN_H_RANGE_MIN_TILES = 3.0
SIN_H_RANGE_MAX_TILES = 6.0
SIN_V_RANGE_MIN_TILES = 1.0
SIN_V_RANGE_MAX_TILES = 2.0
SIN_WALL_MARGIN_TILES = 0.3
SIN_AXIS_PAUSE_CHANCE = 0.30
SIN_AXIS_PAUSE_MS = 500
SIN_AXIS_PAUSE_CD_MS = 3000
SIN_HORIZONTAL_PHASE_STEP = 0.13
SIN_VERTICAL_PHASE_STEP = 0.26


def is_sin_wave_enemy(enemy) -> bool:
    return getattr(enemy, "ai_kind", "") == "sin_wave" or int(enemy.enemy_gid) in SIN_WAVE_GIDS


def is_sin_wave_stunned(enemy, now_ms: int | None = None) -> bool:
    if not is_sin_wave_enemy(enemy):
        return False
    if now_ms is None:
        now_ms = pygame.time.get_ticks()
    return int(getattr(enemy, "_stun_until_ms", 0)) > int(now_ms)


def is_exp_flyer_enemy(enemy) -> bool:
    return getattr(enemy, "ai_kind", "") == "exp_flyer" or int(enemy.enemy_gid) == GID_EXP_X


def is_area_sprayer_enemy(enemy) -> bool:
    return getattr(enemy, "ai_kind", "") == "area_spray" or int(enemy.enemy_gid) == GID_AREA_SPRAYER


def is_flying_enemy(enemy) -> bool:
    if is_sin_wave_stunned(enemy):
        return False
    return (
        is_sin_wave_enemy(enemy)
        or is_exp_flyer_enemy(enemy)
        or is_area_sprayer_enemy(enemy)
    )


def passes_through_walls(enemy) -> bool:
    return bool(getattr(enemy, "ghost_walls", False))


def enemy_ignores_spikes_and_ledges(enemy) -> bool:
    return is_flying_enemy(enemy) or passes_through_walls(enemy)


def entity_on_screen(rect) -> bool:
    from .game_audio import rect_on_screen

    return rect_on_screen(rect)


def update_ai_activation(enemy) -> None:
    """怪物進入玩家視野後永久啟動 AI（eˣ 除外）。"""
    if entity_on_screen(enemy.rect):
        if is_exp_flyer_enemy(enemy) and not getattr(enemy, "_exp_enter_sfx_played", False):
            from . import game_audio

            enemy._exp_enter_sfx_played = True
            game_audio.play_exp_enter(at_rect=enemy.rect, enemy=enemy)
        enemy._ai_activated = True


def is_ai_active(enemy, player=None) -> bool:
    if is_exp_flyer_enemy(enemy):
        return entity_on_screen(enemy.rect)
    return bool(getattr(enemy, "_ai_activated", False))


def apply_archetype_to_enemy(enemy) -> None:
    from .enemy_archetypes import archetype_for_gid

    arch = archetype_for_gid(enemy.enemy_gid)
    if arch is None:
        return
    enemy.max_health = float(arch.max_hp)
    enemy.health = float(arch.max_hp)
    enemy.head_label = arch.head_label
    enemy.speed_mult = float(arch.speed_mult)
    enemy.shoot_cd_mult = float(arch.shoot_cd_mult)
    enemy.scale_mult = float(arch.scale_mult)
    enemy.alpha = int(arch.alpha)
    enemy.ghost_walls = bool(arch.ghost_walls)
    enemy.ghost_area = bool(arch.ghost_area)
    enemy.chase_aggressive = bool(arch.chase_aggressive)
    enemy.ai_kind = arch.ai
    enemy.calculus_immune = bool(arch.calculus_immune)
    enemy.only_heal_bullet_hurt = bool(arch.only_heal_bullet_hurt)
    enemy.invincible = bool(arch.invincible)
    enemy.uses_melee_bump = bool(arch.melee_bump)
    if enemy.enemy_gid == GID_TINY_FRACTION:
        enemy.math_label = "0.01"
    if enemy.enemy_gid == GID_NEGATIVE_ONE:
        enemy.math_label = "-1"
    if is_exp_flyer_enemy(enemy) or is_area_sprayer_enemy(enemy):
        enemy.vel_y = 0.0
        enemy.is_in_air = False
    if is_sin_wave_enemy(enemy):
        enemy.sin_phase_index = 0
        enemy._sin_last_off_y = 0.0
        enemy._sin_anchor_bottom = int(enemy.rect.bottom)
        _init_sin_wave_ranges(enemy)
        enemy._sin_t = 0.0
        enemy._sin_phase_h = 0.0
        enemy._sin_last_off_h = 0.0
        enemy._sin_phase_v = 0.0
        enemy._sin_h_pause_until_ms = 0
        enemy._sin_h_pause_cd_until_ms = 0
        enemy._sin_v_pause_until_ms = 0
        enemy._sin_v_pause_cd_until_ms = 0
        enemy._lunge_remaining_px = 0.0
        enemy.vel_y = 0.0
        enemy.is_in_air = False
    if is_calc_tank_enemy(enemy):
        enemy._calc_tank_base_speed_mult = float(arch.speed_mult)
        configure_calc_tank_algebra_state(enemy)
    if enemy.enemy_gid == GID_GIANT_256:
        enemy._giant_base_max_hp = float(arch.max_hp)
        enemy._giant_base_speed_mult = float(arch.speed_mult)
        enemy._giant_base_scale = float(arch.scale_mult)


def _refresh_appearance(enemy) -> None:
    from .enemy_visual import apply_enemy_appearance, refresh_enemy_alpha

    apply_enemy_appearance(enemy)
    refresh_enemy_alpha(enemy)


def effective_shoot_cooldown(enemy) -> int:
    base = getattr(enemy, "SHOOT_COOLDOWN_FRAMES", 80)
    return max(2, int(round(base * getattr(enemy, "shoot_cd_mult", 1.0))))


def _projectile_is_healing(proj) -> bool:
    return bool(
        getattr(proj, "healing_shot", False)
        or getattr(proj, "is_healing", False)
    )


def can_take_projectile_damage(enemy, proj) -> bool:
    if not enemy.is_alive:
        return False
    if getattr(enemy, "invincible", False):
        return False
    if getattr(enemy, "only_heal_bullet_hurt", False):
        return _projectile_is_healing(proj)
    return True


def on_projectile_hit(enemy, proj) -> None:
    if getattr(enemy, "only_heal_bullet_hurt", False) and _projectile_is_healing(proj):
        enemy.health = 0.0
        enemy.check_alive()
        return
    if getattr(enemy, "invincible", False):
        return
    dmg = float(getattr(proj, "hit_damage", 0))
    if _projectile_is_healing(proj):
        enemy.heal(dmg)
    else:
        enemy.take_damage(dmg)


def on_calculus_block_hit(enemy, kind: str) -> bool:
    """回傳 True 表示已處理（不再走預設凍結邏輯）。"""
    if getattr(enemy, "calculus_immune", False):
        return True
    gid = int(enemy.enemy_gid)
    if is_calc_tank_enemy(enemy):
        _calc_tank_algebra(enemy, kind)
        return True
    if gid == GID_TINY_FRACTION:
        _tiny_fraction_algebra(enemy, kind)
        _refresh_appearance(enemy)
        return True
    if gid == GID_NEGATIVE_ONE:
        _neg_one_algebra(enemy, kind)
        _refresh_appearance(enemy)
        return True
    if gid == GID_GIANT_256:
        _giant_algebra(enemy, kind)
        _refresh_appearance(enemy)
        return True
    if is_sin_wave_enemy(enemy):
        _sin_algebra(enemy, kind)
        _sin_lunge(enemy)
        return True
    return False


def is_calc_tank_enemy(enemy) -> bool:
    return int(getattr(enemy, "enemy_gid", 0)) == GID_KEY_TANK


def configure_calc_tank_algebra_state(enemy, *, force: bool = False) -> None:
    """設定 99999 坦克代數狀態（65840 預設純 99999）。"""
    if not is_calc_tank_enemy(enemy):
        return
    if force or not getattr(enemy, "_calc_tank_algebra_inited", False):
        enemy._calc_tank_base_exp = 1
        enemy._calc_tank_x_exp = 0
        enemy._calc_tank_algebra_inited = True
    _calc_tank_sync_label(enemy)


def _calc_tank_label(enemy) -> str:
    return str(getattr(enemy, "math_label", None) or enemy.head_label or "99999")


def _calc_tank_set_label(enemy, label: str) -> None:
    enemy.math_label = label
    enemy.head_label = label


def _calc_tank_exp_suffix(power: int) -> str:
    if power <= 1:
        return ""
    return "²" if power == 2 else f"^{power}"


def _calc_tank_sync_label(enemy) -> None:
    base_exp = max(1, int(getattr(enemy, "_calc_tank_base_exp", 1)))
    x_exp = max(0, int(getattr(enemy, "_calc_tank_x_exp", 0)))
    label = "99999"
    if base_exp > 1:
        label += _calc_tank_exp_suffix(base_exp)
    if x_exp > 0:
        label += "x" + _calc_tank_exp_suffix(x_exp)
    enemy._calc_tank_base_exp = base_exp
    enemy._calc_tank_x_exp = x_exp
    _calc_tank_set_label(enemy, label)


def _calc_tank_reset_speed(enemy) -> None:
    base_speed = float(getattr(enemy, "_calc_tank_base_speed_mult", 0.7))
    enemy._calc_integral_permanent = False
    enemy.speed_mult = base_speed


def calc_tank_kill(enemy) -> None:
    enemy.health = 0.0
    enemy.check_alive()


def _calc_tank_algebra(enemy, kind: str) -> None:
    """積分加 x；平方提高次方（99999x→99999x^2…）；僅純 99999 被微分即死。每次僅 ±1。"""
    now_ms = pygame.time.get_ticks()
    if now_ms < int(getattr(enemy, "_calc_tank_algebra_gate_ms", 0)):
        return
    enemy._calc_tank_algebra_gate_ms = now_ms + 100

    base_exp = max(1, int(getattr(enemy, "_calc_tank_base_exp", 1)))
    x_exp = max(0, int(getattr(enemy, "_calc_tank_x_exp", 0)))

    if kind == "integral":
        if x_exp > 0:
            enemy._calc_tank_x_exp = x_exp + 1
        else:
            enemy._calc_tank_x_exp = 1
        enemy._calc_integral_permanent = True
        enemy.speed_mult = 10.0
    elif kind == "derivative":
        if base_exp == 1 and x_exp == 0:
            calc_tank_kill(enemy)
            return
        if x_exp > 0:
            enemy._calc_tank_x_exp = x_exp - 1
            if enemy._calc_tank_x_exp == 0:
                _calc_tank_reset_speed(enemy)
        elif base_exp > 1:
            enemy._calc_tank_base_exp = base_exp - 1
    elif kind == "square":
        if x_exp > 0:
            enemy._calc_tank_x_exp = x_exp + 1
        else:
            enemy._calc_tank_base_exp = base_exp + 1
    elif kind == "sqrt":
        if x_exp > 1:
            enemy._calc_tank_x_exp = x_exp - 1
        elif x_exp == 1:
            enemy._calc_tank_x_exp = 0
            _calc_tank_reset_speed(enemy)
        elif base_exp > 1:
            enemy._calc_tank_base_exp = base_exp - 1

    _calc_tank_sync_label(enemy)


def _tiny_fraction_algebra(enemy, kind: str) -> None:
    label = getattr(enemy, "math_label", "0.01")
    if kind == "sqrt":
        if label == "0.01":
            enemy.math_label = "0.1"
            enemy.head_label = "0.1"
            enemy.speed_mult = 1.0
            enemy.scale_mult = 1.0
            enemy.invincible = False
            enemy.shoot_cd_mult = 1.0 / 3.0
        elif label == "0.0001":
            enemy.math_label = "0.01"
            enemy.head_label = "0.01"
            enemy.speed_mult = 10.0
            enemy.scale_mult = 0.1
            enemy.shoot_cd_mult = 1.0 / 3.0
            enemy.invincible = False
        elif label == "0.1":
            enemy.math_label = "0.01"
            enemy.head_label = "0.01"
            enemy.speed_mult = 10.0
            enemy.scale_mult = 0.1
            enemy.shoot_cd_mult = 1.0 / 3.0
    elif kind == "square":
        if label == "0.01":
            enemy.math_label = "0.0001"
            enemy.head_label = "0.0001"
            enemy.invincible = True
            enemy.shoot_cd_mult = 1.0 / 5.0


def _neg_one_algebra(enemy, kind: str) -> None:
    label = getattr(enemy, "math_label", "-1")
    if kind == "sqrt" and label == "-1":
        enemy.math_label = "i"
        enemy.head_label = "i"
        enemy.ghost_walls = True
        enemy.ghost_area = True
        enemy.alpha = 178
        enemy.only_heal_bullet_hurt = False
        enemy.ai_kind = "imaginary"
    elif kind == "square" and label == "i":
        enemy.math_label = "-1"
        enemy.head_label = "-1"
        enemy.ghost_walls = False
        enemy.ghost_area = False
        enemy.alpha = 153
        enemy.only_heal_bullet_hurt = True
        enemy.ai_kind = "neg_one"


def _giant_algebra(enemy, kind: str) -> None:
    from . import game_audio

    old_max = float(enemy.max_health)
    old_hp = float(enemy.health)
    if kind in ("square", "sqrt"):
        game_audio.play_giant_crush(at_rect=enemy.rect)
    if kind == "square":
        enemy.pending_crush_player = True
        enemy.max_health = old_max * 2.0
        enemy.health = enemy.max_health - old_max + old_hp
        enemy.speed_mult = getattr(enemy, "_giant_base_speed_mult", 0.25) * 0.5
        enemy.scale_mult = getattr(enemy, "_giant_base_scale", 1.0) * 1.3
        enemy.head_label = str(int(round(enemy.max_health)))
        enemy._giant_grown_until_ms = pygame.time.get_ticks() + 1500
    elif kind == "sqrt":
        enemy.max_health = max(1.0, old_max * 0.5)
        enemy.health = max(enemy.max_health, old_hp)
        enemy.speed_mult = getattr(enemy, "_giant_base_speed_mult", 0.25) * 2.0
        enemy.scale_mult = getattr(enemy, "_giant_base_scale", 1.0) / 1.3
        enemy.head_label = str(int(round(enemy.max_health)))


def _sin_algebra(enemy, kind: str) -> None:
    idx = int(getattr(enemy, "sin_phase_index", 0)) % 3
    if kind == "derivative":
        idx = (idx + 1) % 3
    elif kind == "integral":
        idx = (idx - 1) % 3
    enemy.sin_phase_index = idx
    enemy.head_label = _SIN_LABELS[idx]


def _sin_lunge(enemy) -> None:
    enemy._lunge_remaining_px = float(TILE_SIZE * SIN_LUNGE_TILES)
    enemy._lunge_speed_backup = float(getattr(enemy, "speed_mult", 1.5))
    enemy.speed_mult = 2.0
    enemy._height_scale = 0.5


def sin_wave_lunge_active(enemy) -> bool:
    return float(getattr(enemy, "_lunge_remaining_px", 0.0)) > 0.5


def _sin_nearest_wall_center_x(enemy, world) -> int | None:
    """暈眩時朝最近牆壁的水平中心。"""
    margin_y = int(TILE_SIZE * 4)
    best_dist = None
    best_x = None
    ex = enemy.rect.centerx
    for _img, rect in world.obstacle_list:
        if rect.bottom < enemy.rect.top - margin_y or rect.top > enemy.rect.bottom + margin_y:
            continue
        dist = abs(rect.centerx - ex)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_x = rect.centerx
    return best_x


def _tick_sin_wave_stun_move(enemy, world) -> None:
    """暈眩期間水平移向最近牆壁，並維持落地重力。"""
    target_x = _sin_nearest_wall_center_x(enemy, world)
    if target_x is not None:
        dx = target_x - enemy.rect.centerx
        if abs(dx) >= 2:
            speed = max(2, int(round(enemy.speed * float(getattr(enemy, "speed_mult", 1.0)))))
            step = int(math.copysign(min(abs(dx), speed), dx))
            step = enemy._clamp_horizontal_move(step, world, None)
            enemy.rect.x += step
    if getattr(enemy, "is_in_air", False):
        enemy.vel_y = min(14.0, float(enemy.vel_y) + GRAVITY)
        enemy.rect.y += int(enemy.vel_y)
        feet = pygame.Rect(enemy.rect.x, enemy.rect.bottom + 1, enemy.rect.width, 2)
        if any(rect.colliderect(feet) for _img, rect in world.obstacle_list):
            enemy.vel_y = 0.0
            enemy.is_in_air = False
            enemy._height_scale = 1.0


def _begin_sin_wave_stun(enemy, now_ms: int | None = None) -> None:
    """暈眩 5s：失去飛行、掉落，播放暈眩音效。"""
    from . import game_audio

    if now_ms is None:
        now_ms = pygame.time.get_ticks()
    was_stunned = is_sin_wave_stunned(enemy, now_ms)
    enemy._stun_until_ms = int(now_ms) + SIN_STUN_MS
    enemy._lunge_remaining_px = 0.0
    enemy._height_scale = 1.0
    enemy.vel_y = 5.0
    enemy.is_in_air = True
    if not was_stunned:
        game_audio.play_sin_stun(at_rect=enemy.rect, enemy=enemy)


def tick_sin_wave_move_sfx(enemy, moving: bool) -> None:
    """sin(x) 移動時播放拍翅音效。"""
    from . import game_audio

    if not enemy.is_alive or not moving or is_sin_wave_stunned(enemy):
        return
    now_ms = pygame.time.get_ticks()
    if now_ms - int(getattr(enemy, "_sin_wing_sfx_ms", 0)) < 1000:
        return
    enemy._sin_wing_sfx_ms = now_ms
    game_audio.play_sin_wing_flap(at_rect=enemy.rect, enemy=enemy)


def sin_wave_lunge_step(enemy, world) -> None:
    """俯衝固定 4 格距離（速度 ×2、高度 ×0.5）；撞牆暈眩。"""
    remain = float(getattr(enemy, "_lunge_remaining_px", 0.0))
    if remain <= 0:
        _end_sin_lunge(enemy)
        return
    step = max(2, int(round(enemy.speed * 2.0 * getattr(enemy, "speed_mult", 2.0))))
    move = min(step, remain) * int(enemy.direction)
    if move == 0:
        _end_sin_lunge(enemy)
        return
    move = enemy._clamp_horizontal_move(move, world, None)
    if move == 0:
        _end_sin_lunge(enemy)
        _begin_sin_wave_stun(enemy)
        return
    enemy.rect.x += move
    enemy._lunge_remaining_px = max(0.0, remain - abs(move))
    if enemy._lunge_remaining_px <= 0.5:
        _end_sin_lunge(enemy)


def _end_sin_lunge(enemy) -> None:
    enemy._lunge_remaining_px = 0.0
    enemy.speed_mult = float(getattr(enemy, "_lunge_speed_backup", 3.0))
    enemy._height_scale = 1.0


def update_enemy_special(enemy, player, world, enemy_bullet_group, area_group, now_ms: int) -> None:
    from .enums import ActionTypes

    if not enemy.is_alive:
        return
    if getattr(enemy, "_stun_until_ms", 0) > now_ms:
        if is_sin_wave_enemy(enemy):
            _tick_sin_wave_stun_move(enemy, world)
        enemy.update_action(ActionTypes.IDLE)
        return
    if enemy.enemy_gid == GID_GIANT_256:
        grown_until = getattr(enemy, "_giant_grown_until_ms", 0)
        if grown_until and now_ms >= grown_until and not getattr(enemy, "_giant_reverting", False):
            enemy._giant_reverting = True
            enemy.max_health = float(getattr(enemy, "_giant_base_max_hp", 256))
            enemy.health = min(enemy.health, enemy.max_health)
            enemy.speed_mult = float(getattr(enemy, "_giant_base_speed_mult", 0.25))
            enemy.scale_mult = float(getattr(enemy, "_giant_base_scale", 1.0))
            enemy.head_label = "256"
            enemy._giant_grown_until_ms = 0
            _refresh_appearance(enemy)
    if getattr(enemy, "ai_kind", "") == "imaginary":
        _imaginary_drain(player, enemy, now_ms)


def _calc_tank_sense_rect(enemy) -> pygame.Rect:
    """左、右各 5 格、上方 5 格、往下 2 格（與面朝無關）。"""
    r = enemy.rect
    return pygame.Rect(
        r.left - TILE_SIZE * 5,
        r.top - TILE_SIZE * 5,
        r.width + TILE_SIZE * 10,
        r.height + TILE_SIZE * 7,
    )


def _calc_tank_block_in_sense(block, sense: pygame.Rect) -> bool:
    if not hasattr(block, "rect"):
        return False
    br = block.rect
    return sense.colliderect(br) or sense.collidepoint(br.centerx, br.centery)


def _calc_tank_scan_blocks(enemy, blocks, kind: str, sense: pygame.Rect):
    """在感測框內找最近的一塊（不依面朝）。"""
    from .calculus_blocks import CalculusBlock

    best = None
    best_dist = float("inf")
    for block in blocks:
        if not isinstance(block, CalculusBlock):
            continue
        if getattr(block, "kind", None) != kind:
            continue
        if not _calc_tank_block_in_sense(block, sense):
            continue
        d = math.hypot(
            block.rect.centerx - enemy.rect.centerx,
            block.rect.centery - enemy.rect.centery,
        )
        if d < best_dist:
            best_dist = d
            best = block
    return best


def _calc_tank_can_move_horiz(enemy, world, area_group, direction: int) -> bool:
    """單步探測：該水平方向是否走得動（牆／刺／懸崖）。"""
    if direction == 0:
        return False
    probe = direction * max(1, min(6, enemy._effective_speed()))
    if enemy._would_overlap_spike_damage_feet(world, probe):
        return False
    if not getattr(enemy, "ghost_walls", False):
        if enemy._clamp_horizontal_move(probe, world, area_group) == 0:
            return False
    if not enemy.is_in_air and enemy._ledge_clear_ahead(world, area_group, direction):
        return False
    return True


def _calc_tank_pick_flee_direction(enemy, world, area_group, threat) -> int:
    """遠離微分；逃離方向遇牆／懸崖則改走懸崖反方向。"""
    away = 1 if enemy.rect.centerx > threat.rect.centerx else -1
    if _calc_tank_can_move_horiz(enemy, world, area_group, away):
        return away
    inland = -away
    if _calc_tank_can_move_horiz(enemy, world, area_group, inland):
        return inland
    return away


def calc_tank_bump_attack_range_rect(enemy) -> pygame.Rect:
    """與衝撞判定相近的攻擊範圍（水平約 3 格）。"""
    return enemy.rect.inflate(TILE_SIZE * 5, TILE_SIZE)


def calc_tank_derivative_in_attack_range(enemy) -> bool:
    """攻擊／衝撞範圍內有微分則不發動攻擊。"""
    from .calculus_blocks import CalculusBlock

    zone = calc_tank_bump_attack_range_rect(enemy)
    for block in getattr(enemy, "_nearby_derivative_blocks", ()):
        if not isinstance(block, CalculusBlock):
            continue
        if getattr(block, "kind", None) != "derivative":
            continue
        if zone.colliderect(block.rect):
            return True
    return False


def _calc_tank_block_ai(enemy, world, now_ms: int, area_group=None) -> None:
    """65840：感測內遠離微分、靠近積分（×2）；離開感測即恢復；碰到微分即死。"""
    from .calculus_blocks import CalculusBlock

    base_speed = float(getattr(enemy, "_calc_tank_base_speed_mult", 0.7))
    react_speed = base_speed * 2.0
    enemy._calc_tank_block_override = False
    enemy._calc_tank_priority = False
    sense = _calc_tank_sense_rect(enemy)
    deriv_blocks = tuple(getattr(enemy, "_nearby_derivative_blocks", ()))
    int_blocks = tuple(getattr(enemy, "_nearby_integral_blocks", ()))

    threat = _calc_tank_scan_blocks(enemy, deriv_blocks, "derivative", sense)
    attract = _calc_tank_scan_blocks(enemy, int_blocks, "integral", sense)

    if getattr(enemy, "_calc_integral_permanent", False):
        enemy.speed_mult = 10.0
        return

    if threat is not None:
        enemy.speed_mult = react_speed
        enemy.direction = _calc_tank_pick_flee_direction(enemy, world, area_group, threat)
        enemy._calc_tank_block_override = True
        enemy._calc_tank_priority = True
    elif attract is not None:
        enemy.speed_mult = react_speed
        toward = 1 if attract.rect.centerx >= enemy.rect.centerx else -1
        if not _calc_tank_can_move_horiz(enemy, world, area_group, toward):
            alt = -toward
            if _calc_tank_can_move_horiz(enemy, world, area_group, alt):
                toward = alt
        enemy.direction = toward
        enemy._calc_tank_block_override = True
        enemy._calc_tank_priority = True
    else:
        enemy._calc_tank_block_override = False
        enemy._calc_tank_priority = False
        enemy._dodge_until_ms = 0
        if not getattr(enemy, "_calc_integral_permanent", False):
            enemy.speed_mult = base_speed


def calc_tank_overrides_chase_direction(enemy, now_ms: int) -> bool:
    return bool(getattr(enemy, "_calc_tank_block_override", False))


def calc_tank_priority_active(enemy, now_ms: int) -> bool:
    """僅在感測框內有微分／積分時優先移動；離開感測即恢復。"""
    if bool(getattr(enemy, "_calc_integral_permanent", False)):
        return False
    return bool(getattr(enemy, "_calc_tank_priority", False))


def calc_tank_drop_blocked_by_spikes(enemy, world, lead_x: int, land_top_y: int) -> bool:
    """65840 欲往下 1~2 格：僅在伸出地刺時偵測；落點或下落路徑有刺則不可下落。"""
    if not is_calc_tank_enemy(enemy):
        return False
    if not getattr(world, "spikes_extended", False):
        return False
    cur_feet = int(enemy.rect.bottom)
    land_top_y = int(land_top_y)
    drop_px = land_top_y - cur_feet
    min_drop = max(4, TILE_SIZE // 2)
    max_drop = TILE_SIZE * 2 + 8
    if drop_px < min_drop or drop_px > max_drop:
        return False
    margin = max(6, enemy.rect.width // 4)
    left = min(enemy.rect.left + margin, int(lead_x) - margin)
    right = max(enemy.rect.right - margin, int(lead_x) + margin)
    path = pygame.Rect(
        left,
        cur_feet,
        max(1, right - left),
        drop_px + max(8, enemy.rect.height // 3),
    )
    spike_rects = world.spike_damage_rects()
    if any(path.colliderect(sr) for sr in spike_rects):
        return True
    land_feet = enemy._feet_rect_for_spike(
        pygame.Rect(
            int(lead_x) - enemy.rect.width // 2,
            land_top_y - enemy.rect.height,
            enemy.rect.width,
            enemy.rect.height,
        )
    )
    land_feet.bottom = land_top_y
    land_feet.top = land_top_y - 12
    return any(land_feet.colliderect(sr) for sr in spike_rects)


def calc_tank_flee_spikes(enemy, player, world, area_group, enemy_group=None) -> bool:
    """65840：踩刺或下一步會踩刺時離開，不主動靠近尖刺。"""
    from .enums import ActionTypes

    if not is_calc_tank_enemy(enemy):
        return False
    spd = int(round(enemy._effective_speed()))
    on_spike = enemy.feet_on_spike_damage(world)
    ahead = enemy._would_overlap_spike_damage_feet(world, spd * enemy.direction)
    if not on_spike and not ahead:
        return False
    enemy._try_step_off_spikes(world)
    ai_left = enemy.direction == -1
    ai_right = enemy.direction == 1
    ai_left, ai_right = enemy._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
    if not ai_left and not ai_right:
        enemy.direction *= -1
        ai_left = enemy.direction == -1
        ai_right = enemy.direction == 1
        ai_left, ai_right = enemy._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
    enemy._apply_chase_move(
        player, world, area_group, ai_left, ai_right,
        enemy_group=enemy_group, skip_ledge_brake=True,
    )
    enemy.update_action(ActionTypes.RUN if (ai_left or ai_right) else ActionTypes.IDLE)
    return True


def ai_calc_tank_priority_move(enemy, player, world, area_group, enemy_group=None) -> bool:
    """僅執行閃避／靠近積分移動，不追玩家、不衝撞。"""
    from .enums import ActionTypes

    now_ms = pygame.time.get_ticks()
    if calc_tank_flee_spikes(enemy, player, world, area_group, enemy_group):
        return True
    if not calc_tank_priority_active(enemy, now_ms):
        return False
    if getattr(enemy, "_bump_ticks_remaining", 0) > 0:
        enemy._bump_ticks_remaining = 0
        enemy._bump_damage_done = True
    ai_left = enemy.direction == -1
    ai_right = enemy.direction == 1
    ai_left, ai_right = enemy._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
    ai_left, ai_right, ledge = enemy._apply_chase_move(
        player,
        world,
        area_group,
        ai_left,
        ai_right,
        enemy_group=enemy_group,
        skip_ledge_brake=True,
    )
    if ledge:
        enemy.update_action(ActionTypes.IDLE)
    elif ai_left or ai_right:
        enemy.update_action(ActionTypes.RUN)
    else:
        enemy.update_action(ActionTypes.IDLE)
    return True


def _imaginary_drain(player, enemy, now_ms: int) -> None:
    if not player.is_alive:
        return
    dist = math.hypot(
        player.rect.centerx - enemy.rect.centerx,
        player.rect.centery - enemy.rect.centery,
    )
    if dist > TILE_SIZE * 5:
        return
    last = getattr(enemy, "_imaginary_drain_ms", 0)
    if now_ms - last < 1000:
        return
    enemy._imaginary_drain_ms = now_ms
    player.take_damage(player.max_health / 20.0)


def ai_imaginary(enemy, player, world, area_group, enemy_group=None) -> None:
    """虛數態：在玩家附近徘徊。"""
    from .enums import ActionTypes

    cx, cy = player.rect.centerx, player.rect.centery
    ex, ey = enemy.rect.centerx, enemy.rect.centery
    dist = math.hypot(cx - ex, cy - ey)
    orbit_r = TILE_SIZE * 3.2
    if dist > orbit_r * 1.6:
        ai_left = cx < ex - 4
        ai_right = cx > ex + 4
    else:
        tangent = (-(cy - ey) / max(dist, 1), (cx - ex) / max(dist, 1))
        ai_left = tangent[0] < -0.15
        ai_right = tangent[0] > 0.15
        if not ai_left and not ai_right:
            ai_left = enemy.direction == -1
            ai_right = enemy.direction == 1
    enemy.direction = 1 if cx >= ex else -1
    enemy.facing = enemy.direction
    ai_left, ai_right, ledge = enemy._apply_chase_move(
        player, world, area_group, ai_left, ai_right, enemy_group=enemy_group,
    )
    if ledge:
        enemy.update_action(ActionTypes.IDLE)
    elif ai_left or ai_right:
        enemy.update_action(ActionTypes.RUN)
    else:
        enemy.update_action(ActionTypes.IDLE)


def spawn_enemy_bullet_at_player(enemy, bullet_group, player) -> None:
    """敵人子彈瞄準玩家直線飛行。"""
    if bullet_group is None or player is None or not player.is_alive:
        return
    ox = enemy.rect.centerx + 0.6 * enemy.width * enemy.direction
    oy = enemy.rect.centery
    dx = float(player.rect.centerx - ox)
    dy = float(player.rect.centery - oy)
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        bullet_group.add(EnemyBullet(ox, oy, enemy.direction))
        return
    spd = float(EnemyBullet.SPEED)
    bullet = EnemyBullet(ox, oy, 1 if dx >= 0 else -1, vy=spd * dy / dist)
    bullet.vx = spd * dx / dist
    bullet_group.add(bullet)


def _spawn_enemy_bullet_toward(
    enemy_bullet_group,
    x: float,
    y: float,
    tx: float,
    ty: float,
    *,
    speed: float = 7.0,
    aim_jitter: int = 0,
) -> None:
    if aim_jitter:
        tx += random.randint(-aim_jitter, aim_jitter)
        ty += random.randint(-aim_jitter, aim_jitter)
    dx = float(tx) - float(x)
    dy = float(ty) - float(y)
    dist = math.hypot(dx, dy)
    if dist < 1.0:
        bullet = EnemyBullet(int(x), int(y), 1 if dx >= 0 else -1)
    else:
        vx = speed * dx / dist
        vy = speed * dy / dist
        bullet = EnemyBullet(int(x), int(y), 1 if vx >= 0 else -1, vy=vy)
        bullet.vx = vx
        bullet.vy = vy
    enemy_bullet_group.add(bullet)


def ai_area_sprayer(
    enemy, player, world, enemy_bullet_group, area_group, now_ms: int,
) -> bool:
    """暴走：僅對視野內靜止面積極大量瞄準射擊；無面積時回復直線追玩家。"""
    from .enums import ActionTypes

    target_area = None
    best_dist = float("inf")
    vision = pygame.Rect(0, 0, TILE_SIZE * 16, TILE_SIZE * 12)
    vision.center = enemy.rect.center
    if area_group is not None:
        for area in list(area_group):
            if not area.alive() or not area.is_stationary():
                continue
            if not vision.colliderect(area.rect):
                continue
            d = math.hypot(
                area.rect.centerx - enemy.rect.centerx,
                area.rect.centery - enemy.rect.centery,
            )
            if d < best_dist:
                best_dist = d
                target_area = area
    if target_area is None:
        return False

    from . import game_audio

    enemy.direction = 1 if target_area.rect.centerx >= enemy.rect.centerx else -1
    enemy.facing = enemy.direction
    burst_cd = AREA_SPRAYER_RAMPAGE_BURST_MS
    if now_ms < int(getattr(enemy, "_area_rampage_next_ms", 0)):
        enemy.update_action(ActionTypes.IDLE)
        return True
    enemy._area_rampage_next_ms = now_ms + burst_cd
    game_audio.play_area_rampage(at_rect=enemy.rect, enemy=enemy)
    ax, ay = target_area.rect.center
    for _ in range(AREA_SPRAYER_RAMPAGE_BULLETS):
        _spawn_enemy_bullet_toward(
            enemy_bullet_group,
            enemy.rect.centerx + random.randint(-8, 8),
            enemy.rect.centery + random.randint(-8, 8),
            ax,
            ay,
            aim_jitter=18,
        )
    enemy.update_action(ActionTypes.IDLE)
    return True


def ai_area_sprayer_chase(
    enemy,
    player,
    world,
    area_group,
    enemy_bullet_group=None,
    enemy_group=None,
) -> None:
    """直線朝玩家飛行（穿牆、無重力）；無靜止面積時以一般模式射擊玩家。"""
    from .enums import ActionTypes

    dx = float(player.rect.centerx - enemy.rect.centerx)
    dy = float(player.rect.centery - enemy.rect.centery)
    dist = math.hypot(dx, dy)
    enemy.direction = 1 if dx >= 0 else -1
    enemy.facing = enemy.direction
    if dist > 6:
        spd = float(enemy._effective_speed())
        enemy.rect.centerx += int(round(spd * dx / dist))
        enemy.rect.centery += int(round(spd * dy / dist))
    enemy.vel_y = 0.0
    enemy.is_in_air = False
    enemy.rect.x = max(0, min(SCREEN_WIDTH - enemy.rect.width, enemy.rect.x))
    enemy.rect.y = max(0, min(SCREEN_HEIGHT - enemy.rect.height, enemy.rect.y))
    enemy.update_action(ActionTypes.RUN if dist > 6 else ActionTypes.IDLE)
    if enemy_bullet_group is not None and player.is_alive and enemy.shoot_cooldown == 0:
        cd = max(3, effective_shoot_cooldown(enemy))
        if random.randint(1, cd) == 1:
            enemy.shoot(enemy_bullet_group, player_ref=player)


def _sin_wall_margin_px() -> int:
    return max(2, int(round(TILE_SIZE * SIN_WALL_MARGIN_TILES)))


def _sin_body_rect(enemy, dx: int = 0, dy: int = 0) -> pygame.Rect:
    body = enemy.rect.inflate(-6, -6)
    body.x += int(dx)
    body.y += int(dy)
    return body


def _sin_body_hits_wall(enemy, world, dx: int = 0, dy: int = 0) -> bool:
    margin = _sin_wall_margin_px()
    body = _sin_body_rect(enemy, dx, dy)
    for _img, rect in world.obstacle_list:
        expanded = rect.inflate(margin * 2, margin * 2)
        if body.colliderect(expanded):
            return True
    return False


def _sin_ceiling_too_close(enemy, world) -> bool:
    margin = _sin_wall_margin_px()
    body = _sin_body_rect(enemy)
    probe = pygame.Rect(body.x, body.top - margin - 1, body.width, margin + 2)
    return any(probe.colliderect(r) for _img, r in world.obstacle_list)


def _sin_wall_blocks_ahead(enemy, world, tiles_ahead: int, direction: int | None = None) -> bool:
    fwd = int(enemy.direction if direction is None else direction)
    if fwd == 0:
        fwd = 1
    for t in range(1, tiles_ahead + 1):
        if _sin_body_hits_wall(enemy, world, dx=fwd * t * TILE_SIZE, dy=0):
            return True
    return False


def _sin_wall_ahead_one_tile(enemy, world) -> bool:
    return _sin_wall_blocks_ahead(enemy, world, 1)


def _sin_ceiling_blocked(enemy, world, dy_up: int) -> bool:
    if dy_up >= 0:
        return False
    body = _sin_body_rect(enemy, 0, dy_up)
    head = pygame.Rect(body.x, body.top - TILE_SIZE, body.width, TILE_SIZE)
    return any(head.colliderect(r) for _img, r in world.obstacle_list)


def _sin_avoid_wall_direction(enemy, world, ai_left: bool, ai_right: bool) -> tuple[bool, bool]:
    """前方或頭頂將撞牆時改向，避免主動撞牆。"""
    if _sin_body_hits_wall(enemy, world):
        enemy.direction *= -1
        ai_left = enemy.direction < 0
        ai_right = enemy.direction > 0
    if ai_right and _sin_wall_blocks_ahead(enemy, world, 2, direction=1):
        enemy.direction = -1
        ai_left, ai_right = True, False
    elif ai_left and _sin_wall_blocks_ahead(enemy, world, 2, direction=-1):
        enemy.direction = 1
        ai_left, ai_right = False, True
    return ai_left, ai_right


def _sin_clamp_centerx(enemy, world, target_cx: float) -> float:
    """水平正弦偏移遇牆時縮限。"""
    body_w = max(8, enemy.width // 2)
    probe = pygame.Rect(
        int(target_cx - body_w),
        enemy.rect.centery - TILE_SIZE,
        body_w * 2,
        TILE_SIZE * 2,
    )
    if not any(probe.colliderect(r) for _img, r in world.obstacle_list):
        return target_cx
    margin_h = int(_sin_h_amp_px(enemy))
    lo = int(target_cx - margin_h)
    hi = int(target_cx + margin_h)
    best = float(enemy.rect.centerx)
    best_dist = abs(best - target_cx)
    for cx in range(lo, hi + 1, max(4, TILE_SIZE // 4)):
        probe.centerx = cx
        if any(probe.colliderect(r) for _img, r in world.obstacle_list):
            continue
        if abs(cx - target_cx) < best_dist:
            best = float(cx)
            best_dist = abs(cx - target_cx)
    return best


def _init_sin_wave_ranges(enemy) -> None:
    enemy._sin_h_range_tiles = random.uniform(SIN_H_RANGE_MIN_TILES, SIN_H_RANGE_MAX_TILES)
    enemy._sin_v_range_tiles = random.uniform(SIN_V_RANGE_MIN_TILES, SIN_V_RANGE_MAX_TILES)


def _sin_h_amp_px(enemy) -> float:
    tiles = float(getattr(enemy, "_sin_h_range_tiles", (SIN_H_RANGE_MIN_TILES + SIN_H_RANGE_MAX_TILES) * 0.5))
    return float(TILE_SIZE) * tiles * 0.5


def _sin_v_amp_px(enemy) -> float:
    tiles = float(getattr(enemy, "_sin_v_range_tiles", (SIN_V_RANGE_MIN_TILES + SIN_V_RANGE_MAX_TILES) * 0.5))
    return float(TILE_SIZE) * tiles


def _sin_axis_paused(enemy, now_ms: int, axis: str) -> bool:
    """30% 機率暫停該軸向移動 0.5s（冷卻 3s）；另一軸仍可動。"""
    if axis == "h":
        pause_key, cd_key, tick_key = (
            "_sin_h_pause_until_ms", "_sin_h_pause_cd_until_ms", "_sin_h_pause_tick_ms",
        )
    else:
        pause_key, cd_key, tick_key = (
            "_sin_v_pause_until_ms", "_sin_v_pause_cd_until_ms", "_sin_v_pause_tick_ms",
        )
    pause_until = int(getattr(enemy, pause_key, 0))
    if now_ms < pause_until:
        return True
    if int(getattr(enemy, tick_key, -1)) == now_ms:
        return False
    setattr(enemy, tick_key, now_ms)
    cd_until = int(getattr(enemy, cd_key, 0))
    if now_ms >= cd_until and random.random() < SIN_AXIS_PAUSE_CHANCE:
        setattr(enemy, pause_key, now_ms + SIN_AXIS_PAUSE_MS)
        setattr(enemy, cd_key, now_ms + SIN_AXIS_PAUSE_MS + SIN_AXIS_PAUSE_CD_MS)
        return True
    return False


def _sin_vertical_wave_limits(enemy, world) -> tuple[float, float]:
    """相對腳底的向上(負)／向下(正)最大偏移，遇牆則縮限（保留 0.3 格間距）。"""
    margin = _sin_wall_margin_px()
    amp = _sin_v_amp_px(enemy)
    max_up = amp
    max_down = amp
    cx = enemy.rect.centerx
    body_w = max(8, enemy.width // 2)
    for _img, rect in world.obstacle_list:
        if not rect.colliderect(
            pygame.Rect(cx - body_w, enemy.rect.top - TILE_SIZE * 3, body_w * 2, TILE_SIZE * 4)
        ):
            continue
        if rect.bottom <= enemy.rect.centery + 4:
            allow_up = enemy.rect.bottom - rect.bottom - margin
            if allow_up >= 0:
                max_up = min(max_up, allow_up)
        if rect.top >= enemy.rect.centery - 4:
            allow_down = rect.top - enemy.rect.bottom - margin
            if allow_down >= 0:
                max_down = min(max_down, allow_down)
    return max_up, max_down


def ai_sin_wave_move(
    enemy, player, world, area_group, now_ms: int,
) -> tuple[bool, bool]:
    """與玩家保持 2～3 格；水平前後來回；主動避開牆與天花板。"""
    dx = player.rect.centerx - enemy.rect.centerx
    dist = abs(dx)
    min_px = TILE_SIZE * SIN_STANDOFF_MIN_TILES
    max_px = TILE_SIZE * SIN_STANDOFF_MAX_TILES
    toward_player = dx > 0

    enemy._sin_t = getattr(enemy, "_sin_t", 0.0) + SIN_HORIZONTAL_PHASE_STEP
    if dist > max_px:
        enemy.direction = 1 if toward_player else -1
    elif dist < min_px:
        enemy.direction = -1 if toward_player else 1
    else:
        wave_dir = math.cos(enemy._sin_t)
        if toward_player:
            enemy.direction = 1 if wave_dir >= 0 else -1
        else:
            enemy.direction = -1 if wave_dir >= 0 else 1

    if enemy.direction == 0:
        enemy.direction = 1 if dx >= 0 else -1

    ai_left = enemy.direction < 0
    ai_right = enemy.direction > 0
    ai_left, ai_right = _sin_avoid_wall_direction(enemy, world, ai_left, ai_right)

    if _sin_axis_paused(enemy, now_ms, "h"):
        return False, False
    return ai_left, ai_right


def apply_sin_horizontal_oscillation(enemy, player, world, now_ms: int) -> None:
    """水平左右來回（每隻怪隨機 3～6 格峰值間距）。"""
    if _sin_axis_paused(enemy, now_ms, "h"):
        return
    to_player = 1 if player.rect.centerx >= enemy.rect.centerx else -1
    last_h = float(getattr(enemy, "_sin_last_off_h", 0.0))
    chase_cx = float(enemy.rect.centerx) - last_h * to_player
    enemy._sin_phase_h = float(getattr(enemy, "_sin_phase_h", 0.0)) + SIN_HORIZONTAL_PHASE_STEP
    amp = _sin_h_amp_px(enemy)
    off_h = math.sin(enemy._sin_phase_h) * amp
    target_cx = chase_cx + off_h * to_player
    if not _sin_body_hits_wall(enemy, world, int(round(target_cx - enemy.rect.centerx)), 0):
        enemy.rect.centerx = int(round(target_cx))
        enemy._sin_last_off_h = off_h
    enemy.rect.x = max(0, min(SCREEN_WIDTH - enemy.rect.width, enemy.rect.x))


def apply_sin_wave_motion(enemy, player, world, now_ms: int) -> None:
    """垂直正弦波動（每隻怪隨機 1～2 格，相位速度 ×2）。"""
    if getattr(enemy, "_sin_anchor_bottom", None) is None:
        enemy._sin_anchor_bottom = int(enemy.rect.bottom)
    last_v = float(getattr(enemy, "_sin_last_off_y", 0.0))
    if _sin_axis_paused(enemy, now_ms, "v"):
        enemy.rect.bottom = int(enemy._sin_anchor_bottom) + int(round(last_v))
        enemy.vel_y = 0.0
        enemy.is_in_air = False
        return

    enemy._sin_phase_v = float(getattr(enemy, "_sin_phase_v", 0.0)) + SIN_VERTICAL_PHASE_STEP
    t = float(enemy._sin_phase_v)
    amp = _sin_v_amp_px(enemy)
    chase_bottom = float(enemy.rect.bottom) - last_v
    enemy._sin_anchor_bottom = int(round(chase_bottom))

    off_v = math.sin(t) * amp
    if random.randint(1, 200) == 1:
        off_v += random.choice([-1, 1]) * TILE_SIZE * 0.35
    max_up, max_down = _sin_vertical_wave_limits(enemy, world)
    if off_v < 0:
        off_v = max(-max_up, off_v)
    else:
        off_v = min(max_down, off_v)
    off_v = max(-amp, min(amp, off_v))
    trial_dy = int(round(off_v)) - int(round(last_v))
    if trial_dy < 0 and (_sin_ceiling_blocked(enemy, world, trial_dy) or _sin_ceiling_too_close(enemy, world)):
        off_v = min(off_v, last_v)
        if off_v > last_v:
            off_v = last_v
    elif trial_dy > 0 and _sin_body_hits_wall(enemy, world, 0, trial_dy):
        off_v = last_v
    enemy._sin_last_off_y = off_v

    enemy.rect.bottom = int(enemy._sin_anchor_bottom) + int(round(off_v))
    if _sin_ceiling_too_close(enemy, world):
        enemy.rect.y += _sin_wall_margin_px()
    enemy.vel_y = 0.0
    enemy.is_in_air = False
    enemy.rect.x = max(0, min(SCREEN_WIDTH - enemy.rect.width, enemy.rect.x))
    enemy.rect.y = max(0, min(SCREEN_HEIGHT - enemy.rect.height, enemy.rect.y))


def try_exp_flyer_player_touch(player, enemy) -> bool:
    """玩家碰到 e^x（131449）：怪物消失，玩家僅能使用積分模式。"""
    if not is_exp_flyer_enemy(enemy) or not enemy.is_alive or not player.is_alive:
        return False
    if not enemy._melee_body_overlaps_player(player):
        return False
    from . import game_audio

    enemy.health = 0.0
    enemy.is_alive = False
    game_audio.stop_enemy_sfx(enemy)
    enemy.kill()
    return True


def ai_exp_flyer(enemy, player, world, area_group, enemy_group) -> None:
    """直線朝玩家移動＋近戰衝撞（同 65834）。"""
    from .constants import ENEMY_BULLET_DAMAGE
    from .enums import ActionTypes

    dx = float(player.rect.centerx - enemy.rect.centerx)
    dy = float(player.rect.centery - enemy.rect.centery)
    dist = math.hypot(dx, dy)
    enemy.direction = 1 if dx >= 0 else -1
    enemy.facing = enemy.direction
    now = pygame.time.get_ticks()

    if dist > 6:
        spd = float(enemy._effective_speed())
        enemy.rect.centerx += int(round(spd * dx / dist))
        enemy.rect.centery += int(round(spd * dy / dist))
    enemy.vel_y = 0.0
    enemy.is_in_air = False

    if enemy._melee_in_attack_range(player):
        enemy._try_melee_contact_damage(player, now)

    if enemy._bump_ticks_remaining > 0:
        enemy._bump_ticks_remaining -= 1
        spd = max(5, int(round(enemy._effective_speed() * 2.5)))
        step = int(round(spd * enemy.direction))
        if step:
            enemy.rect.x += step
        if player.is_alive and not enemy._bump_damage_done:
            if enemy._melee_in_attack_range(player):
                player.take_damage(ENEMY_BULLET_DAMAGE)
                enemy._bump_damage_done = True
                enemy._melee_touch_ms = now
        enemy.update_action(ActionTypes.RUN)
        return

    if (
        enemy._bump_ticks_remaining <= 0
        and now >= enemy._bump_next_ready_ms
        and dist < TILE_SIZE * 3
        and player.is_alive
    ):
        enemy._bump_ticks_remaining = 18
        enemy._bump_damage_done = False
        enemy._bump_next_ready_ms = now + 1200
        from . import game_audio

        game_audio.play_monster_attack_if_visible(enemy.rect, enemy)

    enemy.update_action(ActionTypes.RUN if dist > 6 else ActionTypes.IDLE)


def after_enemy_move_wall_check(enemy, world, now_ms: int) -> None:
    if not is_sin_wave_enemy(enemy) or sin_wave_lunge_active(enemy):
        return
    body = enemy.rect.inflate(-6, -6)
    if any(body.colliderect(r) for _img, r in world.obstacle_list):
        _begin_sin_wave_stun(enemy, now_ms)


def display_label(enemy) -> str:
    if is_calc_tank_enemy(enemy):
        return _calc_tank_label(enemy)
    if getattr(enemy, "head_label", None):
        return str(enemy.head_label)
    if getattr(enemy, "math_label", None):
        return str(enemy.math_label)
    return f"{enemy.health:.2f}"


def blit_enemy_head_label(screen, font, enemy, color=(255, 255, 255)) -> None:
    """繪製頭上標籤；e^x 用上標 x 避免缺字。"""
    from .fonts import get_font

    label = display_label(enemy)
    cx = enemy.rect.centerx
    base_y = enemy.rect.top - 6
    if is_exp_flyer_enemy(enemy) and label in ("e^x", "eˣ"):
        e_img = font.render("e", True, color)
        x_font = get_font(max(12, int(font.get_height() * 0.7)), bold=True)
        x_img = x_font.render("x", True, color)
        w = e_img.get_width() + x_img.get_width()
        h = max(e_img.get_height(), x_img.get_height() + 6)
        bg = pygame.Surface((w + 8, h + 4), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 140))
        x0 = cx - w // 2
        y0 = base_y - h
        screen.blit(bg, (x0 - 4, y0 - 2))
        screen.blit(e_img, (x0, y0 + h - e_img.get_height()))
        screen.blit(x_img, (x0 + e_img.get_width(), y0 + h - x_img.get_height() - 5))
        return
    hp_img = font.render(label, True, color)
    hp_rect = hp_img.get_rect(midbottom=(cx, base_y))
    bg = pygame.Surface((hp_rect.width + 8, hp_rect.height + 4), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 140))
    screen.blit(bg, (hp_rect.x - 4, hp_rect.y - 2))
    screen.blit(hp_img, hp_rect)
