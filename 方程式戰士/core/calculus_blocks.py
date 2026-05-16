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
from . import game_audio
from .projectile import MathProjectile
from .fonts import get_font


def _integral_block_smashes_player(block, player) -> bool:
    """積分塊自上方砸到角色（扣血條件）；側向輕碰不算。"""
    if block.kind != "integral":
        return False
    if not block.rect.colliderect(player.rect):
        return False
    # 須有下落速度，避免站著側貼、静止疊放也算「砸」
    if block.vel_y < 0.85:
        return False
    head_depth = max(14, int(player.rect.height * 0.38))
    crush_top = player.rect.top - 8
    crush_bottom = player.rect.top + head_depth
    # 塊底落在角色頭頂附近（砸中上半身頂端）
    if not (crush_top <= block.rect.bottom <= crush_bottom + 10):
        return False
    overlap_w = min(block.rect.right, player.rect.right) - max(block.rect.left, player.rect.left)
    return overlap_w > 6


class CalculusBlock(pygame.sprite.Sprite):
    """kind: 'derivative' | 'integral'"""

    def __init__(self, center_xy, kind: str, axis: str = "y", *, map_spawned: bool = False):
        super().__init__()
        self.kind = kind
        self.axis = axis.lower()
        self.vel_y = 0.0
        self._just_spawned = True
        self._map_spawned = bool(map_spawned)
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
            if not self._map_spawned:
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
                game_audio.play_calculus_effect()
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

    if projectile_group is not None:
        for proj in list(projectile_group):
            if not proj.alive() or not block.rect.colliderect(proj.rect):
                continue
            if block.kind == "integral" and isinstance(proj, MathProjectile):
                proj.apply_integral_enlarge()
                block.kill()
                game_audio.play_calculus_effect()
                return
            if block.kind == "derivative":
                proj.kill()
                block.kill()
                game_audio.play_calculus_effect()
                return

    if block.rect.colliderect(player.rect):
        if block.kind == "derivative":
            player.apply_degree_delta(-1)
        else:
            player.apply_degree_delta(1)
            if _integral_block_smashes_player(block, player):
                player.take_damage(player.health * 0.5)
        block.kill()
        game_audio.play_calculus_effect()
        return

    for enemy in list(enemy_group):
        if enemy.is_alive and block.rect.colliderect(enemy.rect):
            if block.kind == "derivative":
                enemy.calc_frozen = True
            else:
                enemy.calc_frozen = False
            block.kill()
            game_audio.play_calculus_effect()
            return

    if block.kind == "derivative":
        for bullet in list(enemy_bullet_group):
            if bullet.alive() and block.rect.colliderect(bullet.collision_rect()):
                bullet.kill()
                block.kill()
                game_audio.play_calculus_effect()
                return
    else:
        for bullet in list(enemy_bullet_group):
            if bullet.alive() and block.rect.colliderect(bullet.collision_rect()):
                bullet.apply_integral_enlarge()
                block.kill()
                game_audio.play_calculus_effect()
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
                            float(block.rect.centerx),
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
                            float(block.rect.centerx),
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
            game_audio.play_calculus_effect()
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
            game_audio.play_calculus_effect()
            return
        if block.kind == "integral":
            area.apply_push_from_direction(0.0, 1.0)
            game_audio.play_calculus_effect()
            return
