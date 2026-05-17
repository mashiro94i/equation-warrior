"""滑鼠點擊與 ∫xy / Sigmoid 等互動"""
from __future__ import annotations

import pygame

from .area_entity import (
    build_area_bodies_from_circle,
    build_area_bodies_from_polygon,
    build_area_bodies_from_shifted_stroke,
)
from .constants import (
    INTEGRAL_XY_EXTEND_MAX_PX, SIGMOID_ALPHA, SIGMOID_HEAL_MAX,
)
from .enums import IntegralAxis
from . import game_audio
from .gameplay import sigmoid_heal_from_damage


def try_sigmoid_on_enemy_bullet(mx: int, my: int, enemy_bullet_group) -> bool:
    probe = pygame.Rect(0, 0, 20, 20)
    probe.center = (int(mx), int(my))
    for bullet in list(enemy_bullet_group):
        if bullet.collision_rect().colliderect(probe):
            h = sigmoid_heal_from_damage(bullet.DAMAGE, SIGMOID_HEAL_MAX, SIGMOID_ALPHA)
            bullet.apply_sigmoid_heal(h)
            return True
    return False


def try_integral_xy_on_enemy_bullet(mx: int, my: int, axis: IntegralAxis, enemy_bullet_group) -> bool:
    step = max(12, INTEGRAL_XY_EXTEND_MAX_PX // 4)
    for bullet in list(enemy_bullet_group):
        if bullet.collision_rect().collidepoint(mx, my):
            bullet.apply_integral_extend(axis, step)
            game_audio.play_calculus_effect(at_rect=bullet.rect)
            return True
    return False


def try_integral_xy_on_brush(
    mx: int,
    my: int,
    axis: IntegralAxis,
    player,
    brush_manager,
    area_group: pygame.sprite.Group,
    world,
) -> bool:
    stroke = brush_manager.stroke_under_point(mx, my)
    if stroke is None:
        return False
    extend = INTEGRAL_XY_EXTEND_MAX_PX
    # 線太短時改成球：半徑=角色一半
    if stroke.length < max(8.0, float(player.rect.width)):
        center = stroke.points[-1] if stroke.points else (mx, my)
        bodies = build_area_bodies_from_circle(
            center,
            radius=max(4.0, player.rect.width * 0.5),
            world=world,
            source_points=stroke.points,
            source_color_index=stroke.color_index,
            damage_ref_radius=max(1.0, player.rect.width * 2.0),
        )
        for body in bodies:
            area_group.add(body)
        brush_manager.remove_stroke(stroke)
        if bodies:
            game_audio.play_calculus_effect(at_rect=bodies[0].rect)
        return len(bodies) > 0
    if stroke.is_closed_loop():
        poly = stroke.integral_area_polygon(axis.value, float(mx), extend)
        if not poly or len(poly) < 3:
            return False
        bodies = build_area_bodies_from_polygon(
            poly,
            world,
            source_points=stroke.points,
            source_color_index=stroke.color_index,
            damage_ref_radius=max(1.0, player.rect.width * 2.0),
        )
    else:
        dx, dy = stroke.integral_shift_vector(axis.value, float(mx), extend)
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
    if bodies:
        game_audio.play_calculus_effect(at_rect=bodies[0].rect)
    return len(bodies) > 0
