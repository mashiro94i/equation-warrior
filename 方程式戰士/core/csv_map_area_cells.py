"""CSV 中 65796：八連通合併 → n×n 實心正方形用圓；其餘平滑上包絡，有支撐才 ∫y 向下填。"""
from __future__ import annotations

from collections import deque

from .area_entity import (
    build_area_bodies_from_circle,
    build_area_bodies_from_polygon,
    build_area_bodies_from_shifted_stroke,
)


def _neighbors8(x: int, y: int):
    """九宮格（含對角）鄰居。"""
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            yield x + dx, y + dy


def find_connected_components(
    grid: list[list[int]], gid: int, rows: int, cols: int
) -> list[set[tuple[int, int]]]:
    seen: set[tuple[int, int]] = set()
    out: list[set[tuple[int, int]]] = []
    for y in range(rows):
        row = grid[y]
        for x in range(cols):
            if x >= len(row) or row[x] != gid:
                continue
            if (x, y) in seen:
                continue
            comp: set[tuple[int, int]] = set()
            q = deque([(x, y)])
            seen.add((x, y))
            while q:
                cx, cy = q.popleft()
                comp.add((cx, cy))
                for nx, ny in _neighbors8(cx, cy):
                    if nx < 0 or ny < 0 or ny >= rows or nx >= len(grid[ny]):
                        continue
                    if grid[ny][nx] != gid:
                        continue
                    if (nx, ny) in seen:
                        continue
                    seen.add((nx, ny))
                    q.append((nx, ny))
            if comp:
                out.append(comp)
    return out


def _is_solid_bbox_fill(cells: set[tuple[int, int]]) -> bool:
    if not cells:
        return False
    min_x = min(c[0] for c in cells)
    max_x = max(c[0] for c in cells)
    min_y = min(c[1] for c in cells)
    max_y = max(c[1] for c in cells)
    w = max_x - min_x + 1
    h = max_y - min_y + 1
    return len(cells) == w * h


def square_disk_side_n(cells: set[tuple[int, int]]) -> int | None:
    """若為 n×n 實心正方形（1、4、9…格）回傳邊長 n，否則 None。"""
    if not cells or not _is_solid_bbox_fill(cells):
        return None
    min_x = min(c[0] for c in cells)
    max_x = max(c[0] for c in cells)
    min_y = min(c[1] for c in cells)
    max_y = max(c[1] for c in cells)
    w = max_x - min_x + 1
    h = max_y - min_y + 1
    if w != h:
        return None
    return w


def build_square_disk_circle_area(
    cells: set[tuple[int, int]], tile_size: int, world
) -> list:
    n = square_disk_side_n(cells)
    if not n:
        return []
    cx = tile_size * sum(x + 0.5 for x, _ in cells) / len(cells)
    cy = tile_size * sum(y + 0.5 for _, y in cells) / len(cells)
    r = n * tile_size * 0.5
    return build_area_bodies_from_circle(
        (cx, cy),
        r,
        world,
        source_points=None,
        source_color_index=0,
        damage_ref_radius=max(1.0, float(tile_size) * 2.0),
        use_map_integral_visual=True,
    )


def _catmull_rom(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * t
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
    )


def _smooth_chain(points: list[tuple[float, float]], samples: int = 6) -> list[tuple[float, float]]:
    if len(points) < 2:
        return list(points)
    if len(points) == 2:
        a, b = points
        out = []
        for i in range(samples + 1):
            t = i / samples
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        return out
    out: list[tuple[float, float]] = []
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[0]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else p2
        for s in range(samples + 1):
            t = s / samples
            out.append(
                (
                    _catmull_rom(p0[0], p1[0], p2[0], p3[0], t),
                    _catmull_rom(p0[1], p1[1], p2[1], p3[1], t),
                )
            )
    return out


def _laplacian_smooth_open(
    points: list[tuple[float, float]], passes: int = 5, lam: float = 0.42
) -> list[tuple[float, float]]:
    """開放折線：拉普拉斯平滑，轉角變圓弧／橢圓狀。"""
    cur = list(points)
    if len(cur) < 3:
        return cur
    for _ in range(passes):
        nxt = [cur[0]]
        for i in range(1, len(cur) - 1):
            px = (1.0 - lam) * cur[i][0] + lam * 0.5 * (cur[i - 1][0] + cur[i + 1][0])
            py = (1.0 - lam) * cur[i][1] + lam * 0.5 * (cur[i - 1][1] + cur[i + 1][1])
            nxt.append((px, py))
        nxt.append(cur[-1])
        cur = nxt
    return cur


def _top_profile_centers(
    cells: set[tuple[int, int]], tile_size: int
) -> list[tuple[float, float]]:
    by_x: dict[int, list[int]] = {}
    for x, y in cells:
        by_x.setdefault(x, []).append(y)
    xs = sorted(by_x.keys())
    pts: list[tuple[float, float]] = []
    for x in xs:
        ymin = min(by_x[x])
        pts.append((x * tile_size + tile_size * 0.5, ymin * tile_size + tile_size * 0.5))
    return pts


