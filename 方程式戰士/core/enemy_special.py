"""特殊敵人 AI、代數狀態、傷害過濾。"""
from __future__ import annotations

import math
import random

import pygame

from .constants import GRAVITY, SCREEN_HEIGHT, SCREEN_WIDTH, TILE_SIZE, WHITE
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
NEG_ONE_SHOOT_CD_MULT = 0.4
IMAGINARY_SINE_AMP_PX = 28.0
IMAGINARY_SINE_PERIOD_MS = 2200
# 子彈穿透虛數／−1 時仍顯示（略淡＋淡藍描邊）；過低會像「隱形彈」
PROJECTILE_PASS_THROUGH_ALPHA = 155
IMAGINARY_DRAIN_RANGE_PX = TILE_SIZE * 3.5
IMAGINARY_DRAIN_INTERVAL_MS = 1000
GIANT_HP_FACTOR_MIN = 4.0
GIANT_SCALE_FACTOR_MIN = 0.32
GIANT_SQRT_SHRINK_KEEP = 0.62
GIANT_ALGEBRA_SPEED_MULT = 1.2
GIANT_SQUARE_CHASE_SPEED_MULT = 1.2
GIANT_LOW_HP_THRESHOLD = 64.0
GIANT_LOW_HP_SPEED_MULT = 2.0
GIANT_LOW_HP_SQUARE_SENSE_PX = TILE_SIZE * 14
GIANT_PLAYER_AGGRO_RANGE_PX = TILE_SIZE * 3.0
GIANT_PLAYER_AGGRO_AFTER_HIT_MS = 4000
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
        or is_imaginary_enemy(enemy)
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


def tiny_fraction_kill(enemy) -> None:
    enemy.health = 0.0
    enemy.check_alive()


def enemy_collides_rect(enemy, other: pygame.Rect) -> bool:
    """子彈／方塊與敵人碰撞：以顯示碰撞箱為準。"""
    if not getattr(enemy, "is_alive", True):
        return False
    return enemy_body_rect(enemy).colliderect(other)


def apply_archetype_to_enemy(enemy) -> None:
    from .enemy_archetypes import archetype_for_gid

    arch = archetype_for_gid(enemy.enemy_gid)
    if arch is None:
        return
    enemy.max_health = float(arch.max_hp)
    enemy.health = float(arch.max_hp)
    enemy.head_label = arch.head_label
    enemy.label_suffix = arch.label_suffix
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
        _init_enemy_imaginary_state(enemy)
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
        enemy.invincible = False
        enemy.only_heal_bullet_hurt = False
        enemy.max_health = 99999.0
        enemy.health = min(float(enemy.health), 99999.0)
        configure_calc_tank_algebra_state(enemy)
    if enemy.enemy_gid == GID_GIANT_256:
        enemy._giant_base_max_hp = float(arch.max_hp)
        enemy._giant_base_speed_mult = float(arch.speed_mult)
        enemy._giant_base_scale = float(arch.scale_mult)
        enemy._giant_hp_factor = 1.0
        enemy._giant_scale_factor = 1.0
        enemy._giant_algebra_speed_mult = 1.0
        enemy._giant_grown_until_ms = 0
        enemy._giant_reverting = False
        enemy._giant_player_aggro_until_ms = 0


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


def is_imaginary_enemy(enemy) -> bool:
    return getattr(enemy, "ai_kind", "") == "imaginary"


def projectile_passes_through_enemy(enemy, proj) -> bool:
    """虛數 i 或 −1 對非治療彈：子彈穿透不阻擋。"""
    if not enemy.is_alive:
        return False
    if is_imaginary_enemy(enemy):
        return True
    if getattr(enemy, "only_heal_bullet_hurt", False):
        return not _projectile_is_healing(proj)
    return False


def mark_projectile_passed_through(proj) -> None:
    """穿透虛數／−1：子彈繼續飛行，略透明並加淡藍圈（避免像隱形彈）。"""
    target = PROJECTILE_PASS_THROUGH_ALPHA
    if int(getattr(proj, "_pass_through_ghost_alpha", 255)) <= target:
        return
    proj._pass_through_ghost_alpha = target
    base = proj.image.copy()
    base.set_alpha(target)
    w, h = base.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    out.blit(base, (0, 0))
    cx, cy = w // 2, h // 2
    r = max(3, min(cx, cy) - 1)
    pygame.draw.circle(out, (160, 210, 255, 200), (cx, cy), r, 2)
    proj.image = out


def can_take_projectile_damage(enemy, proj) -> bool:
    if not enemy.is_alive:
        return False
    if projectile_passes_through_enemy(enemy, proj):
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
    if is_calc_tank_enemy(enemy):
        enemy._head_label_cache = None
        if int(getattr(enemy, "_calc_tank_x_exp", 0)) == 0:
            enemy.head_label = str(int(round(float(enemy.health))))
    elif is_giant_colossus_enemy(enemy):
        enemy._head_label_cache = None
        enemy.head_label = str(int(round(float(enemy.health))))
        notify_giant_player_aggro(enemy)


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


def is_tiny_fraction_enemy(enemy) -> bool:
    from .enemy_archetypes import is_tiny_fraction_enemy as _is_tiny

    return _is_tiny(enemy)


TINY_FRACTION_DODGE_MS = 100
TINY_FRACTION_DODGE_SPEED = 16
TINY_FRACTION_DODGE_COOLDOWN_MS = 140
_TINY_DODGE_DIRS = (
    (-1, 0), (1, 0), (0, -1), (0, 1),
    (-1, -1), (1, -1), (-1, 1), (1, 1),
)


