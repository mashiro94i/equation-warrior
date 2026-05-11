"""下落微分／積分符號塊"""
import pygame

from .area_entity import (
    build_area_bodies_from_circle,
    build_area_bodies_from_polygon,
    build_area_bodies_from_shifted_stroke,
)
from .constants import (
    CALC_BLOCK_GRAVITY, CALC_BLOCK_H, CALC_BLOCK_INTEGRAL_H, CALC_BLOCK_W,
    INTEGRAL_XY_EXTEND_MAX_PX,
    SCREEN_HEIGHT, SCREEN_WIDTH, WHITE,
)
from .projectile import MathProjectile
from .fonts import get_font
from .enums import IntegralAxis


class CalculusBlock(pygame.sprite.Sprite):
    """kind: 'derivative' | 'integral'"""

    def __init__(self, center_xy, kind: str, axis: str = "y"):
        super().__init__()
        self.kind = kind
        self.axis = axis.lower()
        self.vel_y = 0.0
        self._just_spawned = True
        self._build_image()
        self.rect = self.image.get_rect(center=center_xy)

    def _build_image(self):
        h = CALC_BLOCK_H if self.kind == "derivative" else CALC_BLOCK_INTEGRAL_H
        surf = pygame.Surface((CALC_BLOCK_W, h), pygame.SRCALPHA)
        surf.fill((40, 40, 50, 230))
        pygame.draw.rect(surf, WHITE, surf.get_rect(), 2)
        if self.kind == "derivative":
            font = get_font(15, bold=True)
            num = font.render("d", True, WHITE)
            den = font.render("dx", True, WHITE)
            cx = CALC_BLOCK_W // 2
            surf.blit(num, num.get_rect(center=(cx, 9)))
            pygame.draw.line(surf, WHITE, (cx - 10, 13), (cx + 10, 13), 2)
            surf.blit(den, den.get_rect(center=(cx, 20)))
        else:
            font = get_font(22, bold=True)
            label = "∫x" if self.axis == "x" else "∫y"
            txt = font.render(label, True, WHITE)
            surf.blit(txt, txt.get_rect(center=(CALC_BLOCK_W // 2, h // 2)))
        self.image = surf

    def _land_on_rect_top(self, floor_top: int):
        if self.rect.bottom > floor_top:
            self.rect.bottom = floor_top
            self.vel_y = 0.0

    def update_physics(self, world, same_group: pygame.sprite.Group, opp_group: pygame.sprite.Group):
        """重力、地板、障礙物頂、同類塊堆疊"""
        # 只在「生成當下」若已與地圖重疊才清除；正常生成則可落在地圖上不消失
        if self._just_spawned:
            self._just_spawned = False
            for _img, orect in world.obstacle_list:
                if self.rect.colliderect(orect):
                    self.kill()
                    return

        self.vel_y += CALC_BLOCK_GRAVITY
        self.rect.y += int(self.vel_y)

        if self.rect.bottom >= SCREEN_HEIGHT:
            self._land_on_rect_top(SCREEN_HEIGHT)

        for _img, orect in world.obstacle_list:
            if not self.rect.colliderect(orect):
                continue
            if self.rect.centery <= orect.centery:
                self._land_on_rect_top(orect.top)

        for other in list(same_group):
            if other is self:
                continue
            if not self.rect.colliderect(other.rect):
                continue
            if self.rect.centery <= other.rect.centery - 2:
                self._land_on_rect_top(other.rect.top)

        for other in list(opp_group):
            if other is self:
                continue
            if self.rect.colliderect(other.rect):
                self.kill()
                other.kill()
                return

        if self.rect.top > SCREEN_HEIGHT + 40:
            self.kill()


def resolve_calculus_block_interactions(
    block: CalculusBlock,
    player,
    enemy_group: pygame.sprite.Group,
    enemy_bullet_group: pygame.sprite.Group,
    brush_manager,
    area_group: pygame.sprite.Group,
    world,
    projectile_group: pygame.sprite.Group = None,
):
    """碰玩家／敵人／敵彈／畫筆後塊消失（邊界仍觸發）"""
    if not block.alive():
        return

    if block.kind == "integral" and projectile_group is not None:
        for proj in list(projectile_group):
            if isinstance(proj, MathProjectile) and proj.alive() and block.rect.colliderect(proj.rect):
                proj.apply_integral_enlarge()
                block.kill()
                return

    if block.rect.colliderect(player.rect):
        if block.kind == "derivative":
            player.apply_degree_delta(-1)
        else:
            player.apply_degree_delta(1)
        block.kill()
        return

    for enemy in list(enemy_group):
        if enemy.is_alive and block.rect.colliderect(enemy.rect):
            if block.kind == "derivative":
                enemy.calc_frozen = True
            else:
                enemy.calc_frozen = False
            block.kill()
            return

    if block.kind == "derivative":
        for bullet in list(enemy_bullet_group):
            if bullet.alive() and block.rect.colliderect(bullet.collision_rect()):
                bullet.kill()
                block.kill()
                return

    for stroke in list(brush_manager.strokes):
        if stroke.stroke_hits_rect(block.rect):
            if block.kind == "integral":
                if stroke.length < max(8.0, float(player.rect.width)):
                    center = stroke.points[-1] if stroke.points else block.rect.center
                    bodies = build_area_bodies_from_circle(
                        center,
                        radius=max(4.0, player.rect.width * 0.5),
                        world=world,
                        source_points=stroke.points,
                        source_color_index=stroke.color_index,
                        damage_ref_radius=max(1.0, player.rect.width * 2.0),
                    )
                else:
                    bodies = []
                    if stroke.is_closed_loop():
                        poly = stroke.integral_area_polygon(
                            block.axis,
                            player.rect.centerx,
                            INTEGRAL_XY_EXTEND_MAX_PX,
                        )
                        if poly and len(poly) >= 3:
                            bodies = build_area_bodies_from_polygon(
                                poly,
                                world,
                                source_points=stroke.points,
                                source_color_index=stroke.color_index,
                                damage_ref_radius=max(1.0, player.rect.width * 2.0),
                            )
                    else:
                        dx, dy = stroke.integral_shift_vector(
                            block.axis,
                            player.rect.centerx,
                            INTEGRAL_XY_EXTEND_MAX_PX,
                        )
                        bodies = build_area_bodies_from_shifted_stroke(
                            stroke.points,
                            dx,
                            dy,
                            world,
                            source_points=stroke.points,
                            source_color_index=stroke.color_index,
                            damage_ref_radius=max(1.0, player.rect.width * 2.0),
                        )
                for body in bodies:
                    area_group.add(body)
            brush_manager.remove_stroke(stroke)
            block.kill()
            return

    for area in list(area_group):
        if not area.intersects_rect(block.rect):
            continue
        if not area.is_stationary():
            continue
        if block.kind == "derivative":
            if area.source_points:
                brush_manager.add_stroke_from_points(area.source_points, area.source_color_index)
            area.kill()
            block.kill()
            return
        if block.kind == "integral":
            area.apply_push_from_direction(0.0, 1.0)
            return
