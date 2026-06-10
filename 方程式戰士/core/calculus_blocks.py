"""下落微分／積分／平方／根號符號塊"""
import math

import pygame

from .area_entity import (
    build_area_bodies_from_circle,
    build_area_bodies_from_polygon,
    build_area_bodies_from_shifted_stroke,
)
from .constants import (
    CALC_BLOCK_GRAVITY, CALC_BLOCK_H, CALC_BLOCK_INTEGRAL_H, CALC_BLOCK_W,
    INTEGRAL_XY_EXTEND_MAX_PX, SQUARE_SPLIT_ANGLE_DEG,
    SCREEN_HEIGHT, SCREEN_WIDTH, WHITE, YELLOW,
)

# 游標下方預覽：與 CalculusBlock 同版型，填色／描邊較淺、字為黃色
_PREVIEW_FILL = (58, 58, 72, 200)
_PREVIEW_BORDER = (200, 200, 215)
_PREVIEW_BELOW_CURSOR_PX = 22
_PREVIEW_SURF_CACHE: dict[tuple[str, str], pygame.Surface] = {}

from . import game_audio
from .enemy_archetypes import GID_CHASHER, GID_SHOOTER
from .enums import PowerType
from .projectile import MathProjectile
from .soldier import Player
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
    """kind: 'derivative' | 'integral' | 'square' | 'sqrt'"""

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
        if self.kind == "integral":
            h = CALC_BLOCK_INTEGRAL_H
        else:
            h = CALC_BLOCK_H
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
        elif self.kind == "square":
            font = get_font(20, bold=True)
            txt = font.render("x²", True, WHITE)
            surf.blit(txt, txt.get_rect(center=(CALC_BLOCK_W // 2, h // 2)))
        elif self.kind == "sqrt":
            font = get_font(20, bold=True)
            txt = font.render("√x", True, WHITE)
            surf.blit(txt, txt.get_rect(center=(CALC_BLOCK_W // 2, h // 2)))
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
        step_y = int(self.vel_y)
        prev_bottom = self.rect.bottom
        self.rect.y += step_y

        if self.rect.bottom >= SCREEN_HEIGHT:
            self._land_on_rect_top(SCREEN_HEIGHT)

        for _img, orect in world.obstacle_list:
            if not self.rect.colliderect(orect):
                continue
            foot_overlap = min(self.rect.right, orect.right) - max(self.rect.left, orect.left)
            if foot_overlap < max(6, self.rect.width // 3):
                continue
            if self.vel_y < 0:
                continue
            if self.rect.bottom <= orect.top:
                continue
            if self.rect.top >= orect.bottom:
                continue
            if prev_bottom <= orect.top + 4 or step_y > 0:
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
                game_audio.play_calculus_effect(at_rect=self.rect)
                return

        if self.rect.top > SCREEN_HEIGHT + 40:
            self.kill()


def _carried_preview_surface(kind: str, axis: str = "y") -> pygame.Surface:
    key = (kind, axis.lower())
    cached = _PREVIEW_SURF_CACHE.get(key)
    if cached is not None:
        return cached
    if kind == "integral":
        h = CALC_BLOCK_INTEGRAL_H
    else:
        h = CALC_BLOCK_H
    surf = pygame.Surface((CALC_BLOCK_W, h), pygame.SRCALPHA)
    surf.fill(_PREVIEW_FILL)
    pygame.draw.rect(surf, _PREVIEW_BORDER, surf.get_rect(), 2)
    if kind == "derivative":
        font = get_font(15, bold=True)
        num = font.render("d", True, YELLOW)
        den = font.render("dx", True, YELLOW)
        cx = CALC_BLOCK_W // 2
        surf.blit(num, num.get_rect(center=(cx, 9)))
        pygame.draw.line(surf, YELLOW, (cx - 10, 13), (cx + 10, 13), 2)
        surf.blit(den, den.get_rect(center=(cx, 20)))
    elif kind == "square":
        font = get_font(20, bold=True)
        txt = font.render("x²", True, YELLOW)
        surf.blit(txt, txt.get_rect(center=(CALC_BLOCK_W // 2, h // 2)))
    elif kind == "sqrt":
        font = get_font(20, bold=True)
        txt = font.render("√x", True, YELLOW)
        surf.blit(txt, txt.get_rect(center=(CALC_BLOCK_W // 2, h // 2)))
    else:
        font = get_font(22, bold=True)
        label = "∫x" if axis.lower() == "x" else "∫y"
        txt = font.render(label, True, YELLOW)
        surf.blit(txt, txt.get_rect(center=(CALC_BLOCK_W // 2, h // 2)))
    _PREVIEW_SURF_CACHE[key] = surf
    return surf


def draw_carried_block_preview(
    screen: pygame.Surface,
    game_x: int,
    game_y: int,
    kind: str,
    axis: str = "y",
) -> None:
    """游標下方：淺色方塊 + 黃色符號（手形游標另由 assets 繪製）。"""
    surf = _carried_preview_surface(kind, axis)
    cy = int(game_y) + _PREVIEW_BELOW_CURSOR_PX + surf.get_height() // 2
    screen.blit(surf, surf.get_rect(center=(int(game_x), cy)))


def count_player_placed_calculus(group: pygame.sprite.Group) -> int:
    """只計玩家放置的塊；地圖內建塊不佔上限。"""
    return sum(
        1 for s in group.sprites() if not getattr(s, "_map_spawned", False)
    )


def add_calculus_block_with_limit(
    group: pygame.sprite.Group,
    block: CalculusBlock,
    max_count: int,
    *,
    evict_oldest: bool,
) -> bool:
    """加入微積分塊；達上限時依設定移除最舊的玩家放置塊。回傳是否成功加入。"""
    if getattr(block, "_map_spawned", False):
        group.add(block)
        return True
    player_placed = [
        s for s in group.sprites() if not getattr(s, "_map_spawned", False)
    ]
    if len(player_placed) >= max_count:
        if not evict_oldest:
            return False
        if player_placed:
            player_placed[0].kill()
    group.add(block)
    return True


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
    if not block.alive() or block.kind in ("square", "sqrt"):
        return

    if projectile_group is not None:
        for proj in list(projectile_group):
            if not proj.alive() or not block.rect.colliderect(proj.rect):
                continue
            if block.kind == "integral" and isinstance(proj, MathProjectile):
                proj.apply_integral_enlarge()
                block.kill()
                game_audio.play_calculus_effect(at_rect=block.rect)
                return
            if block.kind == "derivative":
                proj.kill()
                block.kill()
                game_audio.play_calculus_effect(at_rect=block.rect)
                return

    if block.rect.colliderect(player.rect):
        if block.kind == "derivative":
            player.apply_degree_delta(-1)
        else:
            player.apply_degree_delta(1)
            if _integral_block_smashes_player(block, player):
                player.take_damage(player.health * 0.5)
        block.kill()
        game_audio.play_calculus_effect(at_rect=block.rect)
        return

    for enemy in list(enemy_group):
        from .enemy_special import enemy_collides_rect, on_calculus_block_hit, try_apply_giant_crush

        if enemy_collides_rect(enemy, block.rect):
            if on_calculus_block_hit(enemy, block.kind):
                try_apply_giant_crush(enemy, player, pygame.time.get_ticks())
                block.kill()
                game_audio.play_calculus_effect(at_rect=block.rect)
                return
            if block.kind == "derivative":
                enemy.calc_frozen = True
                if int(enemy.enemy_gid) in (GID_CHASHER, GID_SHOOTER):
                    Player.show_center_notice(player, "你微分了線性移動！")
            else:
                was_frozen = bool(getattr(enemy, "calc_frozen", False))
                enemy.calc_frozen = False
                if was_frozen and int(enemy.enemy_gid) in (GID_CHASHER, GID_SHOOTER):
                    Player.show_center_notice(player, "你積分了0移動")
            block.kill()
            game_audio.play_calculus_effect(at_rect=block.rect)
            return

    if block.kind == "derivative":
        for bullet in list(enemy_bullet_group):
            if bullet.alive() and block.rect.colliderect(bullet.collision_rect()):
                bullet.kill()
                block.kill()
                game_audio.play_calculus_effect(at_rect=block.rect)
                return
    else:
        for bullet in list(enemy_bullet_group):
            if bullet.alive() and block.rect.colliderect(bullet.collision_rect()):
                bullet.apply_integral_enlarge()
                block.kill()
                game_audio.play_calculus_effect(at_rect=block.rect)
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
            game_audio.play_calculus_effect(at_rect=block.rect)
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
            game_audio.play_calculus_effect(at_rect=block.rect)
            return
        if block.kind == "integral":
            area.apply_push_from_direction(0.0, 1.0)
            game_audio.play_calculus_effect(at_rect=block.rect)
            return


def spawn_square_split_projectiles(projectile_group, origin, base_angle_rad: float, player) -> None:
    """平方塊被彈命中：沿原彈道左右各 15° 各射一枚直線彈。"""
    healing = bool(getattr(player, "heal_sigmoid_active", False))
    for delta_deg in (-SQUARE_SPLIT_ANGLE_DEG, SQUARE_SPLIT_ANGLE_DEG):
        ang = base_angle_rad + math.radians(delta_deg)
        dx, dy = math.cos(ang), math.sin(ang)
        norm = math.hypot(dx, dy) or 1.0
        direction = (dx / norm, dy / norm)
        proj = MathProjectile(
            origin=origin,
            power=PowerType.LINEAR,
            params={},
            facing=1 if dx >= 0 else -1,
            direction=direction,
            healing_shot=healing,
        )
        projectile_group.add(proj)


def resolve_algebra_block_interactions(
    block: CalculusBlock,
    player,
    projectile_group: pygame.sprite.Group,
    enemy_group: pygame.sprite.Group | None = None,
):
    """平方／根號塊：僅處理與我方子彈的互動。"""
    if block.kind not in ("square", "sqrt") or not block.alive():
        return
    if enemy_group is not None:
        for enemy in list(enemy_group):
            from .enemy_special import enemy_collides_rect, on_calculus_block_hit, try_apply_giant_crush

            if enemy_collides_rect(enemy, block.rect):
                kind = "square" if block.kind == "square" else "sqrt"
                if on_calculus_block_hit(enemy, kind):
                    try_apply_giant_crush(enemy, player, pygame.time.get_ticks())
                    block.kill()
                    game_audio.play_calculus_effect(at_rect=block.rect)
                    return
    if projectile_group is None:
        return
    for proj in list(projectile_group):
        if not proj.alive() or not isinstance(proj, MathProjectile):
            continue
        if not block.rect.colliderect(proj.rect):
            continue
        origin = proj.rect.center
        if block.kind == "square":
            spawn_square_split_projectiles(
                projectile_group, origin, proj.travel_angle_rad(), player,
            )
            proj.kill()
            block.kill()
            game_audio.play_calculus_effect(at_rect=block.rect)
            return
        proj.kill()
        block.kill()
        game_audio.play_calculus_effect(at_rect=block.rect)
        return