def _projectile_screen_velocity(proj) -> tuple[float, float]:
    from .enums import PowerType
    from .projectile import MathProjectile, NumericProjectile

    if isinstance(proj, NumericProjectile):
        return float(proj.SPEED * proj.dx), float(-proj.SPEED * proj.dy)
    if isinstance(proj, MathProjectile):
        if proj.power == PowerType.LINEAR and proj.direction is not None:
            dx, dy = proj.direction
            sp = float(MathProjectile.SPEED_PX)
            return dx * sp, -dy * sp
        return float(MathProjectile.SPEED_PX * proj.facing), 0.0
    return 0.0, 0.0


def _projectile_threatens_enemy(proj, enemy) -> bool:
    if not getattr(proj, "alive", lambda: True)():
        return False
    body = enemy_body_rect(enemy)
    sense = body.inflate(96, 72)
    if not sense.colliderect(proj.rect):
        return False
    vx, vy = _projectile_screen_velocity(proj)
    if abs(vx) < 0.5 and abs(vy) < 0.5:
        return False
    to_x = float(body.centerx - proj.rect.centerx)
    to_y = float(body.centery - proj.rect.centery)
    return to_x * vx + to_y * vy > 0.0


def _tiny_fraction_begin_dodge(enemy, vx: float, vy: float, world, area_group, enemy_group, player, now_ms: int) -> bool:
    best: tuple[int, int] | None = None
    best_score = -1e9
    for dx_dir, dy_dir in _TINY_DODGE_DIRS:
        step_x = dx_dir * TINY_FRACTION_DODGE_SPEED
        step_y = dy_dir * TINY_FRACTION_DODGE_SPEED
        trial = enemy.rect.move(step_x, step_y)
        if enemy._solid_body_blocks_rect(trial, world, area_group, enemy_group, player):
            continue
        away = -(dx_dir * vx + dy_dir * vy)
        score = away + random.random() * 0.05
        if score > best_score:
            best_score = score
            best = (step_x, step_y)
    if best is None:
        return False
    enemy._tiny_dodge_until_ms = now_ms + TINY_FRACTION_DODGE_MS
    enemy._tiny_dodge_dx = best[0]
    enemy._tiny_dodge_dy = best[1]
    enemy._tiny_dodge_cd_until_ms = now_ms + TINY_FRACTION_DODGE_COOLDOWN_MS
    return True


def tiny_fraction_bullet_dodge_step(
    enemy,
    projectile_group,
    numeric_group,
    world,
    area_group,
    enemy_group,
    player,
    now_ms: int,
) -> bool:
    """65820：偵測逼近子彈並短距離閃避（不閃平方／根號）。回傳 True 表示本帧已處理移動。"""
    from .enums import ActionTypes

    if not is_tiny_fraction_enemy(enemy) or not enemy.is_alive:
        return False

    if now_ms < int(getattr(enemy, "_tiny_dodge_until_ms", 0)):
        dx = int(getattr(enemy, "_tiny_dodge_dx", 0))
        dy = int(getattr(enemy, "_tiny_dodge_dy", 0))
        enemy.rect.x += dx
        enemy.rect.y += dy
        if not getattr(enemy, "ghost_walls", False):
            enemy._depenetrate_world_obstacles_only(world)
        enemy.update_action(ActionTypes.RUN)
        return True

    if now_ms < int(getattr(enemy, "_tiny_dodge_cd_until_ms", 0)):
        return False

    threats: list = []
    if projectile_group is not None:
        threats.extend(list(projectile_group))
    if numeric_group is not None:
        threats.extend(list(numeric_group))

    for proj in threats:
        if not _projectile_threatens_enemy(proj, enemy):
            continue
        vx, vy = _projectile_screen_velocity(proj)
        if _tiny_fraction_begin_dodge(enemy, vx, vy, world, area_group, enemy_group, player, now_ms):
            enemy.rect.x += int(enemy._tiny_dodge_dx)
            enemy.rect.y += int(enemy._tiny_dodge_dy)
            if not getattr(enemy, "ghost_walls", False):
                enemy._depenetrate_world_obstacles_only(world)
            enemy.update_action(ActionTypes.RUN)
            return True
    return False


def is_giant_colossus_enemy(enemy) -> bool:
    return int(getattr(enemy, "enemy_gid", 0)) == GID_GIANT_256


def player_on_giant_head(player, enemy) -> bool:
    """玩家站在臨界巨像頭頂（不應受近戰／碾壓傷害）。"""
    if not is_giant_colossus_enemy(enemy):
        return False
    body = enemy_body_rect(enemy)
    overlap_w = min(player.rect.right, body.right) - max(player.rect.left, body.left)
    min_w = max(6, int(player.rect.width * 0.22))
    if overlap_w < min_w:
        return False
    dy = player.rect.bottom - body.top
    return -12 <= dy <= 18 and player.rect.centery <= body.centery


def giant_colossus_is_crush_hazard(enemy) -> bool:
    """平方變大後（或待壓扁狀態）的巨像會碾玩家。"""
    if not is_giant_colossus_enemy(enemy) or not getattr(enemy, "is_alive", True):
        return False
    if getattr(enemy, "pending_crush_player", False):
        return True
    return float(getattr(enemy, "_giant_scale_factor", 1.0)) > 1.01


