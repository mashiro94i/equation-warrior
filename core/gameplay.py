"""純規則函式：血量精度、次方、放置區等（易單元測試，無 pygame）"""
import math
from typing import Optional, Tuple

from .enums import PowerType


def round_hp(value: float, decimals: int = 2) -> float:
    """HP 顯示與累加用：四捨五入到小數第 decimals 位"""
    return round(float(value) + 0.0, decimals)


def clamp_degree(degree: int) -> int:
    return max(0, min(3, int(degree)))


def degree_to_fire_power(degree: int) -> Optional[PowerType]:
    """發射用：0=彩蛋無彈、1=線性、2=二次、3=尚未實作→None"""
    d = clamp_degree(degree)
    if d == 0 or d == 3:
        return None
    if d == 1:
        return PowerType.LINEAR
    return PowerType.QUADRATIC


def placement_zone_left_third(screen_width: int, screen_height: int) -> Tuple[int, int, int, int]:
    """可放置區：左 2/3 寬、全螢幕高。回傳 (x, y, w, h)"""
    w = max(1, (screen_width * 2) // 3)
    return (0, 0, w, screen_height)


def point_in_placement_zone(px: float, py: float, screen_width: int, screen_height: int) -> bool:
    x, y, w, h = placement_zone_left_third(screen_width, screen_height)
    return x <= px < x + w and y <= py < y + h


def logistic_sigma(t: float) -> float:
    """標準 logistic σ(t)=1/(1+e^{-t})，值域 (0,1)"""
    if t >= 30:
        return 1.0
    if t <= -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-t))


def sigmoid_heal_from_damage(
    damage: float,
    heal_max: float,
    alpha: float,
) -> float:
    """H = heal_max * σ(α * D)（正值，之後以治療邏輯扣減傷害）"""
    return heal_max * logistic_sigma(alpha * float(damage))


def math_floor_positive(x: float) -> int:
    import math as _m
    return int(_m.floor(x))


def build_sigma_shot_schedule(
    n_upper: int,
    t0_ms: int,
    interval_ms: int,
    zero_burst: int,
):
    """回傳 [(time_ms, value), ...]；僅 n_upper=0 時展開 zero_burst 發 0。"""
    n_upper = int(max(0, math.floor(n_upper)))
    out = []
    t = int(t0_ms)
    if n_upper == 0:
        for _ in range(int(zero_burst)):
            out.append((t, 0))
            t += int(interval_ms)
        return out
    for v in range(0, n_upper + 1):
        out.append((t, v))
        t += int(interval_ms)
    return out
