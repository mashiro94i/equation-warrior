"""畫筆：左側區域、多色筆觸、總長度上限"""
from __future__ import annotations

import math
import colorsys
from typing import List, Optional, Tuple

import pygame

from .constants import (
    BRUSH_MAX_STROKES, BRUSH_MAX_TOTAL_LENGTH_PX, BRUSH_MIN_SEGMENT,
    BLUE, RED, SCREEN_HEIGHT, SCREEN_WIDTH,
)
from .gameplay import placement_zone_around_player

def _make_palette(n: int):
    out = []
    for i in range(max(1, n)):
        h = (i / max(1, n)) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.75, 0.95)
        out.append((int(r * 255), int(g * 255), int(b * 255)))
    return tuple(out)


BRUSH_PALETTE = _make_palette(BRUSH_MAX_STROKES)


def _seg_len(x1, y1, x2, y2) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _segment_intersection(p1, p2, q1, q2):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = q1
    x4, y4 = q2
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-6:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / den
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        px = x1 + t * (x2 - x1)
        py = y1 + t * (y2 - y1)
        return (px, py)
    return None


def _segment_hit_rect(x1, y1, x2, y2, pad: int = 6) -> pygame.Rect:
    left = min(x1, x2) - pad
    top = min(y1, y2) - pad
    w = abs(x2 - x1) + pad * 2
    h = abs(y2 - y1) + pad * 2
    return pygame.Rect(int(left), int(top), int(max(w, 1)), int(max(h, 1)))


class BrushStroke:
    def __init__(self, color_index: int):
        self.color_index = int(color_index) % len(BRUSH_PALETTE)
        self.points: List[Tuple[float, float]] = []
        self.length = 0.0
        self.closed = False

    def add_point(self, x: float, y: float, budget_left: float) -> float:
        """回傳本次消耗的長度"""
        if self.closed:
            return 0.0
        if not self.points:
            self.points.append((float(x), float(y)))
            return 0.0
        lx, ly = self.points[-1]
        d = _seg_len(lx, ly, x, y)
        if d < BRUSH_MIN_SEGMENT:
            return 0.0
        use = min(d, budget_left)
        ratio = use / d
        nx = lx + (float(x) - lx) * ratio
        ny = ly + (float(y) - ly) * ratio
        self.points.append((nx, ny))
        self.length += use
        # 1) 首尾接近直接收口
        if len(self.points) >= 4:
            sx, sy = self.points[0]
            if _seg_len(nx, ny, sx, sy) <= 12:
                self.points[-1] = (sx, sy)
                self.closed = True
                self._recompute_length()
                return use
        # 2) 新線段與舊線段相交也算閉環，裁掉多餘段
        self._try_close_by_intersection()
        return use

    def _recompute_length(self):
        total = 0.0
        for i in range(len(self.points) - 1):
            x1, y1 = self.points[i]
            x2, y2 = self.points[i + 1]
            total += _seg_len(x1, y1, x2, y2)
        self.length = total

    def _try_close_by_intersection(self):
        if self.closed or len(self.points) < 4:
            return
        a1 = self.points[-2]
        a2 = self.points[-1]
        # 跳過最後相鄰邊，只找真正形成閉環的舊邊
        for i in range(len(self.points) - 3):
            b1 = self.points[i]
            b2 = self.points[i + 1]
            hit = _segment_intersection(a1, a2, b1, b2)
            if hit is None:
                continue
            # 保留封閉輪廓，移除輪廓外多餘線段
            loop_points = [hit]
            loop_points.extend(self.points[i + 1:-1])
            loop_points.append(hit)
            self.points = loop_points
            self.closed = True
            self._recompute_length()
            return

    def iter_hit_rects(self):
        for i in range(len(self.points) - 1):
            x1, y1 = self.points[i]
            x2, y2 = self.points[i + 1]
            yield _segment_hit_rect(x1, y1, x2, y2)

    def stroke_hits_rect(self, r: pygame.Rect) -> bool:
        for hr in self.iter_hit_rects():
            if hr.colliderect(r):
                return True
        p = self.points[0] if self.points else None
        if p:
            pr = pygame.Rect(0, 0, 8, 8)
            pr.center = (int(p[0]), int(p[1]))
            if pr.colliderect(r):
                return True
        return False

    def is_closed_loop(self, close_px: float = 16.0) -> bool:
        if self.closed:
            return True
        if len(self.points) < 4:
            return False
        x1, y1 = self.points[0]
        x2, y2 = self.points[-1]
        return _seg_len(x1, y1, x2, y2) <= close_px

    def integral_area_polygon(self, axis: str, player_centerx: float, extend: float):
        if len(self.points) < 2:
            return None
        if self.is_closed_loop():
            return list(self.points)
        if axis == "y":
            dx, dy = 0.0, float(extend)
        else:
            avg_x = sum(p[0] for p in self.points) / len(self.points)
            dx = -float(extend) if avg_x < player_centerx else float(extend)
            dy = 0.0
        shifted = [(x + dx, y + dy) for x, y in self.points]
        return list(self.points) + list(reversed(shifted))

    def integral_shift_vector(self, axis: str, player_centerx: float, extend: float):
        if axis == "y":
            return (0.0, float(extend))
        avg_x = sum(p[0] for p in self.points) / len(self.points)
        dx = -float(extend) if avg_x < player_centerx else float(extend)
        return (dx, 0.0)