def _giant_normal_speed_mult(enemy) -> float:
    """體型越大越慢；根號累積 ×1.2、平方累積 ÷1.2。"""
    base_spd = float(getattr(enemy, "_giant_base_speed_mult", 0.25))
    sc_f = max(GIANT_SCALE_FACTOR_MIN, float(getattr(enemy, "_giant_scale_factor", 1.0)))
    alg = float(getattr(enemy, "_giant_algebra_speed_mult", 1.0))
    return max(0.08, base_spd * (1.0 / sc_f) * alg)


def _giant_chase_speed_mult(enemy) -> float:
    """追平方塊或低血量時的額外速度倍率。"""
    spd = _giant_normal_speed_mult(enemy)
    low_hp = float(enemy.health) < GIANT_LOW_HP_THRESHOLD
    if low_hp:
        return spd * GIANT_LOW_HP_SPEED_MULT
    return spd * GIANT_SQUARE_CHASE_SPEED_MULT


def notify_giant_player_aggro(enemy, now_ms: int | None = None) -> None:
    """玩家攻擊巨像後，短時間內改為優先追玩家。"""
    if not is_giant_colossus_enemy(enemy):
        return
    if now_ms is None:
        now_ms = pygame.time.get_ticks()
    enemy._giant_player_aggro_until_ms = int(now_ms) + GIANT_PLAYER_AGGRO_AFTER_HIT_MS


def _giant_should_prioritize_player(enemy, player, now_ms: int) -> bool:
    if float(enemy.health) < GIANT_LOW_HP_THRESHOLD:
        return False
    if not player.is_alive:
        return False
    dist = math.hypot(
        player.rect.centerx - enemy.rect.centerx,
        player.rect.centery - enemy.rect.centery,
    )
    if dist <= GIANT_PLAYER_AGGRO_RANGE_PX:
        return True
    return int(now_ms) < int(getattr(enemy, "_giant_player_aggro_until_ms", 0))


