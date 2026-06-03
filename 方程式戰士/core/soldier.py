"""Soldier base + Player + Enemy"""
import math
import random

import pygame

from .assets import load_soldier_action_frames
from .constants import (
    ENEMY_DEFAULT_MAX_HP,
    ENEMY_BULLET_DAMAGE,
    ENEMY_VISUAL_SCALE,
    GRAVITY,
    HP_DECIMAL_PLACES,
    JUMP_IMPULSE,
    PLAYER_MAX_HP,
    PLAYER_VISUAL_SCALE,
    SCROLL_THRESH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TILE_SIZE,
)
from .enums import ActionTypes, CharacterTypes, IntegralAxis, PlayerMode
from .gameplay import clamp_degree, round_hp
from .map_tile_loader import surface_for_gid
from .projectile import EnemyBullet

GID_CHASHER_MELEE_ENEMY = 65834

ENEMY_KENNEY_WALK_PAIR_GIDS = {
    65834: (65834, 65835),
    65840: (65840, 65841),
    65838: (65838, 65837),
    65820: (65820, 65819),
    65822: (65821, 65822),
    65823: (65823, 65824),
}

ENEMY_PAIR_ANIM_INTERVAL_MS = 350
ENEMY_PEER_GAP_TILES = 0.3
ENEMY_PEER_JUMP_CHANCE = 10  # 1/10 = 10%
ENEMY_PEER_JUMP_COOLDOWN_MS = 5000
ENEMY_PEER_RETREAT_CHANCE = 7  # 7/10 = 70%
ENEMY_PEER_RETREAT_COOLDOWN_MS = 1000

ENEMY_KENNEY_WALK_SEQUENCE_GIDS = {
    65843: (65843, 65844, 65845),
}

ENEMY_KENNEY_TILE_RGB = {
    65834: (255, 100, 100),
    65835: (255, 115, 105),
    65837: (235, 95, 105),
    65838: (245, 85, 95),
    65840: (240, 90, 90),
    65841: (235, 88, 92),
    65819: (250, 195, 115),
    65820: (255, 200, 120),
    65821: (175, 115, 250),
    65822: (180, 120, 255),
    65823: (120, 200, 255),
    65824: (115, 195, 250),
    131437: (200, 80, 80),
    65843: (100, 200, 255),
    65844: (110, 205, 255),
    65845: (120, 210, 255),
    131449: (255, 180, 100),
}


def player_standing_on_enemy_head(player, enemy) -> bool:
    """玩家踩在敵人頭頂（橫向足夠重疊、腳底貼敵頂）時為 True。"""
    overlap_w = min(player.rect.right, enemy.rect.right) - max(player.rect.left, enemy.rect.left)
    min_w = max(6, int(player.rect.width * 0.22))
    if overlap_w < min_w:
        return False
    dy = player.rect.bottom - enemy.rect.top
    return -8 <= dy <= 14


