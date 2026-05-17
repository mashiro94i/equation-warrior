"""玩家方程式子彈 + 敵人子彈 + Sigma 數字彈"""
import math

import pygame

from .constants import (
    ENEMY_BULLET_DAMAGE,
    GREEN, HEAL_SIGMOID_HEAL_AMOUNT,
    INTEGRAL_HIT_BULLET_DAMAGE_MULT, INTEGRAL_HIT_BULLET_RADIUS_MULT,
    INTEGRAL_XY_EXTEND_MAX_PX, PURPLE, RED,
    SCREEN_HEIGHT, SCREEN_WIDTH, YELLOW,
    player_attack_hit_damage,
)
from .enums import IntegralAxis, PowerType
from .equation import Equation


class MathProjectile(pygame.sprite.Sprite):
    """方程式子彈。

    LINEAR: vector 運動，傳入 direction = (dx_norm, dy_norm)，每 frame 走 SPEED_PX
    QUADRATIC: 函數運動，world_x ± SPEED_PX，y = f(world_x)
    """
    SPEED_PX = 6

    def __init__(self, origin, power, params, facing, direction=None, *, healing_shot: bool = False):
        super().__init__()
        self.origin = (origin[0], origin[1])
        self.power = power
        self.params = dict(params)
        self.facing = facing
        self.direction = direction
        self.world_x = 0.0
        self.world_y = 0.0
        self.healing_shot = bool(healing_shot)
        self.hit_damage = player_attack_hit_damage()
        self._bullet_radius = 7
        self._enlarged_by_integral = False
        self._pierced_enemy_ids = set()
        self._rebuild_bullet_image()
        if power == PowerType.LINEAR:
            self.rect = self.image.get_rect(center=self.origin)
        else:
            y0 = -Equation.evaluate(power, params, 0)
            self.rect = self.image.get_rect(center=(self.origin[0], self.origin[1] + y0))

    def _rebuild_bullet_image(self):
        r = max(3, int(self._bullet_radius))
        d = r * 2 + 2
        self.image = pygame.Surface((d, d), pygame.SRCALPHA)
        if self.healing_shot:
            pygame.draw.circle(self.image, GREEN, (r + 1, r + 1), r)
            pygame.draw.circle(self.image, (180, 255, 200), (r + 1, r + 1), r, 1)
        else:
            pygame.draw.circle(self.image, RED, (r + 1, r + 1), r)
            pygame.draw.circle(self.image, YELLOW, (r + 1, r + 1), r, 1)

    def travel_angle_rad(self) -> float:
        """數學座標下的飛行方向角（供平方塊分裂彈使用）。"""
        if self.power == PowerType.LINEAR and self.direction is not None:
            dx, dy = self.direction
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                return 0.0
            return math.atan2(float(dy), float(dx))
        return 0.0 if self.facing >= 0 else math.pi

    def apply_integral_enlarge(self):
        if self._enlarged_by_integral:
            return
        self._enlarged_by_integral = True
        cx, cy = self.rect.center
        self._bullet_radius *= INTEGRAL_HIT_BULLET_RADIUS_MULT
        self.hit_damage = float(self.hit_damage) * INTEGRAL_HIT_BULLET_DAMAGE_MULT
        self._rebuild_bullet_image()
        self.rect = self.image.get_rect(center=(cx, cy))

    def update(self, world, enemy_group, player, area_group=None):
        prev_x, prev_y = self.rect.centerx, self.rect.centery
        if self.power == PowerType.LINEAR and self.direction is not None:
            dx, dy = self.direction
            self.world_x += self.SPEED_PX * dx
            self.world_y += self.SPEED_PX * dy
            sx = self.origin[0] + self.world_x
            sy = self.origin[1] - self.world_y
            self.rect.center = (int(sx), int(sy))
        else:
            self.world_x += self.SPEED_PX * self.facing
            rel_y = -Equation.evaluate(self.power, self.params, self.world_x)
            self.rect.center = (self.origin[0] + self.world_x, self.origin[1] + rel_y)

        if not pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT).colliderect(self.rect):
            self.kill()
            return
        for _img, rect in world.obstacle_list:
            if rect.colliderect(self.rect):
                self.on_wall_hit()
                return
        if area_group is not None:
            for area in list(area_group):
                if area.intersects_rect(self.rect):
                    path = self._future_motion_path(160)
                    if path:
                        area.apply_motion_path(path)
                    else:
                        adx = float(self.rect.centerx - prev_x)
                        ady = float(self.rect.centery - prev_y)
                        if abs(adx) < 1e-6 and abs(ady) < 1e-6:
                            if self.power == PowerType.LINEAR and self.direction is not None:
                                adx, ady = self.direction
                            else:
                                adx, ady = float(self.facing), 0.0
                        area.apply_push_from_direction(adx, ady)
                    self.kill()
                    return
        for enemy in list(enemy_group):
            if enemy.is_alive and pygame.sprite.collide_rect(self, enemy):
                from .enemy_special import can_take_projectile_damage, on_projectile_hit

                if not can_take_projectile_damage(enemy, self):
                    self.kill()
                    return
                eid = id(enemy)
                if self.healing_shot:
                    on_projectile_hit(enemy, self)
                    self.kill()
                    return
                if self._enlarged_by_integral:
                    if eid not in self._pierced_enemy_ids:
                        on_projectile_hit(enemy, self)
                        self._pierced_enemy_ids.add(eid)
                else:
                    on_projectile_hit(enemy, self)
                    self.kill()
                    return

    def on_wall_hit(self):
        self.kill()

    def _future_motion_path(self, steps: int = 120):
        out = []
        if self.power == PowerType.LINEAR and self.direction is not None:
            dx, dy = self.direction
            wx = float(self.world_x)
            wy = float(self.world_y)
            for _ in range(max(1, int(steps))):
                wx += self.SPEED_PX * dx
                wy += self.SPEED_PX * dy
                sx = self.origin[0] + wx
                sy = self.origin[1] - wy
                if sx < 0 or sx >= SCREEN_WIDTH or sy < 0 or sy >= SCREEN_HEIGHT:
                    break
                out.append((sx, sy))
            return out
        if self.power == PowerType.QUADRATIC:
            wx = float(self.world_x)
            for _ in range(max(1, int(steps))):
                wx += self.SPEED_PX * self.facing
                rel_y = -Equation.evaluate(self.power, self.params, wx)
                sx = self.origin[0] + wx
                sy = self.origin[1] + rel_y
                if sx < 0 or sx >= SCREEN_WIDTH or sy < 0 or sy >= SCREEN_HEIGHT:
                    break
                out.append((sx, sy))
        return out


