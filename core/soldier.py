"""Soldier base + Player + Enemy"""
import os
import random
import pygame

from .assets import fallback_enemy_frame, fallback_player_frame
from .constants import (
    GRAVITY, HP_DECIMAL_PLACES, JUMP_IMPULSE, PLAYER_MAX_HP,
    SCREEN_HEIGHT, SCREEN_WIDTH, TILE_SIZE,
)
from .enums import ActionTypes, CharacterTypes, IntegralAxis, PlayerMode
from .gameplay import clamp_degree, round_hp
from .projectile import EnemyBullet


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
        fallback_fn = fallback_player_frame if is_player else fallback_enemy_frame
        for action in ActionTypes:
            frames = []
            url = f"./assets/img/{self.char_type.value}/{action.value}"
            if os.path.isdir(url):
                pngs = sorted(f for f in os.listdir(url) if f.endswith('.png'))
                for fname in pngs:
                    path = os.path.join(url, fname)
                    try:
                        img = pygame.image.load(path).convert_alpha()
                        img = pygame.transform.scale(
                            img,
                            (int(img.get_width() * scale), int(img.get_height() * scale)),
                        )
                        frames.append(img)
                    except pygame.error:
                        pass
            if not frames:
                frames = [fallback_fn(scale)]
            anim[action] = frames
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
        if self.char_type == CharacterTypes.Player and enemy_group is not None:
            for e in enemy_group:
                if getattr(e, "is_alive", True) and e.rect.colliderect(test_rect):
                    return True
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
        if self.char_type == CharacterTypes.Player and enemy_group is not None:
            for e in enemy_group:
                if not getattr(e, "is_alive", True):
                    continue
                er = e.rect
                if er.left <= foot_x <= er.right:
                    gap = bottom_y - er.top
                    if -snap_up <= gap <= snap_down:
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
            if self.char_type == CharacterTypes.Player and enemy_group is not None:
                for e in enemy_group:
                    if not e.is_alive:
                        continue
                    if e.rect.colliderect(test):
                        push = e.rect.bottom - self.rect.top
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
        if self.char_type == CharacterTypes.Player and enemy_group is not None:
            for e in enemy_group:
                if not e.is_alive:
                    continue
                if e.rect.colliderect(test):
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

    def move(self, moving_left, moving_right, world, area_group=None, enemy_group=None, player_ref=None):
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

        if self.rect.left + dx < 0:
            dx = -self.rect.left
        if self.rect.right + dx > SCREEN_WIDTH:
            dx = SCREEN_WIDTH - self.rect.right

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
            on_ground = any(e.is_alive and e.rect.colliderect(feet) for e in enemy_group)

        if self.char_type == CharacterTypes.Player and enemy_group is not None and not on_ground:
            for e in enemy_group:
                if not e.is_alive:
                    continue
                if self.rect.right <= e.rect.left or self.rect.left >= e.rect.right:
                    continue
                gap = e.rect.top - self.rect.bottom
                if 0 <= gap <= self.GROUND_SNAP_PX + 2:
                    on_ground = True
                    self.rect.y += gap
                    self.vel_y = 0
                    break

        if on_ground:
            self.is_in_air = False
            if self.vel_y > 0:
                self.vel_y = 0
        else:
            self.is_in_air = True

        self._depenetrate_world_obstacles_only(world)

        if self.rect.y > SCREEN_HEIGHT:
            self.health = 0.0

    def take_damage(self, dmg):
        if not self.is_alive:
            return
        self.health = round_hp(max(0.0, float(self.health) - float(dmg)), HP_DECIMAL_PLACES)

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
        super().__init__(CharacterTypes.Player, x, y, 1.0, 5)
        self.max_health = float(PLAYER_MAX_HP)
        self.health = float(PLAYER_MAX_HP)
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

    def move(self, moving_left, moving_right, world, area_group=None, enemy_group=None):
        super().move(moving_left, moving_right, world, area_group, enemy_group=enemy_group, player_ref=None)
        if self.rect.top < 0:
            self.rect.top = 0
            if self.vel_y < 0:
                self.vel_y = max(2.0, -self.vel_y * self.PLAYER_TOP_BOUNCE)
            self.is_in_air = True


class Enemy(Soldier):
    SHOOT_COOLDOWN_FRAMES = 80

    def __init__(self, x, y):
        super().__init__(CharacterTypes.Enemy, x, y, 1.0, 2)
        self.calc_frozen = False

    def ai(self, player, world, enemy_bullet_group, area_group=None):
        if not self.is_alive or not player.is_alive:
            return
        if self.calc_frozen:
            self.update_action(ActionTypes.IDLE)
            self.move(False, False, world, area_group, player_ref=player)
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
        self.move(ai_left, ai_right, world, area_group, player_ref=player)
        self.update_action(ActionTypes.RUN)
        self.move_counter += 1
        if self.move_counter >= TILE_SIZE * 3:
            self.direction *= -1
            self.move_counter = 0

    def shoot(self, bullet_group):
        if self.shoot_cooldown == 0:
            self.shoot_cooldown = self.SHOOT_COOLDOWN_FRAMES
            bullet = EnemyBullet(
                self.rect.centerx + 0.6 * self.width * self.direction,
                self.rect.centery,
                self.direction,
            )
            bullet_group.add(bullet)

    def update_cooldowns(self):
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1