class Soldier(pygame.sprite.Sprite):
    """Player + Enemy 共用 base — 物理、動畫、生命"""
    STEP_UP_HEIGHT = 10
    GROUND_SNAP_PX = 6
    SIDE_COLLISION_TRIM = 6
    # 射線對齊：允許略為「陷入」地面再拉回、或懸空一小段再吸附
    GROUND_RAY_SNAP_UP_PX = 8
    GROUND_RAY_SNAP_DOWN_PX = 10
    SLOPE_NUDGE_PX = 3  # 水平受阻時先嘗試微幅上移（坡度容忍）
    LANDING_VEL_EPS = 0.85
    CEILING_DROP_PROBE_PX = 12
    CEILING_DROP_VEL_Y = 4.5
    PLAYER_TOP_BOUNCE = 0.42  # 撞螢幕頂後向下反彈

    def __init__(self, char_type, x, y, scale, speed):
        super().__init__()
        self.char_type = char_type
        self.max_health = 100
        self.health = self.max_health
        self.speed = speed
        self.vel_y = 0
        self.direction = 1
        self.facing = 1
        self.is_aiming = False
        self.is_alive = True
        self.is_jump = False
        self.is_in_air = True
        self.is_x_flip = False

        # AI
        self.move_counter = 0
        self.vision = pygame.Rect(0, 0, 220, 30)
        self.is_idling = False
        self.idling_counter = 0
        self.shoot_cooldown = 0
        self._airborne_since_ms: int | None = None
        self._long_fall_sfx_played = False

        self.action = ActionTypes.IDLE
        self.update_time = pygame.time.get_ticks()
        self.animation_cooldown = 100
        self.death_animation_cooldown = 45
        self.frame_index = 0
        self.animation_list = self._load_animations(scale)
        self.image = self.animation_list[self.action][self.frame_index]
        self.rect = self.image.get_rect(center=(x, y))
        self.width = self.image.get_width()
        self.height = self.image.get_height()

    def _load_animations(self, scale):
        anim = {}
        is_player = self.char_type == CharacterTypes.Player
        char_key = self.char_type.value
        for action in ActionTypes:
            anim[action] = load_soldier_action_frames(
                char_key, action.value, scale, is_player=is_player,
            )
        return anim

    def _is_flying_enemy(self) -> bool:
        if self.char_type != CharacterTypes.Enemy:
            return False
        from .enemy_special import is_flying_enemy

        return is_flying_enemy(self)

    def _collides_with_world_or_area(self, test_rect, world, area_group=None):
        ghost_walls = getattr(self, "ghost_walls", False)
        ghost_area = getattr(self, "ghost_area", False)
        if not ghost_walls:
            for _img, rect in world.obstacle_list:
                if rect.colliderect(test_rect):
                    return True
        if not ghost_area and area_group is not None:
            for area in list(area_group):
                if area.intersects_rect(test_rect):
                    return True
        return False

    def _solid_body_blocks_rect(self, test_rect, world, area_group, enemy_group=None, player_ref=None):
        if self._collides_with_world_or_area(test_rect, world, area_group):
            return True
        # 玩家與敵人：僅水平阻擋（見 move），垂直可穿越，避免跳躍時被擠進牆裡
        if self.char_type == CharacterTypes.Enemy and player_ref is not None:
            if player_ref.is_alive and player_ref.rect.colliderect(test_rect):
                return True
        return False

    def _depenetrate_world_obstacles_only(self, world):
        """僅對地圖磚：若仍與磚重疊，沿穿透最淺軸推出（例：頭頂先撞面積再與磚重疊）。"""
        if getattr(self, "ghost_walls", False):
            return
        for _ in range(10):
            orect = None
            for _img, r in world.obstacle_list:
                if r.colliderect(self.rect):
                    orect = r
                    break
            if orect is None:
                return
            overlap_x = min(self.rect.right, orect.right) - max(self.rect.left, orect.left)
            overlap_y = min(self.rect.bottom, orect.bottom) - max(self.rect.top, orect.top)
            if overlap_x <= 0 or overlap_y <= 0:
                return
            if overlap_x < overlap_y:
                if self.rect.centerx < orect.centerx:
                    self.rect.right = orect.left
                else:
                    self.rect.left = orect.right
            else:
                if self.rect.centery < orect.centery:
                    self.rect.bottom = orect.top
                else:
                    self.rect.top = orect.bottom
                    if self.vel_y < 0:
                        self.vel_y = 0

    def _support_top_at_foot_x(self, foot_x, bottom_y, world, area_group, snap_up, snap_down, enemy_group=None):
        """自腳下 x 對齊：找可站立面之最高 top（單柱射線）。"""
        best = None
        for _, rect in world.obstacle_list:
            if rect.left <= foot_x <= rect.right:
                gap = bottom_y - rect.top
                if -snap_up <= gap <= snap_down:
                    if best is None or rect.top > best:
                        best = rect.top
        if (
            self.char_type == CharacterTypes.Player
            and enemy_group is not None
            and self.vel_y >= 0
        ):
            for e in enemy_group:
                if not getattr(e, "is_alive", True):
                    continue
                er = e.rect
                if er.left <= foot_x <= er.right:
                    gap = bottom_y - er.top
                    if -snap_up <= gap <= snap_down and self.rect.bottom <= er.top + 10:
                        if best is None or er.top > best:
                            best = er.top
        if area_group is not None:
            for area in list(area_group):
                ar = area.rect
                if not (ar.left <= foot_x <= ar.right):
                    continue
                sty = area.surface_top_at_world_x(foot_x)
                if sty is None:
                    continue
                gap = bottom_y - sty
                if -snap_up <= gap <= snap_down:
                    if best is None or sty > best:
                        best = sty
        return best

    def _apply_ground_ray_alignment(self, world, area_group=None, enemy_group=None):
        """底部中心射線 + 邊緣備援：將 rect.bottom 對齊地面，鎖定垂直速度。"""
        if self.vel_y < -1.0:
            return False
        su, sd = self.GROUND_RAY_SNAP_UP_PX, self.GROUND_RAY_SNAP_DOWN_PX
        bottom = self.rect.bottom
        cx = self.rect.centerx
        target = self._support_top_at_foot_x(cx, bottom, world, area_group, su, sd, enemy_group)
        if target is None:
            margin = max(1, min(6, self.width // 5))
            sides = []
            for fx in (self.rect.left + margin, self.rect.right - margin):
                t = self._support_top_at_foot_x(fx, bottom, world, area_group, su, sd, enemy_group)
                if t is not None:
                    sides.append(t)
            if sides:
                target = max(sides)
        if target is None:
            return False
        delta = target - self.rect.bottom
        if abs(delta) <= sd + 1:
            self.rect.bottom = int(target)
            if self.vel_y > 0 or abs(self.vel_y) < self.LANDING_VEL_EPS:
                self.vel_y = 0
            return True
        return False

    def _try_slope_nudge_horizontal(self, dx, world, area_group, enemy_group=None, player_ref=None):
        """水平碰撞前：微幅上移嘗試上坡，減少與斜坡/階梯的拉扯。"""
        if dx == 0:
            return 0, 0
        for lift in range(1, self.SLOPE_NUDGE_PX + 1):
            cand = pygame.Rect(self.rect.x + dx, self.rect.y - lift, self.width, self.height)
            if not self._solid_body_blocks_rect(cand, world, area_group, enemy_group, player_ref):
                return dx, -lift
        return 0, 0

    def _ceiling_close_above(self, world, area_group, enemy_group=None, player_ref=None) -> bool:
        """頭頂附近已有實心（狹窄區跳躍頂到天花板）。"""
        margin = self.CEILING_DROP_PROBE_PX
        probe = pygame.Rect(self.rect.x, self.rect.top - margin, self.width, margin)
        return self._solid_body_blocks_rect(
            probe, world, area_group, enemy_group, player_ref,
        )

    def _resolve_vertical_against_solids(self, dy, world, area_group, enemy_group=None, player_ref=None):
        """單次合併垂直解析：避免多個磚塊迴圈反覆改 dy 造成邊緣抖動。"""
        hit_ceiling = False
        if dy == 0:
            return 0, hit_ceiling
        test = pygame.Rect(self.rect.x, self.rect.y + dy, self.width, self.height)
        if not self._solid_body_blocks_rect(test, world, area_group, enemy_group, player_ref):
            return dy, hit_ceiling

        if dy < 0:
            best = dy
            for _img, rect in world.obstacle_list:
                if rect.colliderect(test):
                    push = rect.bottom - self.rect.top
                    if push > best:
                        best = push
                        hit_ceiling = True
            if area_group is not None:
                for area in list(area_group):
                    if area.intersects_rect(test):
                        xs = (
                            self.rect.left + 2,
                            self.rect.centerx,
                            self.rect.right - 2,
                        )
                        lows = [area.surface_bottom_at_world_x(int(x)) for x in xs]
                        lows = [y for y in lows if y is not None]
                        underside = max(lows) if lows else area.rect.bottom - 1
                        ceiling_line = underside + 1
                        push = ceiling_line - self.rect.top
                        if push > best:
                            best = push
                            hit_ceiling = True
            if self.char_type == CharacterTypes.Enemy and player_ref is not None and player_ref.is_alive:
                if player_ref.rect.colliderect(test):
                    push = player_ref.rect.bottom - self.rect.top
                    if push > best:
                        best = push
                        hit_ceiling = True
            return best, hit_ceiling

        best = dy
        for _img, rect in world.obstacle_list:
            if rect.colliderect(test):
                sep = rect.top - self.rect.bottom
                if sep < best:
                    best = sep
        if area_group is not None:
            for area in list(area_group):
                if area.intersects_rect(test):
                    xs = (
                        self.rect.left + 2,
                        self.rect.centerx,
                        self.rect.right - 2,
                    )
                    tops = [area.surface_top_at_world_x(int(x)) for x in xs]
                    tops = [t for t in tops if t is not None]
                    surf_y = min(tops) if tops else area.rect.top
                    sep = surf_y - self.rect.bottom
                    if sep < best:
                        best = sep
        if self.char_type == CharacterTypes.Player and enemy_group is not None and dy > 0:
            for e in enemy_group:
                if not e.is_alive:
                    continue
                if not e.rect.colliderect(test):
                    continue
                if not player_standing_on_enemy_head(self, e):
                    overlap_w = min(self.rect.right, e.rect.right) - max(self.rect.left, e.rect.left)
                    if overlap_w < max(6, int(self.rect.width * 0.22)):
                        continue
                    if self.rect.bottom > e.rect.top + 14:
                        continue
                sep = e.rect.top - self.rect.bottom
                if sep < best:
                    best = sep
        if self.char_type == CharacterTypes.Enemy and player_ref is not None and player_ref.is_alive:
            if player_ref.rect.colliderect(test):
                sep = player_ref.rect.top - self.rect.bottom
                if sep < best:
                    best = sep
        if best < 0:
            best = 0
        return best, hit_ceiling

    def _feet_rect_for_spike(self, body: pygame.Rect | None = None) -> pygame.Rect:
        """腳底帶（與地刺傷害／避刺判定一致）。"""
        r = self.rect if body is None else body
        margin = max(4, min(14, r.width // 4))
        return pygame.Rect(
            r.left + margin,
            r.bottom - 12,
            max(6, r.width - 2 * margin),
            14,
        )

    def move(
        self,
        moving_left,
        moving_right,
        world,
        area_group=None,
        enemy_group=None,
        player_ref=None,
        *,
        background_scroll: int = 0,
    ) -> int:
        move_spd = (
            self._effective_speed()
            if self.char_type == CharacterTypes.Enemy
            else self.speed
        )
        dx = 0
        if moving_left:
            dx = -move_spd
            self.is_x_flip = True
            self.direction = -1
        if moving_right:
            dx = move_spd
            self.is_x_flip = False
            self.direction = 1
        if self.is_aiming and self.char_type == CharacterTypes.Player:
            dx //= 2

        if self.char_type == CharacterTypes.Player and dx != 0:
            scroll_max = world.scroll_max_px(SCREEN_WIDTH)
            # 僅在「已到關卡邊界且貼齊螢幕邊」時擋移動；勿用 SCROLL_THRESH 當左緣，否則
            # 在 scroll=0 時走進左側捲動區後會無法再往左（往右回頭即卡住）。
            if (
                dx > 0
                and background_scroll >= scroll_max
                and self.rect.right >= SCREEN_WIDTH
            ):
                dx = 0
            elif dx < 0 and background_scroll <= 0:
                if self.rect.left <= 0:
                    dx = 0
                elif self.rect.left + dx < 0:
                    dx = -self.rect.left

        if self.is_in_air:
            self.is_jump = False
        elif self.is_jump:
            from .enemy_special import is_calc_tank_enemy

            self.is_jump = False
            if is_calc_tank_enemy(self):
                pass
            else:
                self.vel_y = JUMP_IMPULSE
                self.is_in_air = True
                if self.char_type == CharacterTypes.Player:
                    from . import game_audio

                    game_audio.play_jump(at_rect=self.rect)

        flying = self._is_flying_enemy()
        if not flying:
            if (
                self.vel_y < 0
                and self._ceiling_close_above(world, area_group, enemy_group, player_ref)
            ):
                self.vel_y = self.CEILING_DROP_VEL_Y

            self.vel_y += GRAVITY
            if self.vel_y > 14:
                self.vel_y = 14
        else:
            self.vel_y = 0.0
        dy = self.vel_y

        horizontal_blocked = False
        micro_lift = 0

        x_body = pygame.Rect(self.rect.x + dx, self.rect.y, self.width, self.height - 1)
        world_blocks = self._collides_with_world_or_area(x_body, world, area_group)
        if world_blocks:
            ndx, nlift = self._try_slope_nudge_horizontal(dx, world, area_group, enemy_group, player_ref)
            if ndx != 0:
                dx = ndx
                micro_lift = max(micro_lift, nlift)
            else:
                dx = 0
                horizontal_blocked = True
                if self.char_type == CharacterTypes.Enemy:
                    self.direction *= -1
                    self.move_counter = 0

        if self.char_type == CharacterTypes.Player and enemy_group is not None and dx != 0:
            x_body = pygame.Rect(self.rect.x + dx, self.rect.y, self.width, self.height - 1)
            if any(e.is_alive and e.rect.colliderect(x_body) for e in enemy_group):
                ndx, nlift = self._try_slope_nudge_horizontal(dx, world, area_group, enemy_group, player_ref)
                if ndx != 0:
                    dx = ndx
                    micro_lift = max(micro_lift, nlift)
                else:
                    dx = 0
                    horizontal_blocked = True

        if self.char_type == CharacterTypes.Enemy and player_ref is not None and player_ref.is_alive and dx != 0:
            x_body = pygame.Rect(self.rect.x + dx, self.rect.y, self.width, self.height - 1)
            if player_ref.rect.colliderect(x_body):
                ndx, nlift = self._try_slope_nudge_horizontal(dx, world, area_group, enemy_group, player_ref)
                if ndx != 0:
                    dx = ndx
                    micro_lift = max(micro_lift, nlift)
                else:
                    dx = 0
                    horizontal_blocked = True
                    self.direction *= -1
                    self.move_counter = 0

        if dx != 0 and self.char_type == CharacterTypes.Enemy and not flying:
            clamped = self._clamp_horizontal_move(
                dx, world, area_group, enemy_group, player_ref,
            )
            if clamped == 0 and dx != 0:
                horizontal_blocked = True
                self.direction *= -1
                self.move_counter = 0
            dx = clamped

        move_sign = -1 if moving_left else (1 if moving_right else 0)
        if horizontal_blocked and move_sign != 0 and not flying:
            step_dx = move_spd * move_sign
            for step in range(1, self.STEP_UP_HEIGHT + 1):
                candidate = pygame.Rect(
                    self.rect.x + step_dx, self.rect.y - step, self.width, self.height
                )
                if not self._solid_body_blocks_rect(candidate, world, area_group, enemy_group, player_ref):
                    dx = step_dx
                    dy = min(dy, -step)
                    horizontal_blocked = False
                    break

        self.rect.x += dx
        if micro_lift:
            self.rect.y -= micro_lift

        if not flying:
            dy_resolved, hit_ceiling = self._resolve_vertical_against_solids(
                dy, world, area_group, enemy_group, player_ref,
            )
            if hit_ceiling:
                if dy < 0 or self.vel_y < 0:
                    self.vel_y = self.CEILING_DROP_VEL_Y
                else:
                    self.vel_y = 0
            if dy_resolved < dy and dy > 0:
                self.vel_y = 0
            self.rect.y += dy_resolved

        aligned = False
        if not flying:
            aligned = self._apply_ground_ray_alignment(world, area_group, enemy_group)
        feet = pygame.Rect(self.rect.x, self.rect.bottom + 1, self.width, 2)
        on_ground = aligned or any(rect.colliderect(feet) for _, rect in world.obstacle_list)
        if not on_ground and area_group is not None:
            on_ground = any(area.intersects_rect(feet) for area in list(area_group))
        if not on_ground and self.char_type == CharacterTypes.Player and enemy_group is not None:
            on_ground = any(
                e.is_alive and player_standing_on_enemy_head(self, e)
                for e in enemy_group
            )

        if flying:
            self.is_in_air = False
            self.vel_y = 0.0
            self._airborne_since_ms = None
            self._long_fall_sfx_played = False
        elif on_ground:
            self.is_in_air = False
            if self.vel_y > 0:
                self.vel_y = 0
            self._airborne_since_ms = None
            self._long_fall_sfx_played = False
        else:
            self.is_in_air = True
            self._update_long_fall_sfx()

        if (
            self.char_type == CharacterTypes.Enemy
            and enemy_group is not None
            and on_ground
            and not flying
            and self.vel_y >= -1.5
        ):
            travel_dir = int(self.direction)
            if dx != 0:
                travel_dir = 1 if dx > 0 else -1
            self._resolve_enemy_peer_overlap(
                travel_dir, enemy_group, world, area_group,
            )

        if not getattr(self, "ghost_walls", False):
            self._depenetrate_world_obstacles_only(world)

        if self.char_type == CharacterTypes.Enemy:
            from .enemy_special import enemy_ignores_spikes_and_ledges

            if not enemy_ignores_spikes_and_ledges(self):
                self._try_step_off_spikes(world)

        if not flying and self.rect.y > SCREEN_HEIGHT:
            self.health = 0.0

        screen_scroll = 0
        if self.char_type == CharacterTypes.Player and dx != 0:
            scroll_max = world.scroll_max_px(SCREEN_WIDTH)
            should_scroll = (
                dx > 0
                and self.rect.right > SCREEN_WIDTH - SCROLL_THRESH
                and background_scroll < scroll_max
            ) or (
                dx < 0
                and self.rect.left < SCROLL_THRESH
                and background_scroll > 0
            )
            if should_scroll:
                self.rect.x -= dx
                screen_scroll = -dx
            if self.rect.left < 0:
                self.rect.left = 0
            if self.rect.right > SCREEN_WIDTH:
                self.rect.right = SCREEN_WIDTH

        return screen_scroll

    def _update_long_fall_sfx(self) -> None:
        if self.vel_y <= 0.35:
            return
        now = pygame.time.get_ticks()
        if self._airborne_since_ms is None:
            self._airborne_since_ms = now
            return
        if self._long_fall_sfx_played:
            return
        if now - self._airborne_since_ms < 1000:
            return
        from . import game_audio

        game_audio.play_fall(at_rect=self.rect)
        self._long_fall_sfx_played = True

    def take_damage(self, dmg):
        if not self.is_alive:
            return
        if self.char_type == CharacterTypes.Enemy and getattr(self, "invincible", False):
            return
        self.health = round_hp(max(0.0, float(self.health) - float(dmg)), HP_DECIMAL_PLACES)
        if self.char_type == CharacterTypes.Player:
            from . import game_audio

            game_audio.play_player_hurt(at_rect=self.rect)
        elif self.char_type == CharacterTypes.Enemy:
            from . import game_audio

            game_audio.play_enemy_hurt(at_rect=self.rect, enemy=self)

    def heal(self, hp):
        self.health = round_hp(
            min(float(self.max_health), float(self.health) + float(hp)),
            HP_DECIMAL_PLACES,
        )

    def check_alive(self):
        if self.health <= 0 and self.is_alive:
            self.is_alive = False
            if self.char_type == CharacterTypes.Enemy:
                from . import game_audio

                game_audio.stop_enemy_sfx(self)
            self.update_action(ActionTypes.DEATH)

    def update_action(self, new_action):
        if self.action != new_action:
            self.action = new_action
            self.frame_index = 0
            self.update_time = pygame.time.get_ticks()

    def update_animation(self):
        if (
            self.char_type == CharacterTypes.Player
            and self.action == ActionTypes.JUMP
        ):
            frames = self.animation_list[self.action]
            if len(frames) >= 2:
                # 00=落地 jump-1；01=空中 jump-2（上升 vel_y<0 用空中格）
                idx = 0 if self.vel_y >= 0 else 1
                self.frame_index = idx
                img = frames[idx]
                ref = frames[1]
                rh = ref.get_height()
                if rh > 0 and img.get_height() != rh:
                    nw = max(1, int(img.get_width() * rh / img.get_height()))
                    img = pygame.transform.smoothscale(img, (nw, rh))
                self.image = img
                self._sync_sprite_size()
                return
        if (
            self.char_type == CharacterTypes.Player
            and self.action == ActionTypes.CAST
        ):
            frames = self.animation_list.get(ActionTypes.CAST) or []
            if frames:
                cd = int(getattr(self, "cast_animation_cooldown", 80))
                now = pygame.time.get_ticks()
                if now - self.update_time > cd:
                    self.update_time = now
                    if self.frame_index < len(frames) - 1:
                        self.frame_index += 1
                    else:
                        self.cast_anim_active = False
                        from .controller import EquationController

                        if pygame.key.get_pressed()[EquationController.FUNCTION_AIM_KEY]:
                            self.cast_anim_hold_last = True
                        else:
                            self.cast_anim_hold_last = False
                if getattr(self, "cast_anim_hold_last", False):
                    self.frame_index = len(frames) - 1
                elif not getattr(self, "cast_anim_active", False):
                    self.cast_anim_hold_last = False
                self.frame_index = min(self.frame_index, len(frames) - 1)
                self.image = frames[self.frame_index]
                self._sync_sprite_size()
                return
        if getattr(self, "_kenney_pair_anim", False) and self.action != ActionTypes.DEATH:
            frames = self.animation_list[self.action]
            if len(frames) >= 2:
                phase = int(getattr(self, "_pair_phase_ms", 0))
                idx = (pygame.time.get_ticks() + phase) // ENEMY_PAIR_ANIM_INTERVAL_MS % 2
                self.frame_index = idx
                self.image = frames[idx]
                return
        cooldown = self.death_animation_cooldown if self.action == ActionTypes.DEATH else self.animation_cooldown
        if pygame.time.get_ticks() - self.update_time > cooldown:
            self.update_time = pygame.time.get_ticks()
            self.frame_index += 1
        frames = self.animation_list[self.action]
        if self.frame_index >= len(frames):
            if self.action == ActionTypes.DEATH:
                self.frame_index = len(frames) - 1
            else:
                self.frame_index = 0
        self.image = frames[self.frame_index]
        if self.char_type == CharacterTypes.Player:
            self._sync_sprite_size()

    def _sync_sprite_size(self):
        if self.image is not None:
            self.width = self.image.get_width()
            self.height = self.image.get_height()

    def draw(self, surface):
        img = self.image
        if self.is_x_flip:
            img = pygame.transform.flip(img, True, False)
        scale = float(getattr(self, "scale_mult", 1.0)) * float(getattr(self, "_height_scale", 1.0))
        if abs(scale - 1.0) > 0.02:
            w = max(1, int(img.get_width() * scale))
            h = max(1, int(img.get_height() * scale))
            img = pygame.transform.smoothscale(img, (w, h))
        alpha = int(getattr(self, "alpha", 255))
        if alpha < 255:
            img = img.copy()
            img.set_alpha(alpha)
        dest = img.get_rect(center=self.rect.center)
        surface.blit(img, dest)


class Player(Soldier):
    def __init__(self, x, y):
        super().__init__(CharacterTypes.Player, x, y, PLAYER_VISUAL_SCALE, 5)
        self.max_health = float(PLAYER_MAX_HP)
        self.health = float(PLAYER_MAX_HP)
        self.key_count = 0
        # 次方僅能靠微分／積分塊碰自機升降；預設 1（一次）
        self.polynomial_degree = 1
        self.game_mode = PlayerMode.FUNCTION
        self.integral_axis = IntegralAxis.Y
        self.heal_sigmoid_active = False
        self.derivative_round_unlocked = False
        self.integral_only_lock = False
        self.center_notice_until_ms = 0
        self.center_notice_text = ""
        # 0 次彩蛋「啵」：由主迴圈依此計數播放（測試可 assert）
        self.pop_sound_requests = 0
        self.cast_anim_active = False
        self.cast_anim_hold_last = False
        self.cast_animation_cooldown = 80

    def begin_cast_animation(self) -> None:
        """發射後播放一次 Cast，播完停在最後格；若仍按住 1 鍵則維持最後格。"""
        self.cast_anim_active = True
        self.cast_anim_hold_last = False
        self.update_action(ActionTypes.CAST)

    def cast_animation_busy(self) -> bool:
        return bool(self.cast_anim_active or self.cast_anim_hold_last)

    def tick_cast_hold_release(self) -> None:
        if not self.cast_anim_hold_last:
            return
        from .controller import EquationController

        if not pygame.key.get_pressed()[EquationController.FUNCTION_AIM_KEY]:
            self.cast_anim_hold_last = False

    @staticmethod
    def show_center_notice(player, text: str, now_ms: int | None = None, duration_ms: int = 2500) -> None:
        if now_ms is None:
            now_ms = pygame.time.get_ticks()
        player.center_notice_text = str(text)
        player.center_notice_until_ms = int(now_ms) + int(duration_ms)

    def apply_degree_delta(self, delta: int):
        self.polynomial_degree = clamp_degree(self.polynomial_degree + int(delta))

    def request_pop_sound(self):
        self.pop_sound_requests += 1

    def respawn_at(self, x: int, y: int):
        """重生點：恢復血量並傳送到世界座標。"""
        self.health = float(self.max_health)
        self.is_alive = True
        self.vel_y = 0.0
        self.is_in_air = False
        self.is_jump = False
        self._airborne_since_ms = None
        self._long_fall_sfx_played = False
        self.rect.center = (int(x), int(y))
        self.frame_index = 0
        self.update_action(ActionTypes.IDLE)

    def move(self, moving_left, moving_right, world, area_group=None, enemy_group=None, background_scroll=0):
        return super().move(
            moving_left,
            moving_right,
            world,
            area_group,
            enemy_group=enemy_group,
            player_ref=None,
            background_scroll=background_scroll,
        )
        if self.rect.top < 0:
            self.rect.top = 0
            if self.vel_y < 0:
                self.vel_y = max(2.0, -self.vel_y * self.PLAYER_TOP_BOUNCE)
            self.is_in_air = True


class Enemy(Soldier):
    SHOOT_COOLDOWN_FRAMES = 80

    def __init__(self, x, y, max_hp: float | None = None, enemy_gid: int = 65834):
        super().__init__(CharacterTypes.Enemy, x, y, ENEMY_VISUAL_SCALE, 2)
        mh = float(ENEMY_DEFAULT_MAX_HP if max_hp is None else max_hp)
        self.max_health = mh
        self.health = mh
        self.calc_frozen = False
        self.enemy_gid = int(enemy_gid)
        self.drops_key_on_death = self.enemy_gid == 65840
        self._key_drop_spawned = False
        self._bump_ticks_remaining = 0
        self._bump_next_ready_ms = 0
        self._bump_damage_done = False
        self._last_spike_damage_ms = 0
        self.head_label = None
        self.math_label = None
        self.speed_mult = 1.0
        self.shoot_cd_mult = 1.0
        self.scale_mult = 1.0
        self.alpha = 255
        self.ghost_walls = False
        self.ghost_area = False
        self.chase_aggressive = False
        self.ai_kind = "default"
        self.calculus_immune = False
        self.only_heal_bullet_hurt = False
        self.invincible = False
        self.uses_melee_bump = False
        self.pending_crush_player = False
        self._calc_tank_block_override = False
        self._calc_integral_boost_ms = 0
        self._calc_integral_permanent = False
        self._giant_grown_until_ms = 0
        self._giant_reverting = False
        self._giant_base_max_hp = mh
        self._giant_base_speed_mult = 1.0
        self._giant_base_scale = 1.0
        self.sin_phase_index = 0
        self._stun_until_ms = 0
        self._lunge_remaining_px = 0.0
        self._lunge_speed_backup = 3.0
        self._height_scale = 1.0
        self._sin_t = 0.0
        self._sin_phase_v = 0.0
        self._sin_last_off = 0.0
        self._ai_activated = False
        self._calc_tank_priority = False
        self._calc_tank_base_speed_mult = 0.7
        self._imaginary_drain_ms = 0
        self._dodge_until_ms = 0
        self._nearby_derivative_blocks = ()
        self._nearby_integral_blocks = ()
        self._peer_jump_cooldown_until_ms = 0
        self._peer_retreat_cooldown_until_ms = 0
        self._peer_rng = random.Random((id(self) ^ int(pygame.time.get_ticks())) & 0x7FFFFFFF)
        self._melee_touch_ms = 0
        self._kenney_pair_anim = False
        self._pair_phase_ms = self._peer_rng.randint(0, max(0, ENEMY_PAIR_ANIM_INTERVAL_MS - 1))
        self._apply_kenney_walk_pair_if_any()
        self._apply_kenney_walk_sequence_if_any()
        from .enemy_special import apply_archetype_to_enemy
        from .enemy_visual import apply_enemy_appearance

        apply_archetype_to_enemy(self)
        apply_enemy_appearance(self)

    def _effective_speed(self) -> int:
        return max(1, int(round(self.speed * getattr(self, "speed_mult", 1.0))))

    def _apply_kenney_walk_pair_if_any(self) -> None:
        pair = ENEMY_KENNEY_WALK_PAIR_GIDS.get(self.enemy_gid)
        if pair is None:
            return
        gid_a, gid_b = pair
        scale = float(getattr(self, "scale_mult", 1.0))
        px = max(8, int(34 * ENEMY_VISUAL_SCALE * scale))
        rgb_a = ENEMY_KENNEY_TILE_RGB.get(gid_a, (220, 90, 90))
        rgb_b = ENEMY_KENNEY_TILE_RGB.get(gid_b, (220, 90, 90))
        img_a = surface_for_gid(gid_a, px, fallback_rgb=rgb_a)
        img_b = surface_for_gid(gid_b, px, fallback_rgb=rgb_b)
        walk_frames = [img_a, img_b]
        death_frames = [img_a]
        for action in ActionTypes:
            self.animation_list[action] = death_frames if action == ActionTypes.DEATH else walk_frames
        self.frame_index = min(self.frame_index, len(self.animation_list[self.action]) - 1)
        self.image = self.animation_list[self.action][self.frame_index]
        cx, cy = self.rect.center
        self.rect = self.image.get_rect(center=(cx, cy))
        self.width = self.image.get_width()
        self.height = self.image.get_height()
        self._kenney_pair_anim = True

    def _apply_kenney_walk_sequence_if_any(self) -> None:
        """移動時依序切換多格 Kenney 貼圖（如 65843→65844→65845）。"""
        seq = ENEMY_KENNEY_WALK_SEQUENCE_GIDS.get(self.enemy_gid)
        if seq is None:
            return
        scale = float(getattr(self, "scale_mult", 1.0))
        px = max(12, int(TILE_SIZE * ENEMY_VISUAL_SCALE * scale))
        walk_frames = []
        for gid in seq:
            rgb = ENEMY_KENNEY_TILE_RGB.get(gid, (200, 90, 100))
            img = surface_for_gid(gid, px, fallback_rgb=rgb)
            if img is None:
                continue
            walk_frames.append(img)
        if not walk_frames:
            return
        idle_frames = [walk_frames[0]]
        death_frames = [walk_frames[0]]
        for action in ActionTypes:
            if action == ActionTypes.DEATH:
                self.animation_list[action] = death_frames
            elif action == ActionTypes.IDLE:
                self.animation_list[action] = idle_frames
            else:
                self.animation_list[action] = walk_frames
        self.frame_index = min(self.frame_index, len(self.animation_list[self.action]) - 1)
        self.image = self.animation_list[self.action][self.frame_index]
        cx, cy = self.rect.center
        self.rect = self.image.get_rect(center=(cx, cy))
        self.width = self.image.get_width()
        self.height = self.image.get_height()

    def _foot_ground_top_y(
        self,
        foot_x: int,
        world,
        area_group,
        *,
        ref_bottom: int | None = None,
        search_up: int | None = None,
        search_down: int | None = None,
    ) -> int | None:
        """在 foot_x 下方掃描最近固體頂部 Y。"""
        feet = self.rect.bottom if ref_bottom is None else int(ref_bottom)
        up = TILE_SIZE if search_up is None else int(search_up)
        down = TILE_SIZE * 3 if search_down is None else int(search_down)
        probe = pygame.Rect(int(foot_x - 10), int(feet - up), 20, up + down + 8)
        best: int | None = None
        y_lo = feet - up
        y_hi = feet + down
        for _img, rect in world.obstacle_list:
            if not rect.colliderect(probe):
                continue
            if rect.top < y_lo or rect.top > y_hi:
                continue
            if best is None or rect.top < best:
                best = rect.top
        if area_group is not None:
            for area in list(area_group):
                if not area.intersects_rect(probe):
                    continue
                top = area.surface_top_at_world_x(int(foot_x))
                if top is not None and y_lo <= top <= y_hi:
                    if best is None or top < best:
                        best = int(top)
        return best

    def _ground_below_ahead(self, foot_x: int, world, area_group, max_drop: int) -> int | None:
        """前方腳點往下 max_drop 內可踩到的地面（較深的平台）。"""
        ref = self.rect.bottom + 4
        return self._foot_ground_top_y(
            foot_x,
            world,
            area_group,
            ref_bottom=ref,
            search_up=0,
            search_down=max_drop,
        )

    def _try_enemy_jump_for_step_up(self, world, area_group, forward: int) -> None:
        from .enemy_special import is_calc_tank_enemy

        if is_calc_tank_enemy(self):
            return
        if forward == 0 or self.is_in_air:
            return
        cur = self._foot_ground_top_y(self.rect.centerx, world, area_group)
        if cur is None:
            return
        margin = max(self._effective_speed(), 4)
        lead_x = int(self.rect.centerx + forward * (self.width // 2 + margin))
        ahead = self._foot_ground_top_y(lead_x, world, area_group)
        if ahead is None:
            return
        rise = cur - ahead
        if 4 < rise <= TILE_SIZE + 8:
            self.is_jump = True

    def _ledge_clear_ahead(
        self,
        world,
        area_group,
        forward: int,
        *,
        from_center_x: int | None = None,
    ) -> bool:
        """True = 懸崖（前方無路）；若下方兩格內有陸地則先視為可下落。"""
        from .enemy_special import calc_tank_drop_blocked_by_spikes, is_calc_tank_enemy

        if forward == 0 or self.is_in_air:
            return False
        cx = self.rect.centerx if from_center_x is None else int(from_center_x)
        cur = self._foot_ground_top_y(cx, world, area_group)
        if cur is None:
            return False
        margin = max(self._effective_speed(), 4)
        lead_x = int(cx + forward * (self.width // 2 + margin))
        ahead = self._foot_ground_top_y(lead_x, world, area_group)
        deep = self._ground_below_ahead(lead_x, world, area_group, TILE_SIZE * 2 + 8)
        if ahead is None:
            if deep is not None and deep >= cur + TILE_SIZE // 2:
                if is_calc_tank_enemy(self) and calc_tank_drop_blocked_by_spikes(
                    self, world, lead_x, deep,
                ):
                    return True
                return False
            return True
        drop = ahead - cur
        rise = cur - ahead
        if drop > TILE_SIZE * 2 + 8:
            if deep is not None and deep > ahead:
                if is_calc_tank_enemy(self) and calc_tank_drop_blocked_by_spikes(
                    self, world, lead_x, deep,
                ):
                    return True
                return False
            return True
        if TILE_SIZE // 2 <= drop <= TILE_SIZE * 2 + 8:
            if is_calc_tank_enemy(self) and calc_tank_drop_blocked_by_spikes(
                self, world, lead_x, ahead,
            ):
                return True
        if rise > TILE_SIZE + 8:
            return True
        return False

    def _clamp_horizontal_move(
        self,
        dx: int,
        world,
        area_group,
        enemy_group=None,
        player_ref=None,
    ) -> int:
        """依實際步長逐像素檢查牆與懸崖，避免高速穿透。"""
        if dx == 0:
            return 0
        sign = 1 if dx > 0 else -1
        steps = max(1, int(abs(dx)))
        allowed = 0
        orig_x = self.rect.x
        orig_y = self.rect.y
        for s in range(1, steps + 1):
            trial = sign * s
            test = pygame.Rect(orig_x + trial, orig_y, self.width, self.height - 1)
            if self._collides_with_world_or_area(test, world, area_group):
                break
            if self.char_type == CharacterTypes.Player and enemy_group is not None:
                if any(e.is_alive and e.rect.colliderect(test) for e in enemy_group):
                    break
            if self.char_type == CharacterTypes.Enemy and player_ref is not None and player_ref.is_alive:
                if player_ref.rect.colliderect(test):
                    break
            if (
                self.char_type == CharacterTypes.Enemy
                and not self.is_in_air
                and not self._is_flying_enemy()
            ):
                trial_cx = orig_x + trial + self.width // 2
                if self._ledge_clear_ahead(
                    world, area_group, sign, from_center_x=trial_cx,
                ):
                    break
            allowed = trial
        return allowed

    def _is_on_walkable_surface(self, world, area_group, enemy_group=None) -> bool:
        """平地或斜面等有支撐（非空中）；用腳底探測，不依 is_in_air 舊值。"""
        if self.vel_y < -2.0:
            return False
        feet = pygame.Rect(self.rect.x, self.rect.bottom + 1, self.width, 2)
        if any(rect.colliderect(feet) for _, rect in world.obstacle_list):
            return True
        if area_group is not None and any(
            area.intersects_rect(feet) for area in list(area_group)
        ):
            return True
        su, sd = self.GROUND_RAY_SNAP_UP_PX, self.GROUND_RAY_SNAP_DOWN_PX
        bottom = self.rect.bottom
        if self._support_top_at_foot_x(
            self.rect.centerx, bottom, world, area_group, su, sd, enemy_group,
        ) is not None:
            return True
        margin = max(1, min(6, self.width // 5))
        for fx in (self.rect.left + margin, self.rect.right - margin):
            if self._support_top_at_foot_x(
                fx, bottom, world, area_group, su, sd, enemy_group,
            ) is not None:
                return True
        return False

    def _overlaps_any_enemy(self, enemy_group) -> bool:
        for other in enemy_group:
            if other is self or not getattr(other, "is_alive", True):
                continue
            if self.rect.colliderect(other.rect):
                return True
        return False

    def _peer_rng_roll(self, lo: int, hi: int) -> int:
        rng = getattr(self, "_peer_rng", None)
        if rng is None:
            self._peer_rng = random.Random((id(self) ^ pygame.time.get_ticks()) & 0x7FFFFFFF)
            rng = self._peer_rng
        return rng.randint(lo, hi)

    def _apply_peer_separation_hop(self) -> None:
        """重疊分離跳：不佔用 is_jump，不影響一般向前跳。"""
        self.vel_y = JUMP_IMPULSE
        self.is_in_air = True
        self.is_jump = False

    def _resolve_enemy_peer_overlap(
        self,
        travel_dir: int,
        enemy_group,
        world,
        area_group,
    ) -> None:
        """地上（含斜面）：重疊時獨立 RNG 決定分離跳或後退。"""
        if enemy_group is None:
            return
        if self.is_in_air or self.vel_y < -1.5:
            return
        if not self._is_on_walkable_surface(world, area_group, enemy_group):
            return
        if not self._overlaps_any_enemy(enemy_group):
            return
        sign = travel_dir if travel_dir != 0 else int(self.direction)
        if sign == 0:
            sign = 1
        now_ms = pygame.time.get_ticks()
        from .enemy_special import is_calc_tank_enemy

        if now_ms >= int(getattr(self, "_peer_jump_cooldown_until_ms", 0)):
            if (
                not is_calc_tank_enemy(self)
                and self._peer_rng_roll(1, ENEMY_PEER_JUMP_CHANCE) == 1
            ):
                self._apply_peer_separation_hop()
                self._peer_jump_cooldown_until_ms = now_ms + ENEMY_PEER_JUMP_COOLDOWN_MS
                return
        if now_ms < int(getattr(self, "_peer_retreat_cooldown_until_ms", 0)):
            return
        if self._peer_rng_roll(1, 10) > ENEMY_PEER_RETREAT_CHANCE:
            return
        retreat = -sign * max(1, int(round(TILE_SIZE * ENEMY_PEER_GAP_TILES)))
        if not getattr(self, "ghost_walls", False):
            retreat = self._clamp_horizontal_move(retreat, world, area_group)
        if retreat:
            self.rect.x += retreat
            self._peer_retreat_cooldown_until_ms = now_ms + ENEMY_PEER_RETREAT_COOLDOWN_MS
            self._apply_ground_ray_alignment(world, area_group, enemy_group)

    def feet_on_spike_damage(self, world) -> bool:
        """腳底是否踩在伸出中的尖刺上（與避刺邏輯一致，不用整體碰撞箱）。"""
        if self.char_type == CharacterTypes.Enemy:
            from .enemy_special import enemy_ignores_spikes_and_ledges

            if enemy_ignores_spikes_and_ledges(self):
                return False
        if not world.spikes_extended:
            return False
        feet = self._feet_rect_for_spike()
        return any(feet.colliderect(sr) for sr in world.spike_damage_rects())

    def _would_overlap_spike_damage_feet(self, world, step_dx: int) -> bool:
        """下一步水平位移後，腳底是否踩進伸出中的尖刺區。"""
        if self.char_type == CharacterTypes.Enemy:
            from .enemy_special import enemy_ignores_spikes_and_ledges

            if enemy_ignores_spikes_and_ledges(self):
                return False
        if not world.spikes_extended:
            return False
        cand = self.rect.copy()
        cand.x += int(round(step_dx))
        feet = self._feet_rect_for_spike(cand)
        return any(feet.colliderect(sr) for sr in world.spike_damage_rects())

    def _try_step_off_spikes(self, world) -> None:
        """已踩在刺上時嘗試水平離開，避免停著仍持續扣血。"""
        if not self.feet_on_spike_damage(world):
            return
        spd = self._effective_speed() if self.char_type == CharacterTypes.Enemy else self.speed
        for try_dx in (
            spd * self.direction,
            -spd * self.direction,
            spd,
            -spd,
            spd * 2,
            -spd * 2,
        ):
            dx = int(round(try_dx))
            if dx == 0:
                continue
            if self._would_overlap_spike_damage_feet(world, dx):
                continue
            old_x = self.rect.x
            self.rect.x += dx
            if not self.feet_on_spike_damage(world):
                return
            self.rect.x = old_x

    def _filter_horizontal_move_for_spikes(self, world, ai_left: bool, ai_right: bool) -> tuple[bool, bool]:
        spd = self._effective_speed() if self.char_type == CharacterTypes.Enemy else max(1, int(round(self.speed)))
        if ai_left and self._would_overlap_spike_damage_feet(world, -spd):
            ai_left = False
        if ai_right and self._would_overlap_spike_damage_feet(world, spd):
            ai_right = False
        return ai_left, ai_right

    def _ai_patrol_no_shoot(self, player, world, area_group=None, enemy_group=None):
        """左右巡邏／發呆，不射擊。"""
        if self.is_idling:
            self.idling_counter -= 1
            self.update_action(ActionTypes.IDLE)
            if self.idling_counter <= 0:
                self.is_idling = False
            return

        if random.randint(1, 240) == 1:
            self.is_idling = True
            self.idling_counter = 60
            self.update_action(ActionTypes.IDLE)
            return

        from .enemy_special import enemy_ignores_spikes_and_ledges, is_calc_tank_enemy

        ai_left = self.direction == -1
        ai_right = self.direction == 1
        ignore_hazards = enemy_ignores_spikes_and_ledges(self)
        no_jump = is_calc_tank_enemy(self)
        if not ignore_hazards and self.feet_on_spike_damage(world):
            self.direction *= -1
            ai_left = self.direction == -1
            ai_right = self.direction == 1
        if not ignore_hazards:
            ai_left, ai_right = self._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
        ledge_brake = False
        if not ignore_hazards and not no_jump and not self.is_in_air and (ai_left or ai_right):
            fwd = -1 if ai_left else 1
            self._try_enemy_jump_for_step_up(world, area_group, fwd)
            if self._ledge_clear_ahead(world, area_group, fwd):
                self.direction *= -1
                ai_left = ai_right = False
                self.move_counter = 0
                ledge_brake = True
        elif not ignore_hazards and no_jump and not self.is_in_air and (ai_left or ai_right):
            fwd = -1 if ai_left else 1
            if self._ledge_clear_ahead(world, area_group, fwd):
                self.direction *= -1
                ai_left = ai_right = False
                self.move_counter = 0
                ledge_brake = True
        self.move(ai_left, ai_right, world, area_group, enemy_group=enemy_group, player_ref=player)
        if ledge_brake:
            self.update_action(ActionTypes.IDLE)
        else:
            self.update_action(ActionTypes.RUN)
        self.move_counter += 1
        if self.move_counter >= TILE_SIZE * 3:
            self.direction *= -1
            self.move_counter = 0

    def _apply_chase_move(
        self,
        player,
        world,
        area_group,
        ai_left: bool,
        ai_right: bool,
        enemy_group=None,
        *,
        skip_ledge_brake: bool = False,
    ) -> tuple[bool, bool]:
        from .enemy_special import enemy_ignores_spikes_and_ledges, is_calc_tank_enemy

        ignore_hazards = enemy_ignores_spikes_and_ledges(self)
        no_jump = is_calc_tank_enemy(self)
        if not ignore_hazards and self.feet_on_spike_damage(world):
            self.direction *= -1
            ai_left = self.direction == -1
            ai_right = self.direction == 1
        if not ignore_hazards:
            ai_left, ai_right = self._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
        ledge_brake = False
        if (
            not skip_ledge_brake
            and not ignore_hazards
            and not self.is_in_air
            and (ai_left or ai_right)
        ):
            fwd = -1 if ai_left else 1
            if not no_jump:
                self._try_enemy_jump_for_step_up(world, area_group, fwd)
            if self._ledge_clear_ahead(world, area_group, fwd):
                self.direction *= -1
                ai_left = ai_right = False
                ledge_brake = True
        self.move(ai_left, ai_right, world, area_group, enemy_group=enemy_group, player_ref=player)
        return ai_left, ai_right, ledge_brake

    def _ai_chase_aggressive(self, player, world, area_group=None, enemy_bullet_group=None, enemy_group=None):
        """持續朝玩家移動並高頻射擊。"""
        from .enemy_special import effective_shoot_cooldown, enemy_ignores_spikes_and_ledges

        dx = player.rect.centerx - self.rect.centerx
        self.direction = 1 if dx >= 0 else -1
        self.facing = self.direction
        ai_left = dx < -4
        ai_right = dx > 4
        ai_left, ai_right, _ = self._apply_chase_move(
            player,
            world,
            area_group,
            ai_left,
            ai_right,
            enemy_group=enemy_group,
            skip_ledge_brake=enemy_ignores_spikes_and_ledges(self),
        )
        if ai_left or ai_right:
            self.update_action(ActionTypes.RUN)
        else:
            self.update_action(ActionTypes.IDLE)
        if enemy_bullet_group is not None and self.shoot_cooldown == 0:
            cd = max(3, effective_shoot_cooldown(self))
            if random.randint(1, cd) == 1:
                self.shoot(enemy_bullet_group, player_ref=player)

    def _ai_melee_tank(self, player, world, area_group=None, enemy_group=None):
        """近戰追擊（65840）：微積分塊反應優先，否則衝撞追擊。"""
        from .enemy_special import (
            _calc_tank_block_ai,
            ai_calc_tank_priority_move,
            calc_tank_flee_spikes,
        )

        if calc_tank_flee_spikes(self, player, world, area_group, enemy_group):
            return
        _calc_tank_block_ai(self, world, pygame.time.get_ticks(), area_group)
        if ai_calc_tank_priority_move(self, player, world, area_group, enemy_group):
            return
        self._ai_chase_contact_melee(player, world, area_group, enemy_group=enemy_group)

    def _melee_body_overlaps_player(self, player) -> bool:
        if not player.is_alive:
            return False
        if player_standing_on_enemy_head(player, self):
            return False
        clip = self.rect.clip(player.rect)
        if clip.width >= max(6, int(min(self.width, player.width) * 0.22)):
            if clip.height >= max(6, int(min(self.height, player.height) * 0.18)):
                return True
        return self._melee_in_attack_range(player)

    def _melee_in_attack_range(self, player) -> bool:
        """貼身／近距離攻擊範圍（含衝刺後未完全重疊）。"""
        if not player.is_alive or player_standing_on_enemy_head(player, self):
            return False
        dx = abs(player.rect.centerx - self.rect.centerx)
        dy = abs(player.rect.centery - self.rect.centery)
        reach_x = max(14, int(max(self.width, player.width) * 0.72))
        reach_y = max(18, int(max(self.height, player.height) * 0.85))
        return dx < reach_x and dy < reach_y

    def _try_melee_contact_damage(self, player, now_ms: int) -> bool:
        """貼身重疊時補傷（避免太近時衝撞判定打不到）。"""
        from .constants import ENEMY_BULLET_DAMAGE, ENEMY_MELEE_CONTACT_INTERVAL_MS

        if not self._melee_body_overlaps_player(player):
            return False
        last = int(getattr(self, "_melee_touch_ms", 0))
        if now_ms - last < ENEMY_MELEE_CONTACT_INTERVAL_MS:
            return False
        self._melee_touch_ms = now_ms
        player.take_damage(ENEMY_BULLET_DAMAGE)
        return True

    def _ai_chase_contact_melee(self, player, world, area_group=None, enemy_group=None):
        """近戰衝撞：週期性向前衝刺並造成單次傷害（65834／65840 等）。"""
        from . import game_audio
        from .constants import ENEMY_BULLET_DAMAGE
        from .enemy_special import (
            _calc_tank_block_ai,
            ai_calc_tank_priority_move,
            calc_tank_derivative_in_attack_range,
            calc_tank_flee_spikes,
            calc_tank_priority_active,
            is_calc_tank_enemy,
        )

        dx = player.rect.centerx - self.rect.centerx
        dy_vertical = abs(player.rect.centery - self.rect.centery)
        now = pygame.time.get_ticks()
        use_bump = bool(getattr(self, "uses_melee_bump", False))

        if is_calc_tank_enemy(self):
            if calc_tank_flee_spikes(self, player, world, area_group, enemy_group):
                return
            _calc_tank_block_ai(self, world, now, area_group)
        if ai_calc_tank_priority_move(self, player, world, area_group, enemy_group):
            return

        if use_bump and self._melee_in_attack_range(player):
            self._try_melee_contact_damage(player, now)

        if use_bump and self._bump_ticks_remaining > 0:
            self._bump_ticks_remaining -= 1
            spd = max(5, int(round(self._effective_speed() * 2.5)))
            step = spd * self.direction
            if not self._would_overlap_spike_damage_feet(world, step):
                if not getattr(self, "ghost_walls", False):
                    step = self._clamp_horizontal_move(
                        step, world, area_group, player_ref=player,
                    )
                if step:
                    self.rect.x += step
                    self._apply_ground_ray_alignment(world, area_group, enemy_group)
                    if (
                        enemy_group is not None
                        and not self.is_in_air
                        and self._is_on_walkable_surface(world, area_group, enemy_group)
                    ):
                        self._resolve_enemy_peer_overlap(
                            self.direction, enemy_group, world, area_group,
                        )
                if player.is_alive and not self._bump_damage_done:
                    if self._melee_in_attack_range(player):
                        player.take_damage(ENEMY_BULLET_DAMAGE)
                        self._bump_damage_done = True
                        self._melee_touch_ms = now
            self.update_action(ActionTypes.RUN)
            self.update_animation()
            return

        self.direction = 1 if dx >= 0 else -1
        self.facing = self.direction
        ai_left = dx < -3
        ai_right = dx > 3
        ai_left, ai_right, ledge_brake = self._apply_chase_move(
            player, world, area_group, ai_left, ai_right, enemy_group=enemy_group,
        )
        if self._melee_in_attack_range(player):
            self._try_melee_contact_damage(player, now)
        if ledge_brake:
            self.update_action(ActionTypes.IDLE)
        elif ai_left or ai_right:
            self.update_action(ActionTypes.RUN)
        else:
            self.update_action(ActionTypes.IDLE)

        if not use_bump:
            return
        if calc_tank_priority_active(self, now):
            return
        bump_blocked = (
            is_calc_tank_enemy(self) and calc_tank_derivative_in_attack_range(self)
        )
        if (
            not bump_blocked
            and self._bump_ticks_remaining <= 0
            and now >= self._bump_next_ready_ms
            and not self.is_in_air
            and dy_vertical < int(TILE_SIZE * 1.2)
            and abs(dx) < TILE_SIZE * 3
            and player.is_alive
        ):
            self._bump_ticks_remaining = 18
            self._bump_damage_done = False
            self._bump_next_ready_ms = now + 1200
            self.direction = 1 if dx >= 0 else -1
            self.facing = self.direction
            game_audio.play_monster_attack_if_visible(self.rect, self)

    def ai(self, player, world, enemy_bullet_group, area_group=None, enemy_group=None):
        from . import enemy_special
        from .enemy_special import effective_shoot_cooldown

        if not self.is_alive or not player.is_alive:
            return
        now_ms = pygame.time.get_ticks()
        enemy_special.update_ai_activation(self)
        enemy_special.update_enemy_special(self, player, world, enemy_bullet_group, area_group, now_ms)
        if getattr(self, "_stun_until_ms", 0) > now_ms:
            return
        if not enemy_special.is_ai_active(self, player):
            self.update_action(ActionTypes.IDLE)
            return
        if self.calc_frozen and not getattr(self, "calculus_immune", False):
            self.update_action(ActionTypes.IDLE)
            self.move(False, False, world, area_group, enemy_group=enemy_group, player_ref=player)
            return
        ai_kind = getattr(self, "ai_kind", "default")
        if ai_kind == "area_spray":
            if enemy_special.ai_area_sprayer(
                self, player, world, enemy_bullet_group, area_group, now_ms,
            ):
                return
            enemy_special.ai_area_sprayer_chase(
                self,
                player,
                world,
                area_group,
                enemy_bullet_group,
                enemy_group,
            )
            return
        if ai_kind == "melee_tank":
            self._ai_melee_tank(player, world, area_group, enemy_group)
            return
        if ai_kind == "imaginary":
            enemy_special.ai_imaginary(self, player, world, area_group, enemy_group)
            return
        if ai_kind in ("chase", "chase_melee", "tiny_fraction", "neg_one", "giant_256"):
            if getattr(self, "uses_melee_bump", False) or ai_kind == "chase_melee":
                self._ai_chase_contact_melee(player, world, area_group, enemy_group)
            else:
                self._ai_chase_aggressive(player, world, area_group, enemy_bullet_group, enemy_group)
            return
        if ai_kind == "sin_wave":
            if enemy_special.sin_wave_lunge_active(self):
                enemy_special.sin_wave_lunge_step(self, world)
                self.update_action(ActionTypes.RUN)
            else:
                ai_left, ai_right = enemy_special.ai_sin_wave_move(
                    self, player, world, area_group, now_ms,
                )
                self._apply_chase_move(
                    player,
                    world,
                    area_group,
                    ai_left,
                    ai_right,
                    enemy_group=enemy_group,
                    skip_ledge_brake=True,
                )
                enemy_special.apply_sin_horizontal_oscillation(self, player, world, now_ms)
                enemy_special.apply_sin_wave_motion(self, player, world, now_ms)
                self.update_action(
                    ActionTypes.RUN if (ai_left or ai_right) else ActionTypes.IDLE,
                )
                enemy_special.tick_sin_wave_move_sfx(self, ai_left or ai_right)
            enemy_special.after_enemy_move_wall_check(self, world, now_ms)
            cd = max(2, int(self.SHOOT_COOLDOWN_FRAMES * getattr(self, "shoot_cd_mult", 1.0) / 1.5))
            if (
                not enemy_special.sin_wave_lunge_active(self)
                and self.shoot_cooldown == 0
                and random.randint(1, cd) == 1
            ):
                self.shoot(enemy_bullet_group, player_ref=player)
            return
        if ai_kind == "exp_flyer":
            enemy_special.ai_exp_flyer(self, player, world, area_group, enemy_group)
            return
        if getattr(self, "chase_aggressive", False):
            if getattr(self, "uses_melee_bump", False):
                self._ai_chase_contact_melee(player, world, area_group, enemy_group)
            else:
                self._ai_chase_aggressive(player, world, area_group, enemy_bullet_group, enemy_group)
            return
        if self.is_idling:
            self.idling_counter -= 1
            self.update_action(ActionTypes.IDLE)
            if self.idling_counter <= 0:
                self.is_idling = False
            return

        self.vision.center = (self.rect.centerx + 110 * self.direction, self.rect.centery)
        if self.vision.colliderect(player.rect):
            self.update_action(ActionTypes.IDLE)
            self.shoot(enemy_bullet_group, player_ref=player)
            return

        if random.randint(1, 240) == 1:
            self.is_idling = True
            self.idling_counter = 60
            self.update_action(ActionTypes.IDLE)
            return

        from .enemy_special import enemy_ignores_spikes_and_ledges, is_calc_tank_enemy

        ai_left = self.direction == -1
        ai_right = self.direction == 1
        ignore_hazards = enemy_ignores_spikes_and_ledges(self)
        no_jump = is_calc_tank_enemy(self)
        if not ignore_hazards and self.feet_on_spike_damage(world):
            self.direction *= -1
            ai_left = self.direction == -1
            ai_right = self.direction == 1
        if not ignore_hazards:
            ai_left, ai_right = self._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
        ledge_brake = False
        if not ignore_hazards and not no_jump and not self.is_in_air and (ai_left or ai_right):
            fwd = -1 if ai_left else 1
            self._try_enemy_jump_for_step_up(world, area_group, fwd)
            if self._ledge_clear_ahead(world, area_group, fwd):
                self.direction *= -1
                ai_left = ai_right = False
                self.move_counter = 0
                ledge_brake = True
        elif not ignore_hazards and no_jump and not self.is_in_air and (ai_left or ai_right):
            fwd = -1 if ai_left else 1
            if self._ledge_clear_ahead(world, area_group, fwd):
                self.direction *= -1
                ai_left = ai_right = False
                self.move_counter = 0
                ledge_brake = True
        self.move(ai_left, ai_right, world, area_group, enemy_group=enemy_group, player_ref=player)
        if ledge_brake:
            self.update_action(ActionTypes.IDLE)
        else:
            self.update_action(ActionTypes.RUN)
        self.move_counter += 1
        if self.move_counter >= TILE_SIZE * 3:
            self.direction *= -1
            self.move_counter = 0

    def shoot(self, bullet_group, player_ref=None):
        if bullet_group is None:
            return
        if self.shoot_cooldown == 0:
            from .enemy_special import effective_shoot_cooldown, spawn_enemy_bullet_at_player

            self.shoot_cooldown = effective_shoot_cooldown(self)
            from . import game_audio
            from .enemy_special import is_sin_wave_enemy

            if is_sin_wave_enemy(self):
                game_audio.play_sin_attack(at_rect=self.rect, enemy=self)
            else:
                game_audio.play_monster_attack_if_visible(self.rect, self)
            if player_ref is not None and player_ref.is_alive:
                spawn_enemy_bullet_at_player(self, bullet_group, player_ref)
            else:
                ox = self.rect.centerx + 0.6 * self.width * self.direction
                oy = self.rect.centery
                bullet_group.add(EnemyBullet(ox, oy, self.direction))

    def update_cooldowns(self):
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1
