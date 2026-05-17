"""各關卡可用模式與按鍵對應"""
from dataclasses import dataclass
from typing import Optional

import pygame

from .enums import PlayerMode


@dataclass(frozen=True)
class LevelModeConfig:
    """單關模式配置：數字鍵切換、B 畫筆／雙 B 面積、治療 S 切換。"""
    key_to_mode: dict[int, PlayerMode]
    allow_brush_b: bool = False
    allow_double_b_area: bool = False
    toggle_heal_sigmoid_key: Optional[int] = None
    cooldown_hud: tuple[tuple[PlayerMode, str], ...] = ()

    def switchable_modes(self) -> frozenset[PlayerMode]:
        modes = frozenset(self.key_to_mode.values())
        if self.allow_brush_b:
            modes = modes | frozenset({PlayerMode.BRUSH, PlayerMode.AREA_MOVE})
        return modes

    def mode_allowed(self, mode: PlayerMode) -> bool:
        return mode in self.switchable_modes()

    def status_hints(self) -> tuple[str, ...]:
        lines = []
        for key, mode in sorted(self.key_to_mode.items()):
            if mode == PlayerMode.FUNCTION:
                lines.append("1：函數模式")
            elif mode == PlayerMode.INTEGRAL_BLOCK:
                lines.append("2：積分模式")
            elif mode == PlayerMode.DERIVATIVE_BLOCK:
                lines.append("3：微分模式")
            elif mode == PlayerMode.SQUARE_BLOCK:
                lines.append("2：平方模式")
            elif mode == PlayerMode.SQRT_BLOCK:
                lines.append("3：根號模式")
        if self.allow_brush_b:
            lines.append("B：畫筆｜雙按 B：面積拖曳")
        if self.toggle_heal_sigmoid_key is not None:
            lines.append("4：切換治療 S")
        return tuple(lines)


def derivative_requires_world_unlock(level: int) -> bool:
    """關卡 1 已內建微分；僅關卡 2 等需碰 131417 解鎖。"""
    return PlayerMode.DERIVATIVE_BLOCK not in get_level_mode_config(level).switchable_modes()


def derivative_switch_key(level: int) -> int | None:
    """微分模式切換鍵：關卡有對應鍵則用之，否則解鎖後預設 2。"""
    for key, mode in get_level_mode_config(level).key_to_mode.items():
        if mode == PlayerMode.DERIVATIVE_BLOCK:
            return int(key)
    return int(pygame.K_2)


def get_level_mode_config(level: int) -> LevelModeConfig:
    lv = max(1, min(int(level), 3))
    if lv == 1:
        return LevelModeConfig(
            key_to_mode={
                pygame.K_1: PlayerMode.FUNCTION,
                pygame.K_2: PlayerMode.INTEGRAL_BLOCK,
                pygame.K_3: PlayerMode.DERIVATIVE_BLOCK,
            },
            cooldown_hud=(
                (PlayerMode.FUNCTION, "1:f(x)"),
                (PlayerMode.INTEGRAL_BLOCK, "2:∫"),
                (PlayerMode.DERIVATIVE_BLOCK, "3:d/dx"),
            ),
        )
    if lv == 2:
        return LevelModeConfig(
            key_to_mode={pygame.K_1: PlayerMode.FUNCTION},
            allow_brush_b=True,
            allow_double_b_area=True,
            cooldown_hud=((PlayerMode.FUNCTION, "1:f(x)"),),
        )
    return LevelModeConfig(
        key_to_mode={
            pygame.K_1: PlayerMode.FUNCTION,
            pygame.K_2: PlayerMode.SQUARE_BLOCK,
            pygame.K_3: PlayerMode.SQRT_BLOCK,
        },
        toggle_heal_sigmoid_key=pygame.K_4,
        cooldown_hud=(
            (PlayerMode.FUNCTION, "1:f(x)"),
            (PlayerMode.SQUARE_BLOCK, "2:x²"),
            (PlayerMode.SQRT_BLOCK, "3:√x"),
        ),
    )