def _giant_has_los_to_rect(enemy, target_rect: pygame.Rect, world) -> bool:
    """巨像與目標之間無地圖實心磚（牆後方不可見）。"""
    from .perf import iter_obstacles_in_probe

    ex, ey = enemy.rect.centerx, enemy.rect.centery
    bx, by = target_rect.centerx, target_rect.centery
    dist = math.hypot(bx - ex, by - ey)
    if dist < 1.0:
        return True
    steps = max(2, min(24, int(dist // 20)))
    los_box = pygame.Rect(min(ex, bx), min(ey, by), abs(bx - ex) + 1, abs(by - ey) + 1)
    los_box.inflate_ip(16, 16)
    nearby_walls = [rect for _img, rect in iter_obstacles_in_probe(world.obstacle_list, los_box)]
    for i in range(1, steps):
        t = i / steps
        x = int(ex + (bx - ex) * t)
        y = int(ey + (by - ey) * t)
        probe = pygame.Rect(x - 4, y - 4, 8, 8)
        if any(probe.colliderect(rect) for rect in nearby_walls):
            return False
    return True


def _giant_scan_nearest_square_block(
    enemy,
    blocks,
    world,
    *,
    max_dist: float | None = None,
    require_los: bool = True,
):
    from .calculus_blocks import CalculusBlock

    best = None
    best_dist = float("inf")
    for block in blocks:
        if not isinstance(block, CalculusBlock):
            continue
        if getattr(block, "kind", None) != "square" or not block.alive():
            continue
        if require_los and not _giant_has_los_to_rect(enemy, block.rect, world):
            continue
        d = math.hypot(
            block.rect.centerx - enemy.rect.centerx,
            block.rect.centery - enemy.rect.centery,
        )
        if max_dist is not None and d > max_dist:
            continue
        if d < best_dist:
            best_dist = d
            best = block
    return best


def _giant_square_block_ai(enemy, world, area_group) -> bool:
    """可視線內的平方塊：平時 ×1.2；HP<64 時 ×2 並只找附近。"""
    blocks = tuple(getattr(enemy, "_nearby_square_blocks", ()))
    low_hp = float(enemy.health) < GIANT_LOW_HP_THRESHOLD
    max_dist = float(GIANT_LOW_HP_SQUARE_SENSE_PX) if low_hp else None
    if low_hp and max_dist is not None:
        blocks = tuple(
            b for b in blocks
            if math.hypot(
                b.rect.centerx - enemy.rect.centerx,
                b.rect.centery - enemy.rect.centery,
            ) <= max_dist
        )
    target = _giant_scan_nearest_square_block(
        enemy, blocks, world, max_dist=max_dist, require_los=True,
    )
    if target is None and low_hp:
        target = _giant_scan_nearest_square_block(
            enemy, blocks, world, max_dist=max_dist, require_los=False,
        )
    if target is None:
        if low_hp:
            enemy._giant_square_chase = True
            enemy.speed_mult = _giant_chase_speed_mult(enemy)
            if not getattr(enemy, "_giant_low_hp_patrol_dir", 0):
                enemy._giant_low_hp_patrol_dir = enemy.direction or 1
            enemy.direction = int(enemy._giant_low_hp_patrol_dir)
            enemy.facing = enemy.direction
            return True
        enemy._giant_square_chase = False
        enemy.speed_mult = _giant_normal_speed_mult(enemy)
        return False
    enemy._giant_square_chase = True
    enemy.speed_mult = _giant_chase_speed_mult(enemy)
    toward = 1 if target.rect.centerx >= enemy.rect.centerx else -1
    enemy.direction = toward
    enemy.facing = toward
    if low_hp:
        enemy._giant_low_hp_patrol_dir = toward
    return True


def _giant_run_square_chase_move(enemy, player, world, area_group, enemy_group, *, low_hp: bool) -> None:
    """朝平方塊方向移動；低血量時不讓玩家身體擋路。"""
    from .enums import ActionTypes

    if getattr(enemy, "_bump_ticks_remaining", 0) > 0:
        enemy._bump_ticks_remaining = 0
        enemy._bump_damage_done = True
    ai_left = enemy.direction == -1
    ai_right = enemy.direction == 1
    ai_left, ai_right = enemy._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
    if not (ai_left or ai_right) and low_hp:
        enemy.direction *= -1
        enemy._giant_low_hp_patrol_dir = enemy.direction
        ai_left = enemy.direction == -1
        ai_right = enemy.direction == 1
    ai_left, ai_right, ledge = enemy._apply_chase_move(
        player,
        world,
        area_group,
        ai_left,
        ai_right,
        enemy_group=enemy_group,
        skip_ledge_brake=True,
        ignore_player_block=low_hp,
    )
    if ledge:
        enemy.update_action(ActionTypes.IDLE)
    elif ai_left or ai_right:
        enemy.update_action(ActionTypes.RUN)
    else:
        enemy.update_action(ActionTypes.IDLE)


def giant_square_chase_active(enemy) -> bool:
    return bool(getattr(enemy, "_giant_square_chase", False))


def ai_giant_colossus(enemy, player, world, area_group, enemy_group=None) -> None:
    """臨界巨像：HP≥64 時玩家太近／剛被攻擊則優先玩家；HP<64 只追附近可見平方塊。"""
    from .enums import ActionTypes

    now_ms = pygame.time.get_ticks()
    low_hp = float(enemy.health) < GIANT_LOW_HP_THRESHOLD
    if not low_hp and _giant_should_prioritize_player(enemy, player, now_ms):
        enemy._giant_square_chase = False
        enemy.speed_mult = _giant_normal_speed_mult(enemy)
        enemy._ai_chase_contact_melee(player, world, area_group, enemy_group)
        return

    _giant_square_block_ai(enemy, world, area_group)
    if giant_square_chase_active(enemy):
        _giant_run_square_chase_move(
            enemy, player, world, area_group, enemy_group, low_hp=low_hp,
        )
        return
    enemy._ai_chase_contact_melee(player, world, area_group, enemy_group)


def enemy_blocks_player_physics(enemy) -> bool:
    """僅臨界巨像對玩家有實體碰撞。"""
    if not getattr(enemy, "is_alive", True):
        return False
    return is_giant_colossus_enemy(enemy)


def player_can_stand_on_enemy(enemy) -> bool:
    """穿透單位（幽靈、面積暴走、小數幽浮等）不可當腳下平台。"""
    if not getattr(enemy, "is_alive", True):
        return False
    if is_tiny_fraction_enemy(enemy):
        return False
    if getattr(enemy, "ghost_walls", False) or getattr(enemy, "ghost_area", False):
        return False
    if is_giant_colossus_enemy(enemy):
        return False
    return True


def enemy_body_rect(enemy) -> pygame.Rect:
    """與 draw() 顯示大小一致的碰撞箱。"""
    img = enemy.image
    if img is None:
        return enemy.rect.copy()
    h_scale = float(getattr(enemy, "_height_scale", 1.0))
    w, h = img.get_width(), img.get_height()
    if abs(h_scale - 1.0) > 0.02:
        w = max(1, int(w))
        h = max(1, int(h * h_scale))
    else:
        w, h = img.get_width(), img.get_height()
    body = pygame.Rect(0, 0, w, h)
    body.center = enemy.rect.center
    return body


CRUSH_ANIM_MS = 5200
CRUSH_FINAL_ZOOM = 0.52
CRUSH_VIEW_EDGE_LEFT = 0.92
CRUSH_VIEW_EDGE_RIGHT = 0.68
CRUSH_VIEW_EDGE_TOP = 0.85
CRUSH_VIEW_EDGE_BOTTOM = 0.62
CRUSH_MIN_HEIGHT_RATIO = 0.22


def _crush_viewport_t(now_ms: int, start_ms: int) -> float:
    raw = min(1.0, max(0.0, (int(now_ms) - int(start_ms)) / CRUSH_ANIM_MS))
    return raw * raw * (3.0 - 2.0 * raw)


def crush_viewport_anim_active(now_ms: int, start_ms: int) -> bool:
    if not start_ms:
        return False
    return (int(now_ms) - int(start_ms)) < CRUSH_ANIM_MS


def crush_viewport_done(now_ms: int, start_ms: int) -> bool:
    if not start_ms:
        return False
    return (int(now_ms) - int(start_ms)) >= CRUSH_ANIM_MS


def crush_viewport_sample_ms(now_ms: int, start_ms: int) -> int:
    """取樣時間（動畫結束後定格最後一幀，不重設）。"""
    if not start_ms:
        return int(now_ms)
    return min(int(now_ms), int(start_ms) + CRUSH_ANIM_MS)


def find_crush_landing_top_y(player, world, area_group=None, enemy_group=None) -> int | None:
    """找玩家腳下最近可站立面（含空中落下）。"""
    fx = int(player.rect.centerx)
    feet = int(player.rect.bottom)
    margin_x = max(8, int(player.rect.width * 0.28))
    search_down = max(960, int(getattr(player, "height", 32)) * 24)
    best: int | None = None

    def consider(top_y: int) -> None:
        nonlocal best
        ty = int(top_y)
        if ty < feet - 28:
            return
        if ty > feet + search_down:
            return
        if best is None or ty < best:
            best = ty

    for _, rect in world.obstacle_list:
        if rect.right < fx - margin_x or rect.left > fx + margin_x:
            continue
        consider(int(rect.top))

    if area_group is not None:
        for area in list(area_group):
            if area.rect.right < fx - margin_x or area.rect.left > fx + margin_x:
                continue
            sty = area.surface_top_at_world_x(fx)
            if sty is not None:
                consider(int(sty))

    if enemy_group is not None:
        for e in enemy_group:
            if not getattr(e, "is_alive", True) or not player_can_stand_on_enemy(e):
                continue
            er = enemy_body_rect(e)
            if er.right < fx - margin_x or er.left > fx + margin_x:
                continue
            consider(int(er.top))

    return best


def snap_player_to_ground_for_crush(player, world, area_group=None, enemy_group=None) -> bool:
    """空中被壓扁時落到最近地面；成功對齊腳底時回傳 True。"""
    target = find_crush_landing_top_y(player, world, area_group, enemy_group)
    if target is None:
        return False
    player.rect.bottom = int(target)
    player.vel_y = 0.0
    player.is_in_air = False
    player.is_jump = False
    player._airborne_since_ms = None
    player._long_fall_sfx_played = False
    return True


def prepare_player_crush_pose(player) -> None:
    """壓扁演出使用 Death 動畫（非 Idle）。"""
    from .enums import ActionTypes

    player.hurt_anim_active = False
    player.cast_anim_active = False
    player.cast_anim_hold_last = False
    player.update_action(ActionTypes.DEATH)
    frames = player.animation_list.get(ActionTypes.DEATH) or []
    if frames:
        player.frame_index = len(frames) - 1
        player.image = frames[player.frame_index]
        if hasattr(player, "_sync_sprite_size"):
            player._sync_sprite_size()


def draw_player_crush_squash(surface: pygame.Surface, player, now_ms: int) -> None:
    """壓扁演出：Death 動畫帧立刻压扁显示。"""
    from .enums import ActionTypes

    start = int(getattr(player, "crush_anim_start_ms", 0))
    if not start:
        player.draw(surface)
        return
    cx, _cy = getattr(player, "crush_anim_center", (player.rect.centerx, player.rect.centery))
    feet_y = int(getattr(player, "crush_anim_feet", player.rect.bottom))
    frames = player.animation_list.get(ActionTypes.DEATH) or []
    img = frames[min(player.frame_index, len(frames) - 1)] if frames else player.image
    if img is None:
        return
    if getattr(player, "is_x_flip", False):
        img = pygame.transform.flip(img, True, False)
    orig_w = max(1, img.get_width())
    orig_h = max(1, img.get_height())
    flat_h = max(2, int(orig_h * CRUSH_MIN_HEIGHT_RATIO))
    flat_w = max(4, orig_w)
    flat = pygame.transform.smoothscale(img, (flat_w, flat_h))
    dest = flat.get_rect(midbottom=(int(cx), feet_y))
    surface.blit(flat, dest)


def crush_death_ui_layout(
    view_x: int,
    view_y: int,
    view_w: int,
    view_h: int,
    scale: float,
    btn_w: int,
    btn_h: int,
) -> tuple[pygame.Rect, pygame.Rect]:
    """視窗座標：YOU DIED 與復活按鈕（壓扁鏡頭結束後疊在視窗上）。"""
    cx = view_x + view_w // 2
    cy = view_y + view_h // 2
    bw = max(80, int(btn_w * scale))
    bh = max(32, int(btn_h * scale))
    msg_y = cy - int(60 * scale)
    btn_rect = pygame.Rect(cx - bw // 2, cy + int(10 * scale), bw, bh)
    msg_rect = pygame.Rect(view_x, msg_y - 40, view_w, 80)
    return msg_rect, btn_rect


def draw_crush_death_ui_on_window(
    window: pygame.Surface,
    font_large,
    font_med,
    btn_bg,
    msg_rect: pygame.Rect,
    btn_rect: pygame.Rect,
) -> None:
    msg = font_large.render("YOU DIED", True, WHITE)
    window.blit(msg, msg.get_rect(center=msg_rect.center))
    if btn_bg is not None:
        bg = pygame.transform.smoothscale(btn_bg, (btn_rect.w, btn_rect.h))
        window.blit(bg, btn_rect.topleft)
    else:
        from .constants import DARK_GRAY

        pygame.draw.rect(window, DARK_GRAY, btn_rect)
        pygame.draw.rect(window, WHITE, btn_rect, 2)
    label = font_med.render("復活", True, WHITE)
    window.blit(label, label.get_rect(center=btn_rect.center))


def build_crush_viewport_surface(
    screen: pygame.Surface,
    cx: int,
    cy: int,
    screen_w: int,
    screen_h: int,
    now_ms: int,
    start_ms: int,
    *,
    pad_color: tuple[int, int, int] = (0, 0, 0),
) -> pygame.Surface:
    """地圖顯示區四邊以不同速率收斂；最終 crop 以玩家為中心（含黑邊補畫）。"""
    sample_ms = crush_viewport_sample_ms(now_ms, start_ms)
    t = _crush_viewport_t(sample_ms, start_ms)
    final_w = max(32, int(screen_w * CRUSH_FINAL_ZOOM))
    final_h = max(32, int(screen_h * CRUSH_FINAL_ZOOM))
    end_l = int(cx) - final_w // 2
    end_t = int(cy) - final_h // 2
    end_r = int(cx) + final_w // 2
    end_b = int(cy) + final_h // 2

    t_l = min(1.0, t * CRUSH_VIEW_EDGE_LEFT)
    t_r = min(1.0, t * CRUSH_VIEW_EDGE_RIGHT)
    t_t = min(1.0, t * CRUSH_VIEW_EDGE_TOP)
    t_b = min(1.0, t * CRUSH_VIEW_EDGE_BOTTOM)

    left = int((1.0 - t_l) * 0 + t_l * end_l)
    top = int((1.0 - t_t) * 0 + t_t * end_t)
    right = int((1.0 - t_r) * screen_w + t_r * end_r)
    bottom = int((1.0 - t_b) * screen_h + t_b * end_b)
    crop_w = max(1, right - left)
    crop_h = max(1, bottom - top)

    frame = pygame.Surface((crop_w, crop_h))
    frame.fill(pad_color)
    visible = pygame.Rect(left, top, crop_w, crop_h).clip(pygame.Rect(0, 0, screen_w, screen_h))
    if visible.width > 0 and visible.height > 0:
        frame.blit(
            screen,
            (visible.x - left, visible.y - top),
            visible,
        )
    return frame


def crush_viewport_src_rect(
    cx: int,
    cy: int,
    screen_w: int,
    screen_h: int,
    now_ms: int,
    start_ms: int,
) -> pygame.Rect:
    """相容舊呼叫：回傳 build 用 crop 範圍（含可能超出螢幕的偏移）。"""
    sample_ms = crush_viewport_sample_ms(now_ms, start_ms)
    t = _crush_viewport_t(sample_ms, start_ms)
    final_w = max(32, int(screen_w * CRUSH_FINAL_ZOOM))
    final_h = max(32, int(screen_h * CRUSH_FINAL_ZOOM))
    end_l = int(cx) - final_w // 2
    end_t = int(cy) - final_h // 2
    end_r = int(cx) + final_w // 2
    end_b = int(cy) + final_h // 2
    t_l = min(1.0, t * CRUSH_VIEW_EDGE_LEFT)
    t_r = min(1.0, t * CRUSH_VIEW_EDGE_RIGHT)
    t_t = min(1.0, t * CRUSH_VIEW_EDGE_TOP)
    t_b = min(1.0, t * CRUSH_VIEW_EDGE_BOTTOM)
    left = int((1.0 - t_l) * 0 + t_l * end_l)
    top = int((1.0 - t_t) * 0 + t_t * end_t)
    right = int((1.0 - t_r) * screen_w + t_r * end_r)
    bottom = int((1.0 - t_b) * screen_h + t_b * end_b)
    return pygame.Rect(left, top, max(1, right - left), max(1, bottom - top))


def begin_giant_crush_on_player(
    player,
    now_ms: int,
    *,
    frozen_scroll: int = 0,
    world=None,
    area_group=None,
    enemy_group=None,
) -> None:
    from . import game_audio

    if getattr(player, "crush_anim_start_ms", 0):
        return
    if world is not None:
        snap_player_to_ground_for_crush(player, world, area_group, enemy_group)
    prepare_player_crush_pose(player)
    player.giant_crush_flatten = True
    player.giant_crush_kill_at_ms = int(now_ms) + CRUSH_ANIM_MS
    player.crush_anim_center = (int(player.rect.centerx), int(player.rect.centery))
    player.crush_anim_feet = int(player.rect.bottom)
    player.crush_anim_start_ms = int(now_ms)
    player.crush_frozen_scroll = int(frozen_scroll)
    player.hurt_anim_active = False
    player.vel_y = 0.0
    player.is_in_air = False
    game_audio.play_giant_crush(at_rect=player.rect)
    game_audio.stop_bgm()


def try_apply_giant_crush(
    enemy,
    player,
    now_ms: int,
    *,
    frozen_scroll: int = 0,
    world=None,
    area_group=None,
    enemy_group=None,
) -> bool:
    """巨像變大後：玩家與其顯示碰撞箱重疊則進入壓扁（視野收斂）。"""
    if not is_giant_colossus_enemy(enemy):
        return False
    if not enemy.is_alive or not player.is_alive:
        if is_giant_colossus_enemy(enemy):
            enemy.pending_crush_player = False
        return False
    if not giant_colossus_is_crush_hazard(enemy):
        return False
    body = enemy_body_rect(enemy)
    if not player.rect.colliderect(body):
        return False
    if player_on_giant_head(player, enemy):
        return False
    enemy.pending_crush_player = False
    scroll = int(frozen_scroll) if frozen_scroll else int(getattr(player, "crush_frozen_scroll", 0))
    begin_giant_crush_on_player(
        player,
        now_ms,
        frozen_scroll=scroll,
        world=world,
        area_group=area_group,
        enemy_group=enemy_group,
    )
    return True


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
        if label == "0.0001":
            enemy.math_label = "0.01"
            enemy.head_label = "0.01"
            enemy.max_health = 0.01
            enemy.health = 0.01
            enemy.speed_mult = 10.0
            enemy.scale_mult = 0.1
            enemy.shoot_cd_mult = 1.0 / 3.0
            enemy.invincible = True
        elif label == "0.01":
            enemy.math_label = "0.1"
            enemy.head_label = "0.1"
            enemy.max_health = 0.1
            enemy.health = 0.1
            enemy.speed_mult = 1.0
            enemy.scale_mult = 1.0
            enemy.invincible = False
            enemy.shoot_cd_mult = 1.0 / 3.0
        elif label == "0.1":
            enemy.math_label = "0.01"
            enemy.head_label = "0.01"
            enemy.max_health = 0.01
            enemy.health = 0.01
            enemy.speed_mult = 10.0
            enemy.scale_mult = 0.1
            enemy.shoot_cd_mult = 1.0 / 3.0
            enemy.invincible = False
    elif kind == "square":
        if label == "0.01":
            enemy.math_label = "0.0001"
            enemy.head_label = "0.0001"
            enemy.max_health = 0.0001
            enemy.health = 0.0001
            enemy.invincible = True
            enemy.speed_mult = 10.0
            enemy.scale_mult = 0.1
            enemy.shoot_cd_mult = 1.0 / 5.0
    _refresh_appearance(enemy)


def _init_enemy_imaginary_state(enemy) -> None:
    """65823 預設為虛數 i 態（顯示 i、穿牆漂浮）。"""
    enemy.math_label = "i"
    enemy.head_label = "i"
    enemy.ghost_walls = True
    enemy.ghost_area = True
    enemy.alpha = 178
    enemy.only_heal_bullet_hurt = False
    enemy.ai_kind = "imaginary"
    enemy.vel_y = 0.0
    enemy.is_in_air = False
    enemy._imag_wave_phase = random.uniform(0.0, math.tau)
    enemy._imag_last_off_y = 0
    enemy._imag_wave_ms = pygame.time.get_ticks()
    enemy._imag_float_y = float(enemy.rect.centery)


def _neg_one_algebra(enemy, kind: str) -> None:
    label = getattr(enemy, "math_label", "i")
    if kind == "sqrt" and label == "-1":
        _init_enemy_imaginary_state(enemy)
    elif kind == "square" and label == "i":
        enemy.math_label = "-1"
        enemy.head_label = "-1"
        enemy.ghost_walls = False
        enemy.ghost_area = False
        enemy.alpha = 153
        enemy.only_heal_bullet_hurt = True
        enemy.ai_kind = "neg_one"


def _apply_giant_scaled_stats(enemy, *, hp_ratio: float | None = None) -> None:
    """依累積倍率更新巨像 HP／體型（不再定時還原）。"""
    base_hp = float(getattr(enemy, "_giant_base_max_hp", 512.0))
    base_sc = float(getattr(enemy, "_giant_base_scale", 2.0))
    base_spd = float(getattr(enemy, "_giant_base_speed_mult", 0.25))
    hp_f = max(GIANT_HP_FACTOR_MIN / base_hp, float(getattr(enemy, "_giant_hp_factor", 1.0)))
    sc_f = max(GIANT_SCALE_FACTOR_MIN, float(getattr(enemy, "_giant_scale_factor", 1.0)))
    enemy._giant_hp_factor = hp_f
    enemy._giant_scale_factor = sc_f
    old_max = float(enemy.max_health)
    old_hp = float(enemy.health)
    ratio = (old_hp / old_max) if old_max > 0 else 1.0
    if hp_ratio is not None:
        ratio = float(hp_ratio)
    enemy.max_health = max(GIANT_HP_FACTOR_MIN, base_hp * hp_f)
    enemy.health = min(enemy.max_health, max(1.0, enemy.max_health * ratio))
    enemy.scale_mult = max(GIANT_SCALE_FACTOR_MIN, base_sc * sc_f)
    enemy.speed_mult = _giant_normal_speed_mult(enemy)
    enemy.head_label = str(int(round(enemy.max_health)))
    enemy._giant_grown_until_ms = 0
    enemy._giant_reverting = False
    _refresh_appearance(enemy)


def _giant_algebra(enemy, kind: str) -> None:
    from . import game_audio

    if kind in ("square", "sqrt"):
        game_audio.play_giant_crush(at_rect=enemy.rect)
    alg_spd = float(getattr(enemy, "_giant_algebra_speed_mult", 1.0))
    if kind == "square":
        enemy.pending_crush_player = True
        enemy._giant_hp_factor = float(getattr(enemy, "_giant_hp_factor", 1.0)) * 2.0
        enemy._giant_scale_factor = float(getattr(enemy, "_giant_scale_factor", 1.0)) * 1.3
        enemy._giant_algebra_speed_mult = alg_spd / GIANT_ALGEBRA_SPEED_MULT
        _apply_giant_scaled_stats(enemy)
    elif kind == "sqrt":
        hp_f = float(getattr(enemy, "_giant_hp_factor", 1.0)) * 0.5
        sc_f = float(getattr(enemy, "_giant_scale_factor", 1.0))
        excess = max(0.0, sc_f - GIANT_SCALE_FACTOR_MIN)
        enemy._giant_hp_factor = max(GIANT_HP_FACTOR_MIN / float(getattr(enemy, "_giant_base_max_hp", 512.0)), hp_f)
        enemy._giant_scale_factor = GIANT_SCALE_FACTOR_MIN + excess * GIANT_SQRT_SHRINK_KEEP
        enemy._giant_algebra_speed_mult = alg_spd * GIANT_ALGEBRA_SPEED_MULT
        _apply_giant_scaled_stats(enemy)


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
    """虛數 i 近身光環傷害（非敵彈）；與穿透我方子彈無關。"""
    if not player.is_alive:
        return
    dist = math.hypot(
        player.rect.centerx - enemy.rect.centerx,
        player.rect.centery - enemy.rect.centery,
    )
    if dist > IMAGINARY_DRAIN_RANGE_PX:
        return
    last = getattr(enemy, "_imaginary_drain_ms", 0)
    if now_ms - last < IMAGINARY_DRAIN_INTERVAL_MS:
        return
    enemy._imaginary_drain_ms = now_ms
    player.take_damage(player.max_health / 20.0)
    player.center_notice_text = "虛數侵蝕"
    player.center_notice_until_ms = int(now_ms) + 700


def _apply_imaginary_sine_drift(enemy) -> None:
    """虛數態：疊加緩慢上下正弦偏移（穿牆時仍有效）。"""
    now_ms = pygame.time.get_ticks()
    last_ms = int(getattr(enemy, "_imag_wave_ms", now_ms))
    dt = max(0.0, (now_ms - last_ms) / 1000.0)
    enemy._imag_wave_ms = now_ms
    phase = float(getattr(enemy, "_imag_wave_phase", 0.0))
    period_s = max(0.2, IMAGINARY_SINE_PERIOD_MS / 1000.0)
    phase += dt * (2.0 * math.pi / period_s)
    enemy._imag_wave_phase = phase
    new_off = int(round(IMAGINARY_SINE_AMP_PX * math.sin(phase)))
    prev_off = int(getattr(enemy, "_imag_last_off_y", 0))
    enemy.rect.y += new_off - prev_off
    enemy._imag_last_off_y = new_off


def ai_imaginary(enemy, player, world, area_group, enemy_group=None) -> None:
    """虛數態：穿牆、子彈穿透，在玩家附近徘徊並上下正弦漂移。"""
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
    _apply_imaginary_sine_drift(enemy)
    enemy._imag_float_y = float(enemy.rect.centery)


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

    in_bump_range = dist < TILE_SIZE * 3 or enemy.rect.colliderect(player.rect)
    if (
        enemy._bump_ticks_remaining <= 0
        and now >= enemy._bump_next_ready_ms
        and in_bump_range
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
        if int(getattr(enemy, "_calc_tank_x_exp", 0)) == 0:
            return str(int(round(float(enemy.health))))
        return _calc_tank_label(enemy)
    if is_giant_colossus_enemy(enemy):
        return str(int(round(float(enemy.health))))
    if getattr(enemy, "head_label", None):
        return str(enemy.head_label)
    if getattr(enemy, "math_label", None):
        return str(enemy.math_label)
    suffix = getattr(enemy, "label_suffix", None)
    if suffix == "e^x":
        return f"{int(round(enemy.health))}e^x"
    return f"{enemy.health:.2f}"


def _render_exp_superscript_label(
    font,
    main_text: str,
    color: tuple[int, int, int],
    *,
    gap_after_main: int = 4,
) -> pygame.Surface:
    """主文字 + 上標 e^x（主文字可為空，僅顯示 e^x）。"""
    from .fonts import get_font

    parts: list[tuple[pygame.Surface, int, int]] = []
    x_off = 4
    y_pad = 2
    e_img = font.render("e", True, color)
    x_font = get_font(max(12, int(font.get_height() * 0.7)), bold=True)
    x_img = x_font.render("x", True, color)
    row_h = max(
        font.get_height(),
        e_img.get_height(),
        x_img.get_height() + 6,
    )
    baseline_bottom = y_pad + row_h
    if main_text:
        main_img = font.render(main_text, True, color)
        parts.append((main_img, x_off, baseline_bottom - main_img.get_height()))
        x_off += main_img.get_width() + gap_after_main
    e_y = baseline_bottom - e_img.get_height()
    x_y = baseline_bottom - x_img.get_height() - 5
    parts.append((e_img, x_off, e_y))
    parts.append((x_img, x_off + e_img.get_width(), x_y))
    w = x_off + e_img.get_width() + x_img.get_width() + 4
    surf_h = row_h + y_pad * 2
    surf = pygame.Surface((w, surf_h + 4), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 140))
    for img, px, py in parts:
        surf.blit(img, (px, py))
    return surf


def blit_enemy_head_label(screen, font, enemy, color=(255, 255, 255)) -> None:
    """繪製頭上標籤；e^x 用上標 x 避免缺字。標籤文字不變時重用快取 surface。"""
    from .enemy_archetypes import is_tiny_fraction_enemy

    label = display_label(enemy)
    draw_font = font
    if is_tiny_fraction_enemy(enemy):
        from .fonts import get_font

        draw_font = get_font(max(font.get_height(), 16), bold=True)
    cache_key = (label, color, draw_font.get_height())
    cached = getattr(enemy, "_head_label_cache", None)
    cx = enemy.rect.centerx
    base_y = enemy.rect.top - 6
    if cached is not None and cached.get("key") == cache_key:
        screen.blit(cached["surf"], cached["surf"].get_rect(midbottom=(cx, base_y)))
        return

    suffix = getattr(enemy, "label_suffix", None)
    if suffix == "e^x" and not getattr(enemy, "head_label", None):
        main_text = str(int(round(enemy.health)))
        surf = _render_exp_superscript_label(draw_font, main_text, color, gap_after_main=0)
        enemy._head_label_cache = {"key": cache_key, "surf": surf}
        screen.blit(surf, surf.get_rect(midbottom=(cx, base_y)))
        return
    if label in ("e^x", "eˣ"):
        surf = _render_exp_superscript_label(draw_font, "", color)
        enemy._head_label_cache = {"key": cache_key, "surf": surf}
        screen.blit(surf, surf.get_rect(midbottom=(cx, base_y)))
        return
    hp_img = draw_font.render(label, True, color)
    hp_rect = hp_img.get_rect(midbottom=(cx, base_y))
    surf = pygame.Surface((hp_rect.width + 8, hp_rect.height + 4), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 140))
    surf.blit(hp_img, (4, 2))
    enemy._head_label_cache = {"key": cache_key, "surf": surf}
    screen.blit(surf, surf.get_rect(midbottom=(cx, base_y)))