class BrushManager:
    def __init__(self):
        self.strokes: List[BrushStroke] = []
        self.current: Optional[BrushStroke] = None
        self.total_length = 0.0
        self._closed_loops_pending: List[Tuple[List[Tuple[float, float]], int]] = []
        self.zone_center_x: float = SCREEN_WIDTH / 6.0

    def set_zone_center_x(self, player_cx: float) -> None:
        self.zone_center_x = float(player_cx)

    def _zone_rect(self) -> pygame.Rect:
        x, y, w, h = placement_zone_around_player(
            self.zone_center_x, SCREEN_WIDTH, SCREEN_HEIGHT,
        )
        return pygame.Rect(x, y, w, h)

    def point_in_zone(self, px: float, py: float) -> bool:
        return self._zone_rect().collidepoint(px, py)

    def start_stroke(self, mx: float, my: float) -> bool:
        if not self.point_in_zone(mx, my):
            return False
        if self.total_length >= BRUSH_MAX_TOTAL_LENGTH_PX:
            return False
        while len(self.strokes) >= BRUSH_MAX_STROKES:
            old = self.strokes.pop(0)
            if self.current is old:
                self.current = None
        color_idx = len(self.strokes) % len(BRUSH_PALETTE)
        stroke = BrushStroke(color_idx)
        self.strokes.append(stroke)
        self.current = stroke
        budget = BRUSH_MAX_TOTAL_LENGTH_PX - self.total_length
        stroke.add_point(mx, my, budget)
        return True

    def extend_stroke(self, mx: float, my: float):
        if self.current is None:
            return
        if not self.point_in_zone(mx, my):
            return
        budget = BRUSH_MAX_TOTAL_LENGTH_PX - self.total_length
        if budget <= 0:
            return
        stroke = self.current
        used = stroke.add_point(mx, my, budget)
        self.total_length += used
        if stroke.closed:
            pts = [(float(x), float(y)) for x, y in stroke.points]
            ci = stroke.color_index
            self._closed_loops_pending.append((pts, ci))
            self.remove_stroke(stroke)
        self._recompute_length()

    def drain_closed_loop_areas(self):
        """取走待轉成面積體的閉環（點列、顏色索引），並清空佇列。"""
        out = self._closed_loops_pending
        self._closed_loops_pending = []
        return out

    def end_stroke(self):
        self.current = None

    def remove_stroke(self, stroke: BrushStroke):
        if stroke in self.strokes:
            self.strokes.remove(stroke)
        if self.current is stroke:
            self.current = None
        self._recompute_length()

    def add_stroke_from_points(self, points, color_index: int = 0):
        if not points:
            return
        while len(self.strokes) >= BRUSH_MAX_STROKES:
            old = self.strokes.pop(0)
            if self.current is old:
                self.current = None
        stroke = BrushStroke(color_index)
        stroke.points = [(float(x), float(y)) for x, y in points]
        length = 0.0
        for i in range(len(stroke.points) - 1):
            x1, y1 = stroke.points[i]
            x2, y2 = stroke.points[i + 1]
            length += _seg_len(x1, y1, x2, y2)
        stroke.length = length
        self.strokes.append(stroke)
        self._recompute_length()

    def _recompute_length(self):
        self.total_length = sum(s.length for s in self.strokes)

    def clear_strokes_hit_by_block(self, block_rect: pygame.Rect):
        to_remove = [s for s in self.strokes if s.stroke_hits_rect(block_rect)]
        for s in to_remove:
            self.remove_stroke(s)

    def draw(self, surface: pygame.Surface):
        for stroke in self.strokes:
            color = BRUSH_PALETTE[stroke.color_index]
            pts = [(int(px), int(py)) for px, py in stroke.points]
            if len(pts) == 1:
                pygame.draw.circle(surface, color, pts[0], 4)
            elif len(pts) >= 2:
                pygame.draw.lines(surface, color, False, pts, 3)

    def stroke_under_point(self, mx: float, my: float) -> Optional[BrushStroke]:
        probe = pygame.Rect(0, 0, 12, 12)
        probe.center = (int(mx), int(my))
        for stroke in reversed(self.strokes):
            for hr in stroke.iter_hit_rects():
                if hr.colliderect(probe):
                    return stroke
            if stroke.points:
                pr = pygame.Rect(0, 0, 10, 10)
                pr.center = (int(stroke.points[-1][0]), int(stroke.points[-1][1]))
                if pr.colliderect(probe):
                    return stroke
        return None

    def bounding_rect_of_stroke(self, stroke: BrushStroke) -> Optional[pygame.Rect]:
        if not stroke.points:
            return None
        xs = [p[0] for p in stroke.points]
        ys = [p[1] for p in stroke.points]
        pad = 4
        r = pygame.Rect(
            int(min(xs) - pad),
            int(min(ys) - pad),
            int(max(xs) - min(xs) + pad * 2),
            int(max(ys) - min(ys) + pad * 2),
        )
        return r