def _columns_vertically_dense(cells: set[tuple[int, int]]) -> bool:
    """每欄從最低到最高格必須連續無空洞（編輯器「填滿」柱狀）。"""
    by_x: dict[int, list[int]] = {}
    for x, y in cells:
        by_x.setdefault(x, []).append(y)
    for ys in by_x.values():
        lo, hi = min(ys), max(ys)
        if hi - lo + 1 != len(ys):
            return False
    return True


def _bottom_cells(cells: set[tuple[int, int]]) -> list[tuple[int, int]]:
    by_x: dict[int, int] = {}
    for x, y in cells:
        if x not in by_x or y > by_x[x]:
            by_x[x] = y
    return list(by_x.items())


def _ground_top_below_cell(
    x: int,
    y: int,
    tile_size: int,
    world,
    *,
    max_gap_tiles: float = 2.0,
) -> float | None:
    """該格正下方最近障礙物頂緣（世界 y）；無則 None。"""
    cell_left = x * tile_size
    cell_right = (x + 1) * tile_size
    probe_bottom = (y + 1) * tile_size
    max_gap = tile_size * max_gap_tiles
    best: float | None = None
    for _img, rect in world.obstacle_list:
        if rect.right <= cell_left or rect.left >= cell_right:
            continue
        if rect.top < probe_bottom - tile_size * 0.35:
            continue
        if rect.top > probe_bottom + max_gap:
            continue
        if best is None or rect.top < best:
            best = float(rect.top)
    return best


def component_should_integral_to_ground(
    cells: set[tuple[int, int]], tile_size: int, world
) -> bool:
    """柱狀填滿且每欄底格下方有地面／牆頂時才向下積分。"""
    if not cells or not _columns_vertically_dense(cells):
        return False
    for x, y in _bottom_cells(cells):
        if _ground_top_below_cell(x, y, tile_size, world) is None:
            return False
    return True


def _integral_shift_dy_to_ground(
    curve: list[tuple[float, float]],
    cells: set[tuple[int, int]],
    tile_size: int,
    world,
) -> float:
    """上包絡到元件下方地面的垂直距離（至少半格厚）。"""
    curve_low = max(p[1] for p in curve)
    ground_tops: list[float] = []
    for x, y in _bottom_cells(cells):
        g = _ground_top_below_cell(x, y, tile_size, world)
        if g is not None:
            ground_tops.append(g)
    if not ground_tops:
        return float(tile_size)
    ground_top = min(ground_tops)
    dy = ground_top - curve_low
    return max(float(tile_size) * 0.5, dy)


def build_floating_strip_from_upper_curve(
    cells: set[tuple[int, int]], tile_size: int, world
) -> list:
    """未落地：薄帶浮在上包絡原位，不向下積分。"""
    curve = _integral_upper_curve_from_cells(cells, tile_size)
    if len(curve) < 2:
        return []
    thick = max(float(tile_size) * 0.85, 6.0)
    bottom = [(x, y + thick) for x, y in reversed(curve)]
    poly = list(curve) + bottom
    return build_area_bodies_from_polygon(
        poly,
        world,
        source_points=list(curve),
        source_color_index=0,
        damage_ref_radius=max(1.0, float(tile_size) * 2.0),
        use_map_integral_visual=True,
    )


def _integral_upper_curve_from_cells(
    cells: set[tuple[int, int]], tile_size: int
) -> list[tuple[float, float]]:
    """離散格頂部錨點 → 加密 Catmull-Rom → 拉普拉斯圓角 → 再平滑（類橢圓邊）。"""
    raw = _top_profile_centers(cells, tile_size)
    if not raw:
        return []
    if len(raw) == 1:
        x, y = raw[0]
        span = max(tile_size * 0.4, 6.0)
        raw = [(x - span * 0.5, y), (x + span * 0.5, y)]
    dense = _smooth_chain(raw, samples=14)
    rounded = _laplacian_smooth_open(dense, passes=6, lam=0.44)
    return _smooth_chain(rounded, samples=8)


def build_integral_strip_from_smoothed_upper_curve(
    cells: set[tuple[int, int]],
    tile_size: int,
    world,
    screen_h: int | None = None,
) -> list:
    del screen_h  # 保留參數以相容舊呼叫，不再用全螢幕向下填
    if not component_should_integral_to_ground(cells, tile_size, world):
        return build_floating_strip_from_upper_curve(cells, tile_size, world)
    curve = _integral_upper_curve_from_cells(cells, tile_size)
    if len(curve) < 2:
        return []
    shift_dy = _integral_shift_dy_to_ground(curve, cells, tile_size, world)
    return build_area_bodies_from_shifted_stroke(
        curve,
        0.0,
        float(shift_dy),
        world,
        source_points=list(curve),
        source_color_index=0,
        damage_ref_radius=max(1.0, float(tile_size) * 2.0),
        use_map_integral_visual=True,
    )


def spawn_area_bodies_for_gid65796(
    grid: list[list[int]],
    tile_size: int,
    screen_h: int,
    world,
    area_group: pygame.sprite.Group,
    gid: int = 65796,
) -> None:
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)
    for comp in find_connected_components(grid, gid, rows, cols):
        if not comp:
            continue
        if square_disk_side_n(comp) is not None:
            bodies = build_square_disk_circle_area(comp, tile_size, world)
        else:
            bodies = build_integral_strip_from_smoothed_upper_curve(comp, tile_size, world, screen_h)
        for b in bodies:
            area_group.add(b)