class NumericProjectile(pygame.sprite.Sprite):
    """Sigma 數字彈：等速直線，互動近似一般子彈"""
    SPEED = 6

    def __init__(self, origin, dx_norm: float, dy_norm: float, value: int):
        super().__init__()
        self.value = int(value)
        self.dx = float(dx_norm)
        self.dy = float(dy_norm)
        self.hit_damage = self._sigma_damage_from_value(self.value)
        self.image = pygame.Surface((20, 16), pygame.SRCALPHA)
        self._redraw()
        self.rect = self.image.get_rect(center=origin)

    def _redraw(self):
        self.image.fill((0, 0, 0, 0))
        pygame.draw.rect(self.image, PURPLE, (0, 0, 20, 16))
        font = pygame.font.Font(None, 18)
        t = font.render(str(self.value), True, YELLOW)
        self.image.blit(t, t.get_rect(center=(10, 8)))

    @staticmethod
    def _sigma_damage_from_value(n: int) -> float:
        base = player_attack_hit_damage()
        if n <= 0:
            return 0.0
        if n < 4:
            return base * (float(n) / 4.0)
        if n < 10:
            return float(base)
        return float(base) * (1.8 ** float(n - 9))

    def _future_motion_path(self, steps: int = 160):
        out = []
        sx = float(self.rect.centerx)
        sy = float(self.rect.centery)
        for _ in range(max(1, int(steps))):
            sx += self.SPEED * self.dx
            sy -= self.SPEED * self.dy
            if sx < 0 or sx >= SCREEN_WIDTH or sy < 0 or sy >= SCREEN_HEIGHT:
                break
            out.append((sx, sy))
        return out

    def update(self, world, enemy_group, area_group=None):
        prev_x, prev_y = self.rect.centerx, self.rect.centery
        self.rect.x += int(self.SPEED * self.dx)
        self.rect.y -= int(self.SPEED * self.dy)
        if not pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT).colliderect(self.rect):
            self.kill()
            return
        for _img, rect in world.obstacle_list:
            if rect.colliderect(self.rect):
                self.kill()
                return
        if area_group is not None:
            for area in list(area_group):
                if area.intersects_rect(self.rect):
                    path = self._future_motion_path(160)
                    if path:
                        area.apply_motion_path(path)
                    else:
                        adx = float(self.rect.centerx - prev_x)
                        ady = float(self.rect.centery - prev_y)
                        if abs(adx) < 1e-6 and abs(ady) < 1e-6:
                            adx, ady = self.dx, -self.dy
                        area.apply_push_from_direction(adx, ady)
                    self.kill()
                    return
        for enemy in list(enemy_group):
            if enemy.is_alive and pygame.sprite.collide_rect(self, enemy):
                from .enemy_special import can_take_projectile_damage, on_projectile_hit

                if can_take_projectile_damage(enemy, self):
                    if self.hit_damage > 0:
                        on_projectile_hit(enemy, self)
                self.kill()
                return


