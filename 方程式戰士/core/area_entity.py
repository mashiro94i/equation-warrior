"""畫筆積分後的懸空面積體：擋敵彈、可被函數子彈推動"""
import pygame
import math

from . import game_audio
from .constants import (
    AREA_BODY_ALPHA_LAYERS, AREA_BODY_PUSH_SPEED,
    AREA_DAMAGE_ANCHOR_DAMAGE, AREA_DAMAGE_ANCHOR_RATIO, AREA_DAMAGE_MAX, AREA_DAMAGE_MIN,
    AREA_DAMAGE_TARGET_DAMAGE, AREA_DAMAGE_TARGET_RATIO,
    AREA_THROW_AIR_FRICTION, AREA_THROW_MAX_SPEED, AREA_THROW_MIN_SPEED,
    GREEN,
    MAP_AREA_FILL_RGBA, MAP_AREA_OUTLINE_RGB,
    SCREEN_HEIGHT, SCREEN_WIDTH,
)


class AreaBody(pygame.sprite.Sprite):
    """不傷自機；擋 3 發敵彈後碎裂；滑行中對敵造成與 MathProjectile 相同傷害"""

    def __init__(
        self,
        rect: pygame.Rect = None,
        points=None,
        source_points=None,
        source_color_index=0,
        damage_ref_radius: float = 80.0,
        *,
        use_map_integral_visual: bool = False,
    ):
        super().__init__()
        self.shape_points = None
        self.source_points = [(float(x), float(y)) for x, y in source_points] if source_points else None
        self.source_color_index = int(source_color_index)
        self.damage_ref_radius = max(1.0, float(damage_ref_radius))
        self.use_map_integral_visual = bool(use_map_integral_visual)
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            self.base_rect = pygame.Rect(
                int(min(xs)),
                int(min(ys)),
                int(max(xs) - min(xs)),
                int(max(ys) - min(ys)),
            )
            self.shape_points = [(float(x), float(y)) for x, y in points]
        else:
            self.base_rect = rect.copy()
        self.hits_taken = 0
        self.vel_x = 0.0
        self.vel_y = 0.0
        self._airborne_since_ms: int | None = None
        self._long_fall_sfx_played = False
        self.motion_path = []
        self.damage = AREA_DAMAGE_MIN
        self._rebuild_image()

    def _rebuild_image(self):
        w = max(4, self.base_rect.width)
        h = max(4, self.base_rect.height)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        alpha = AREA_BODY_ALPHA_LAYERS[min(self.hits_taken, len(AREA_BODY_ALPHA_LAYERS) - 1)]
        if self.shape_points and len(self.shape_points) >= 3:
            local_pts = [
                (int(x - self.base_rect.x), int(y - self.base_rect.y))
                for x, y in self.shape_points
            ]
            if self.use_map_integral_visual:
                fill_col = (MAP_AREA_FILL_RGBA[0], MAP_AREA_FILL_RGBA[1], MAP_AREA_FILL_RGBA[2], alpha)
                pygame.draw.polygon(surf, fill_col, local_pts)
                pygame.draw.polygon(surf, MAP_AREA_OUTLINE_RGB, local_pts, 2)
            else:
                pygame.draw.polygon(surf, (120, 200, 160, alpha), local_pts)
                pygame.draw.polygon(surf, GREEN, local_pts, 2)
        else:
            if self.use_map_integral_visual:
                fill_col = (MAP_AREA_FILL_RGBA[0], MAP_AREA_FILL_RGBA[1], MAP_AREA_FILL_RGBA[2], alpha)
                surf.fill(fill_col)
                pygame.draw.rect(surf, MAP_AREA_OUTLINE_RGB, surf.get_rect(), 2)
            else:
                surf.fill((120, 200, 160, alpha))
                pygame.draw.rect(surf, GREEN, surf.get_rect(), 2)
        self.image = surf
        self.rect = surf.get_rect(topleft=self.base_rect.topleft)
        self.mask = pygame.mask.from_surface(self.image)
        mask_area = pygame.mask.from_surface(surf).count()
        eq_radius = math.sqrt(max(1.0, float(mask_area)) / math.pi)
        ratio = eq_radius / self.damage_ref_radius
        denom = max(1e-6, AREA_DAMAGE_TARGET_RATIO - AREA_DAMAGE_ANCHOR_RATIO)
        k = math.log(max(1e-6, AREA_DAMAGE_TARGET_DAMAGE / AREA_DAMAGE_ANCHOR_DAMAGE)) / denom
        raw = AREA_DAMAGE_ANCHOR_DAMAGE * math.exp(k * (ratio - AREA_DAMAGE_ANCHOR_RATIO))
        self.damage = max(AREA_DAMAGE_MIN, min(AREA_DAMAGE_MAX, int(round(raw))))
        font = pygame.font.Font(None, 24)
        dmg = font.render(str(self.damage), True, (0, 0, 0))
        self.image.blit(dmg, dmg.get_rect(center=(w // 2, h // 2)))

    def register_bullet_hit(self) -> bool:
        """回傳 True 若已碎裂"""
        self.hits_taken += 1
        if self.hits_taken >= 3:
            game_audio.play_break(at_rect=self.rect)
            self.kill()
            return True
        self._rebuild_image()
        return False

    def intersects_rect(self, other_rect: pygame.Rect) -> bool:
        if not self.rect.colliderect(other_rect):
            return False
        other_mask = pygame.mask.Mask((max(1, other_rect.width), max(1, other_rect.height)), fill=True)
        offset = (other_rect.x - self.rect.x, other_rect.y - self.rect.y)
        return self.mask.overlap(other_mask, offset) is not None

    def surface_top_at_world_x(self, world_x: int):
        """此 x 垂直欄位中，形狀最上緣的世界座標 y；勿用 rect.top（外接盒會導致斜面漂浮）。"""
        if self.mask is None:
            return None
        lx = int(world_x) - int(self.rect.left)
        if lx < 0 or lx >= self.rect.width:
            return None
        h = self.rect.height
        for ly in range(h):
            if self.mask.get_at((lx, ly)):
                return int(self.rect.top + ly)
        return None

    def surface_bottom_at_world_x(self, world_x: int):
        """此 x 欄位最底端不透明像素的世界 y（抬頭撞面積下緣時用，勿用 rect.bottom）。"""
        if self.mask is None:
            return None
        lx = int(world_x) - int(self.rect.left)
        if lx < 0 or lx >= self.rect.width:
            return None
        bottom_ly = None
        for ly in range(self.rect.height):
            if self.mask.get_at((lx, ly)):
                bottom_ly = ly
        if bottom_ly is None:
            return None
        return int(self.rect.top + bottom_ly)

    def overlaps_world_obstacles(self, world) -> bool:
        for _img, orect in world.obstacle_list:
            if self.intersects_rect(orect):
                return True
        return False

    def _apply_position_delta(self, dx: int, dy: int):
        self.base_rect.x += int(dx)
        self.base_rect.y += int(dy)
        if self.shape_points:
            self.shape_points = [(x + dx, y + dy) for x, y in self.shape_points]
        if self.source_points:
            self.source_points = [(x + dx, y + dy) for x, y in self.source_points]
        self.rect.topleft = self.base_rect.topleft

    def try_offset_resolve_obstacles(self, dx: int, dy: int, world) -> bool:
        """嘗試平移 (dx,dy)；若與地圖重疊則改試僅 x 或僅 y。有任一成功則 True。"""
        dx, dy = int(round(dx)), int(round(dy))
        for tdx, tdy in ((dx, dy), (dx, 0), (0, dy)):
            if tdx == 0 and tdy == 0:
                continue
            self._apply_position_delta(tdx, tdy)
            self._rebuild_image()
            if self.overlaps_world_obstacles(world):
                self._apply_position_delta(-tdx, -tdy)
                self._rebuild_image()
            else:
                return True
        return False

    def snapshot_pose(self):
        """拖曳還原用（base_rect + 點列拷貝）。"""
        br = self.base_rect.copy()
        pts = [(float(x), float(y)) for x, y in self.shape_points] if self.shape_points else None
        src = [(float(x), float(y)) for x, y in self.source_points] if self.source_points else None
        return (br, pts, src)

    def restore_pose(self, snap):
        br, pts, src = snap
        self.base_rect = br.copy()
        self.shape_points = [(x, y) for x, y in pts] if pts else None
        self.source_points = [(x, y) for x, y in src] if src else None
        self.rect.topleft = self.base_rect.topleft
        self._rebuild_image()

    def apply_push_from_direction(self, dx: float, dy: float):
        self.motion_path = []
        n = (dx * dx + dy * dy) ** 0.5
        if n < 1e-6:
            return
        self.vel_x = AREA_BODY_PUSH_SPEED * dx / n
        self.vel_y = AREA_BODY_PUSH_SPEED * dy / n
        if dy > 0.5:
            game_audio.play_fall(at_rect=self.rect)

    def apply_throw_velocity(self, vx: float, vy: float):
        """面積拖曳放開甩出：給初速，滑行中仍可撞敵（與 update 既有邏輯相同）。"""
        self.motion_path = []
        n = math.hypot(float(vx), float(vy))
        if n < 1e-6:
            self.vel_x = 0.0
            self.vel_y = 0.0
            return
        # 略低於門檻時改為「至少 MIN」沿同方向，避免玩家覺得放開卻完全甩不動
        if n < AREA_THROW_MIN_SPEED:
            k = AREA_THROW_MIN_SPEED / n
            vx, vy = float(vx) * k, float(vy) * k
            n = AREA_THROW_MIN_SPEED
        s = min(AREA_THROW_MAX_SPEED, n) / n
        self.vel_x = float(vx) * s
        self.vel_y = float(vy) * s
        game_audio.play_area_throw(at_rect=self.rect)

    def _update_long_fall_sfx(self) -> None:
        if self.vel_y <= 0.35:
            self._airborne_since_ms = None
            self._long_fall_sfx_played = False
            return
        now = pygame.time.get_ticks()
        if self._airborne_since_ms is None:
            self._airborne_since_ms = now
            return
        if self._long_fall_sfx_played:
            return
        if now - self._airborne_since_ms < 1000:
            return
        game_audio.play_fall(at_rect=self.rect)
        self._long_fall_sfx_played = True

    def apply_motion_path(self, points):
        self.motion_path = list(points or [])
        self.vel_x = 0.0
        self.vel_y = 0.0

    def is_stationary(self) -> bool:
        return not self.motion_path and abs(self.vel_x) < 1e-6 and abs(self.vel_y) < 1e-6

    def move_down(self, px: int):
        dy = int(px)
        self.base_rect.y += dy
        if self.shape_points:
            self.shape_points = [(x, y + dy) for x, y in self.shape_points]
        if self.source_points:
            self.source_points = [(x, y + dy) for x, y in self.source_points]
        self.rect.topleft = self.base_rect.topleft

    def update(self, world, enemy_group, player):
        if self.motion_path:
            nx, ny = self.motion_path.pop(0)
            cx, cy = self.rect.center
            dx = int(nx - cx)
            dy = int(ny - cy)
        else:
            dx = int(round(self.vel_x))
            dy = int(round(self.vel_y))
        self.base_rect.x += dx
        self.base_rect.y += dy
        if self.shape_points:
            self.shape_points = [(x + dx, y + dy) for x, y in self.shape_points]
        if self.source_points:
            self.source_points = [(x + dx, y + dy) for x, y in self.source_points]
        self.rect.topleft = self.base_rect.topleft

        # 靜止面積只負責擋彈；不做撞牆/撞敵消失判定
        if self.is_stationary():
            return

        if not self.motion_path:
            self.vel_x *= AREA_THROW_AIR_FRICTION
            self.vel_y *= AREA_THROW_AIR_FRICTION
            if abs(self.vel_x) < 0.04:
                self.vel_x = 0.0
            if abs(self.vel_y) < 0.04:
                self.vel_y = 0.0
            self._update_long_fall_sfx()

        # 同 frame：敵人優先
        for enemy in list(enemy_group):
            from .enemy_special import enemy_body_rect

            if enemy.is_alive and self.intersects_rect(enemy_body_rect(enemy)):
                enemy.take_damage(self.damage)
                game_audio.play_break(at_rect=self.rect)
                self.kill()
                return

        if hasattr(world, "remove_destructible_walls_hitting"):
            world.remove_destructible_walls_hitting(self)

        for _img, orect in world.obstacle_list:
            if self.rect.colliderect(orect):
                game_audio.play_break(at_rect=self.rect)
                self.kill()
                return

        if not pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT).colliderect(self.rect):
            game_audio.play_break(at_rect=self.rect)
            self.kill()


def build_area_bodies_from_polygon(
    points,
    world,
    source_points=None,
    source_color_index=0,
    damage_ref_radius: float = 80.0,
    *,
    use_map_integral_visual: bool = False,
):
    """先切除與地圖重疊區域，再轉成可碰撞面積體（可能回傳多個）。"""
    if not points or len(points) < 3:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x = int(min(xs))
    min_y = int(min(ys))
    max_x = int(max(xs))
    max_y = int(max(ys))
    w = max(1, max_x - min_x + 1)
    h = max(1, max_y - min_y + 1)

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    local_pts = [(int(x - min_x), int(y - min_y)) for x, y in points]
    if len(local_pts) >= 3:
        pygame.draw.polygon(surf, (255, 255, 255, 255), local_pts)

    global_rect = pygame.Rect(min_x, min_y, w, h)
    for _img, orect in world.obstacle_list:
        inter = global_rect.clip(orect)
        if inter.width <= 0 or inter.height <= 0:
            continue
        local_inter = pygame.Rect(inter.x - min_x, inter.y - min_y, inter.width, inter.height)
        pygame.draw.rect(surf, (0, 0, 0, 0), local_inter)

    return _build_area_bodies_from_surface(
        surf,
        min_x,
        min_y,
        source_points=source_points,
        source_color_index=source_color_index,
        damage_ref_radius=damage_ref_radius,
        use_map_integral_visual=use_map_integral_visual,
    )


def _build_area_bodies_from_surface(
    surf,
    min_x,
    min_y,
    source_points=None,
    source_color_index=0,
    damage_ref_radius: float = 80.0,
    *,
    use_map_integral_visual: bool = False,
):
    out = []
    mask = pygame.mask.from_surface(surf)
    for comp_rect in mask.get_bounding_rects():
        if comp_rect.width < 2 or comp_rect.height < 2:
            continue
        comp_surf = pygame.Surface((comp_rect.width, comp_rect.height), pygame.SRCALPHA)
        comp_surf.blit(
            surf,
            (0, 0),
            area=comp_rect,
        )
        comp_mask = pygame.mask.from_surface(comp_surf)
        outline = comp_mask.outline()
        if len(outline) >= 3:
            pts = [
                (ox + min_x + comp_rect.x, oy + min_y + comp_rect.y)
                for ox, oy in outline
            ]
            out.append(
                AreaBody(
                    points=pts,
                    source_points=source_points,
                    source_color_index=source_color_index,
                    damage_ref_radius=damage_ref_radius,
                    use_map_integral_visual=use_map_integral_visual,
                ),
            )
        else:
            r = pygame.Rect(
                min_x + comp_rect.x,
                min_y + comp_rect.y,
                comp_rect.width,
                comp_rect.height,
            )
            out.append(
                AreaBody(
                    rect=r,
                    source_points=source_points,
                    source_color_index=source_color_index,
                    damage_ref_radius=damage_ref_radius,
                    use_map_integral_visual=use_map_integral_visual,
                ),
            )
    return out


def build_area_bodies_from_circle(
    center,
    radius: float,
    world,
    source_points=None,
    source_color_index=0,
    damage_ref_radius: float = 80.0,
    *,
    use_map_integral_visual: bool = False,
):
    cx, cy = center
    r = max(2.0, float(radius))
    pts = []
    for i in range(24):
        a = (2.0 * math.pi * i) / 24.0
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    sp = source_points if source_points is not None else pts
    return build_area_bodies_from_polygon(
        pts,
        world,
        source_points=sp,
        source_color_index=source_color_index,
        damage_ref_radius=damage_ref_radius,
        use_map_integral_visual=use_map_integral_visual,
    )


def build_area_bodies_from_shifted_stroke(
    points,
    shift_dx: float,
    shift_dy: float,
    world,
    source_points=None,
    source_color_index=0,
    damage_ref_radius: float = 80.0,
    *,
    use_map_integral_visual: bool = False,
):
    if not points or len(points) < 2:
        return []
    shifted = [(x + shift_dx, y + shift_dy) for x, y in points]
    xs = [p[0] for p in points] + [p[0] for p in shifted]
    ys = [p[1] for p in points] + [p[1] for p in shifted]
    min_x = int(min(xs))
    min_y = int(min(ys))
    max_x = int(max(xs))
    max_y = int(max(ys))
    w = max(1, max_x - min_x + 1)
    h = max(1, max_y - min_y + 1)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    # 以每段平移四邊形逐段填充，確保是「整條線平移後的面積」
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        q1 = shifted[i]
        q2 = shifted[i + 1]
        quad = [
            (int(p1[0] - min_x), int(p1[1] - min_y)),
            (int(p2[0] - min_x), int(p2[1] - min_y)),
            (int(q2[0] - min_x), int(q2[1] - min_y)),
            (int(q1[0] - min_x), int(q1[1] - min_y)),
        ]
        pygame.draw.polygon(surf, (255, 255, 255, 255), quad)
    # 端點蓋帽，避免首尾有縫
    cap_r = 3
    pygame.draw.circle(surf, (255, 255, 255, 255), (int(points[0][0] - min_x), int(points[0][1] - min_y)), cap_r)
    pygame.draw.circle(surf, (255, 255, 255, 255), (int(points[-1][0] - min_x), int(points[-1][1] - min_y)), cap_r)
    pygame.draw.circle(surf, (255, 255, 255, 255), (int(shifted[0][0] - min_x), int(shifted[0][1] - min_y)), cap_r)
    pygame.draw.circle(surf, (255, 255, 255, 255), (int(shifted[-1][0] - min_x), int(shifted[-1][1] - min_y)), cap_r)

    global_rect = pygame.Rect(min_x, min_y, w, h)
    for _img, orect in world.obstacle_list:
        inter = global_rect.clip(orect)
        if inter.width <= 0 or inter.height <= 0:
            continue
        local_inter = pygame.Rect(inter.x - min_x, inter.y - min_y, inter.width, inter.height)
        pygame.draw.rect(surf, (0, 0, 0, 0), local_inter)

    return _build_area_bodies_from_surface(
        surf,
        min_x,
        min_y,
        source_points=source_points,
        source_color_index=source_color_index,
        damage_ref_radius=damage_ref_radius,
        use_map_integral_visual=use_map_integral_visual,
    )


def pick_stationary_area_at(area_group, mx: int, my: int):
    """游標下最上層的靜止面積體（拖曳用）。"""
    probe = pygame.Rect(0, 0, 14, 14)
    probe.center = (int(mx), int(my))
    for area in reversed(list(area_group)):
        if area.alive() and area.is_stationary() and area.intersects_rect(probe):
            return area
    return None
