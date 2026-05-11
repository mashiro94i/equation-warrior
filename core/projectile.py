"""玩家方程式子彈 + 敵人子彈 + Sigma 數字彈"""
import pygame

from .constants import (
    GREEN, INTEGRAL_HIT_BULLET_DAMAGE_MULT, INTEGRAL_HIT_BULLET_RADIUS_MULT,
    INTEGRAL_XY_EXTEND_MAX_PX, PLAYER_PROJECTILE_DAMAGE, PURPLE, RED,
    SCREEN_HEIGHT, SCREEN_WIDTH, YELLOW,
)
from .enums import IntegralAxis, PowerType
from .equation import Equation


class MathProjectile(pygame.sprite.Sprite):
    """方程式子彈。

    LINEAR: vector 運動，傳入 direction = (dx_norm, dy_norm)，每 frame 走 SPEED_PX
    QUADRATIC: 函數運動，world_x ± SPEED_PX，y = f(world_x)
    """
    SPEED_PX = 6
    DAMAGE = PLAYER_PROJECTILE_DAMAGE

    def __init__(self, origin, power, params, facing, direction=None):
        super().__init__()
        self.origin = (origin[0], origin[1])
        self.power = power
        self.params = dict(params)
        self.facing = facing
        self.direction = direction
        self.world_x = 0.0
        self.world_y = 0.0
        self.hit_damage = float(PLAYER_PROJECTILE_DAMAGE)
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
        pygame.draw.circle(self.image, RED, (r + 1, r + 1), r)
        pygame.draw.circle(self.image, YELLOW, (r + 1, r + 1), r, 1)

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
                eid = id(enemy)
                if self._enlarged_by_integral:
                    if eid not in self._pierced_enemy_ids:
                        enemy.take_damage(self.hit_damage)
                        self._pierced_enemy_ids.add(eid)
                else:
                    enemy.take_damage(self.hit_damage)
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
    """Sigma 數字彈：等速直線，傷害=顯示值，只打敵人"""
    SPEED = 6

    def __init__(self, origin, dx_norm: float, dy_norm: float, value: int):
        super().__init__()
        self.value = int(value)
        self.dx = float(dx_norm)
        self.dy = float(dy_norm)
        self.image = pygame.Surface((20, 16), pygame.SRCALPHA)
        self._redraw()
        self.rect = self.image.get_rect(center=origin)

    def _redraw(self):
        self.image.fill((0, 0, 0, 0))
        pygame.draw.rect(self.image, PURPLE, (0, 0, 20, 16))
        font = pygame.font.Font(None, 18)
        t = font.render(str(self.value), True, YELLOW)
        self.image.blit(t, t.get_rect(center=(10, 8)))

    def update(self, world, enemy_group):
        self.rect.x += int(self.SPEED * self.dx)
        self.rect.y -= int(self.SPEED * self.dy)
        if not pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT).colliderect(self.rect):
            self.kill()
            return
        for _img, rect in world.obstacle_list:
            if rect.colliderect(self.rect):
                self.kill()
                return
        for enemy in list(enemy_group):
            if enemy.is_alive and pygame.sprite.collide_rect(self, enemy):
                if self.value > 0:
                    enemy.take_damage(self.value)
                self.kill()
                return


class EnemyBullet(pygame.sprite.Sprite):
    SPEED = 7
    DAMAGE = 100

    def __init__(self, x, y, direction):
        super().__init__()
        self.direction = direction
        self.extend_x = 0
        self.extend_y = 0
        self.is_healing = False
        self.heal_amount = 0.0
        self.image = pygame.Surface((10, 6), pygame.SRCALPHA)
        pygame.draw.rect(self.image, RED, (0, 0, 10, 6))
        self.rect = self.image.get_rect(center=(x, y))

    def apply_integral_extend(self, axis: IntegralAxis, delta: int):
        d = int(min(max(0, delta), INTEGRAL_XY_EXTEND_MAX_PX))
        if d <= 0:
            return
        if axis == IntegralAxis.Y:
            self.extend_y = min(INTEGRAL_XY_EXTEND_MAX_PX, self.extend_y + d)
        else:
            self.extend_x = min(INTEGRAL_XY_EXTEND_MAX_PX, self.extend_x + d)

    def apply_sigmoid_heal(self, heal_amount: float):
        self.is_healing = True
        self.heal_amount = float(heal_amount)
        pygame.draw.rect(self.image, GREEN, (0, 0, 10, 6))

    def collision_rect(self) -> pygame.Rect:
        r = self.rect.copy()
        if self.extend_y:
            r.height += self.extend_y
        if self.extend_x:
            if self.direction >= 0:
                r.width += self.extend_x
            else:
                r.x -= self.extend_x
                r.width += self.extend_x
        return r

    def update(self, world, player, area_group=None):
        self.rect.x += self.SPEED * self.direction
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