class EnemyBullet(pygame.sprite.Sprite):
    """直線敵彈；受積分影響時比照我方 MathProjectile：圓形半徑放大，不拉長成細長矩形。"""

    SPEED = 7
    DAMAGE = ENEMY_BULLET_DAMAGE
    _BASE_RADIUS = 5.0
    _MAX_RADIUS = 20.0

    def __init__(self, x, y, direction, *, vy: float = 0.0):
        super().__init__()
        self.direction = int(direction) if direction else 1
        self.vx = float(self.direction) * float(self.SPEED)
        self.vy = float(vy)
        self.is_healing = False
        self.heal_amount = 0.0
        self._bullet_radius = float(self._BASE_RADIUS)
        self._enlarged_by_integral_block = False
        self.rect = pygame.Rect(0, 0, 1, 1)
        self.rect.center = (int(x), int(y))
        self._rebuild_visual()

    def _rebuild_visual(self):
        cx, cy = self.rect.center
        r = max(3, int(round(self._bullet_radius)))
        d = r * 2 + 2
        self.image = pygame.Surface((d, d), pygame.SRCALPHA)
        if self.is_healing:
            pygame.draw.circle(self.image, GREEN, (r + 1, r + 1), r)
        else:
            pygame.draw.circle(self.image, RED, (r + 1, r + 1), r)
            pygame.draw.circle(self.image, YELLOW, (r + 1, r + 1), r, 1)
        self.rect = self.image.get_rect(center=(cx, cy))

    def apply_integral_enlarge(self):
        """積分塊命中：與我方 MathProjectile.apply_integral_enlarge 相同（僅第一次生效）。"""
        if self._enlarged_by_integral_block:
            return
        self._enlarged_by_integral_block = True
        cx, cy = self.rect.center
        self._bullet_radius = min(self._MAX_RADIUS, self._bullet_radius * INTEGRAL_HIT_BULLET_RADIUS_MULT)
        self._rebuild_visual()
        self.rect.center = (cx, cy)

    def apply_integral_extend(self, axis: IntegralAxis, delta: int):
        """滑鼠 ∫x/∫y 點敵彈：維持圓形，依伸長量換算半徑（比照玩家放大手感，避免長條撞牆）。"""
        del axis  # 舊 API 保留；圓形彈不分軸向拉伸
        d = int(min(max(0, delta), INTEGRAL_XY_EXTEND_MAX_PX))
        if d <= 0:
            return
        cx, cy = self.rect.center
        t = d / float(INTEGRAL_XY_EXTEND_MAX_PX)
        mult = 1.0 + t * (INTEGRAL_HIT_BULLET_RADIUS_MULT - 1.0)
        self._bullet_radius = min(self._MAX_RADIUS, self._bullet_radius * mult)
        self._rebuild_visual()
        self.rect.center = (cx, cy)

    def apply_sigmoid_heal(self, heal_amount: float):
        self.is_healing = True
        self.heal_amount = float(heal_amount)
        self._rebuild_visual()

    def collision_rect(self) -> pygame.Rect:
        return self.rect.copy()

    def update(self, world, player, area_group=None):
        self.rect.x += int(round(self.vx))
        if self.vy:
            self.rect.y += int(round(self.vy))
        hr = self.collision_rect()
        if hr.right < 0 or hr.left > SCREEN_WIDTH:
            self.kill()
            return
        for _img, rect in world.obstacle_list:
            if rect.colliderect(hr):
                self.kill()
                return
        if area_group is not None:
            for area in list(area_group):
                if area.intersects_rect(hr):
                    area.register_bullet_hit()
                    self.kill()
                    return
        if hr.colliderect(player.rect) and player.is_alive:
            if self.is_healing:
                player.heal(self.heal_amount)
            else:
                player.take_damage(self.DAMAGE)
            self.kill()
