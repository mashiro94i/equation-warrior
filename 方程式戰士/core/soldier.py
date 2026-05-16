"""Soldier base + Player + Enemy"""
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
}

ENEMY_KENNEY_TILE_RGB = {
    65834: (255, 100, 100),
    65835: (255, 115, 105),
    65837: (235, 95, 105),
    65838: (245, 85, 95),
    65840: (240, 90, 90),
    65841: (235, 88, 92),
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

    def _collides_with_world_or_area(self, test_rect, world, area_group=None):
        for _img, rect in world.obstacle_list:
            if rect.colliderect(test_rect):
                return True
        if area_group is not None:
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
        dx = 0
        if moving_left:
            dx = -self.speed
            self.is_x_flip = True
            self.direction = -1
        if moving_right:
            dx = self.speed
            self.is_x_flip = False
            self.direction = 1
        if self.is_aiming and self.char_type == CharacterTypes.Player:
            dx //= 2

        if self.is_in_air:
            self.is_jump = False
        elif self.is_jump:
            self.vel_y = JUMP_IMPULSE
            self.is_jump = False
            self.is_in_air = True
            if self.char_type == CharacterTypes.Player:
                from . import game_audio

                game_audio.play_jump()

        self.vel_y += GRAVITY
        if self.vel_y > 14:
            self.vel_y = 14
        dy = self.vel_y

        horizontal_blocked = False
        micro_lift = 0

        world_blocks = False
        for _img, rect in world.obstacle_list:
            if rect.colliderect(self.rect.x + dx, self.rect.y, self.width, self.height - 1):
                world_blocks = True
                break
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

        if area_group is not None and dx != 0:
            x_test = pygame.Rect(
                self.rect.x + dx,
                self.rect.y + self.SIDE_COLLISION_TRIM // 2,
                self.width,
                max(1, self.height - self.SIDE_COLLISION_TRIM),
            )
            area_blocks = any(area.intersects_rect(x_test) for area in list(area_group))
            if area_blocks:
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

        move_sign = -1 if moving_left else (1 if moving_right else 0)
        if horizontal_blocked and move_sign != 0:
            step_dx = self.speed * move_sign
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

        dy_resolved, hit_ceiling = self._resolve_vertical_against_solids(
            dy, world, area_group, enemy_group, player_ref,
        )
        if hit_ceiling:
            self.vel_y = 0
        if dy_resolved < dy and dy > 0:
            self.vel_y = 0
        self.rect.y += dy_resolved

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

        if on_ground:
            self.is_in_air = False
            if self.vel_y > 0:
                self.vel_y = 0
            self._airborne_since_ms = None
            self._long_fall_sfx_played = False
        else:
            self.is_in_air = True
            self._update_long_fall_sfx()

        self._depenetrate_world_obstacles_only(world)

        if self.char_type == CharacterTypes.Enemy:
            self._try_step_off_spikes(world)

        if self.rect.y > SCREEN_HEIGHT:
            self.health = 0.0

        screen_scroll = 0
        if self.char_type == CharacterTypes.Player and dx != 0:
            scroll_max = world.scroll_max_px(SCREEN_WIDTH)
            if (
                self.rect.right > SCREEN_WIDTH - SCROLL_THRESH
                and background_scroll < scroll_max
            ) or (self.rect.left < SCROLL_THRESH and background_scroll > 0):
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

        game_audio.play_fall()
        self._long_fall_sfx_played = True

    def take_damage(self, dmg):
        if not self.is_alive:
            return
        self.health = round_hp(max(0.0, float(self.health) - float(dmg)), HP_DECIMAL_PLACES)
        if self.char_type in (CharacterTypes.Player, CharacterTypes.Enemy):
            from . import game_audio

            game_audio.play_player_hurt()

    def heal(self, hp):
        self.health = round_hp(
            min(float(self.max_health), float(self.health) + float(hp)),
            HP_DECIMAL_PLACES,
        )

    def check_alive(self):
        if self.health <= 0 and self.is_alive:
            self.is_alive = False
            self.update_action(ActionTypes.DEATH)

    def update_action(self, new_action):
        if self.action != new_action:
            self.action = new_action
            self.frame_index = 0
            self.update_time = pygame.time.get_ticks()

    def update_animation(self):
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

    def draw(self, surface):
        img = self.image
        if self.is_x_flip:
            img = pygame.transform.flip(img, True, False)
        surface.blit(img, self.rect)


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
        # 0 次彩蛋「啵」：由主迴圈依此計數播放（測試可 assert）
        self.pop_sound_requests = 0

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
        self._apply_kenney_walk_pair_if_any()

    def _apply_kenney_walk_pair_if_any(self) -> None:
        pair = ENEMY_KENNEY_WALK_PAIR_GIDS.get(self.enemy_gid)
        if pair is None:
            return
        gid_a, gid_b = pair
        px = int(34 * ENEMY_VISUAL_SCALE)
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

    def _ledge_clear_ahead(self, world, area_group, forward: int) -> bool:
        """True = 行進方向前緣腳下沒有支撐（懸崖），應煞車／轉向。"""
        if forward == 0:
            return False
        margin = max(int(self.speed), 3)
        lead_cx = self.rect.centerx + forward * (self.width // 2 + margin)
        top = self.rect.bottom
        h = int(TILE_SIZE * 2) + 24
        probe = pygame.Rect(int(lead_cx - 4), int(top), 8, h)
        for _img, rect in world.obstacle_list:
            if rect.colliderect(probe):
                return False
        if area_group is not None:
            for area in list(area_group):
                if area.intersects_rect(probe):
                    return False
        return True

    def _feet_rect_for_spike(self, body: pygame.Rect | None = None) -> pygame.Rect:
        r = self.rect if body is None else body
        margin = max(4, min(14, r.width // 4))
        return pygame.Rect(
            r.left + margin,
            r.bottom - 12,
            max(6, r.width - 2 * margin),
            14,
        )

    def feet_on_spike_damage(self, world) -> bool:
        """腳底是否踩在伸出中的尖刺上（與避刺邏輯一致，不用整體碰撞箱）。"""
        if not world.spikes_extended:
            return False
        feet = self._feet_rect_for_spike()
        return any(feet.colliderect(sr) for sr in world.spike_damage_rects())

    def _would_overlap_spike_damage_feet(self, world, step_dx: int) -> bool:
        """下一步水平位移後，腳底是否踩進伸出中的尖刺區。"""
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
        for try_dx in (
            self.speed * self.direction,
            -self.speed * self.direction,
            self.speed,
            -self.speed,
            self.speed * 2,
            -self.speed * 2,
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
        spd = max(1, int(round(self.speed)))
        if ai_left and self._would_overlap_spike_damage_feet(world, -spd):
            ai_left = False
        if ai_right and self._would_overlap_spike_damage_feet(world, spd):
            ai_right = False
        return ai_left, ai_right

    def _ai_patrol_no_shoot(self, player, world, area_group=None):
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

        ai_left = self.direction == -1
        ai_right = self.direction == 1
        if self.feet_on_spike_damage(world):
            self.direction *= -1
            ai_left = self.direction == -1
            ai_right = self.direction == 1
        ai_left, ai_right = self._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
        ledge_brake = False
        if not self.is_in_air and (ai_left or ai_right):
            fwd = -1 if ai_left else 1
            if self._ledge_clear_ahead(world, area_group, fwd):
                self.direction *= -1
                ai_left = ai_right = False
                self.move_counter = 0
                ledge_brake = True
        self.move(ai_left, ai_right, world, area_group, player_ref=player)
        if ledge_brake:
            self.update_action(ActionTypes.IDLE)
        else:
            self.update_action(ActionTypes.RUN)
        self.move_counter += 1
        if self.move_counter >= TILE_SIZE * 3:
            self.direction *= -1
            self.move_counter = 0

    def _ai_chase_contact_melee(self, player, world, area_group=None):
        """朝玩家追擊；65834 改為週期性向前衝撞單次扣血（站頭頂除外）。"""
        dx = player.rect.centerx - self.rect.centerx
        dy_vertical = abs(player.rect.centery - self.rect.centery)
        now = pygame.time.get_ticks()

        if self.enemy_gid == GID_CHASHER_MELEE_ENEMY and self._bump_ticks_remaining > 0:
            self._bump_ticks_remaining -= 1
            spd = max(5, int(round(self.speed * 2.5)))
            step = spd * self.direction
            if not self._would_overlap_spike_damage_feet(world, step):
                old_x = self.rect.x
                self.rect.x += step
                for _img, r in world.obstacle_list:
                    if self.rect.colliderect(r):
                        self.rect.x = old_x
                        break
                if (
                    player.is_alive
                    and not player_standing_on_enemy_head(player, self)
                    and self.rect.colliderect(player.rect)
                    and not self._bump_damage_done
                ):
                    from . import game_audio

                    game_audio.play_monster_attack()
                    player.take_damage(ENEMY_BULLET_DAMAGE)
                    self._bump_damage_done = True
            self.update_action(ActionTypes.RUN)
            self.update_animation()
            return

        self.direction = 1 if dx >= 0 else -1
        self.facing = self.direction
        ai_left = dx < -4
        ai_right = dx > 4
        if self.feet_on_spike_damage(world):
            self.direction *= -1
            ai_left = self.direction == -1
            ai_right = self.direction == 1
        ai_left, ai_right = self._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
        ledge_brake = False
        if not self.is_in_air and (ai_left or ai_right):
            fwd = -1 if ai_left else 1
            if self._ledge_clear_ahead(world, area_group, fwd):
                ai_left = ai_right = False
                ledge_brake = True
        self.move(ai_left, ai_right, world, area_group, player_ref=player)
        if ledge_brake:
            self.update_action(ActionTypes.IDLE)
        elif ai_left or ai_right:
            self.update_action(ActionTypes.RUN)
        else:
            self.update_action(ActionTypes.IDLE)

        if self.enemy_gid != GID_CHASHER_MELEE_ENEMY:
            return
        if (
            self._bump_ticks_remaining <= 0
            and now >= self._bump_next_ready_ms
            and not self.is_in_air
            and dy_vertical < int(TILE_SIZE * 0.95)
            and abs(dx) < TILE_SIZE * 3
            and player.is_alive
        ):
            self._bump_ticks_remaining = 18
            self._bump_damage_done = False
            self._bump_next_ready_ms = now + 1200
            self.direction = 1 if dx >= 0 else -1
            self.facing = self.direction

    def ai(self, player, world, enemy_bullet_group, area_group=None):
        if not self.is_alive or not player.is_alive:
            return
        if self.calc_frozen:
            self.update_action(ActionTypes.IDLE)
            self.move(False, False, world, area_group, player_ref=player)
            return
        if self.enemy_gid == GID_CHASHER_MELEE_ENEMY:
            chase_vision = pygame.Rect(0, 0, 440, 280)
            chase_vision.center = self.rect.center
            if chase_vision.colliderect(player.rect):
                self._ai_chase_contact_melee(player, world, area_group)
            else:
                self._ai_patrol_no_shoot(player, world, area_group)
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
            self.shoot(enemy_bullet_group)
            return

        if random.randint(1, 240) == 1:
            self.is_idling = True
            self.idling_counter = 60
            self.update_action(ActionTypes.IDLE)
            return

        ai_left = self.direction == -1
        ai_right = self.direction == 1
        if self.feet_on_spike_damage(world):
            self.direction *= -1
            ai_left = self.direction == -1
            ai_right = self.direction == 1
        ai_left, ai_right = self._filter_horizontal_move_for_spikes(world, ai_left, ai_right)
        ledge_brake = False
        if not self.is_in_air and (ai_left or ai_right):
            fwd = -1 if ai_left else 1
            if self._ledge_clear_ahead(world, area_group, fwd):
                self.direction *= -1
                ai_left = ai_right = False
                self.move_counter = 0
                ledge_brake = True
        self.move(ai_left, ai_right, world, area_group, player_ref=player)
        if ledge_brake:
            self.update_action(ActionTypes.IDLE)
        else:
            self.update_action(ActionTypes.RUN)
        self.move_counter += 1
        if self.move_counter >= TILE_SIZE * 3:
            self.direction *= -1
            self.move_counter = 0

    def shoot(self, bullet_group):
        if self.shoot_cooldown == 0:
            self.shoot_cooldown = self.SHOOT_COOLDOWN_FRAMES
            from . import game_audio

            game_audio.play_monster_attack()
            bullet = EnemyBullet(
                self.rect.centerx + 0.6 * self.width * self.direction,
                self.rect.centery,
                self.direction,
            )
            bullet_group.add(bullet)

    def update_cooldowns(self):
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1
