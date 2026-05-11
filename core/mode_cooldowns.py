"""離開特定模式後的再進入冷卻（毫秒）"""
from typing import Optional

import pygame

from .constants import (
    COOLDOWN_MS_LEAVE_DERIV_BLOCK, COOLDOWN_MS_LEAVE_INT_BLOCK,
    COOLDOWN_MS_LEAVE_SIGMA, COOLDOWN_MS_LEAVE_SIGMOID,
)
from .enums import PlayerMode


class ModeCooldowns:
    def __init__(self):
        self._until_ms = {m: 0 for m in PlayerMode}

    def can_use(self, mode: PlayerMode, now_ms: Optional[int] = None) -> bool:
        if now_ms is None:
            now_ms = pygame.time.get_ticks()
        return now_ms >= self._until_ms.get(mode, 0)

    def on_leave(self, mode: PlayerMode, now_ms: Optional[int] = None):
        if now_ms is None:
            now_ms = pygame.time.get_ticks()
        if mode == PlayerMode.DERIVATIVE_BLOCK:
            self._until_ms[PlayerMode.DERIVATIVE_BLOCK] = now_ms + COOLDOWN_MS_LEAVE_DERIV_BLOCK
        elif mode == PlayerMode.INTEGRAL_BLOCK:
            self._until_ms[PlayerMode.INTEGRAL_BLOCK] = now_ms + COOLDOWN_MS_LEAVE_INT_BLOCK
        elif mode == PlayerMode.SIGMOID:
            self._until_ms[PlayerMode.SIGMOID] = now_ms + COOLDOWN_MS_LEAVE_SIGMOID
        elif mode == PlayerMode.SIGMA:
            self._until_ms[PlayerMode.SIGMA] = now_ms + COOLDOWN_MS_LEAVE_SIGMA

    def total_ms(self, mode: PlayerMode) -> int:
        if mode == PlayerMode.DERIVATIVE_BLOCK:
            return COOLDOWN_MS_LEAVE_DERIV_BLOCK
        if mode == PlayerMode.INTEGRAL_BLOCK:
            return COOLDOWN_MS_LEAVE_INT_BLOCK
        if mode == PlayerMode.SIGMOID:
            return COOLDOWN_MS_LEAVE_SIGMOID
        if mode == PlayerMode.SIGMA:
            return COOLDOWN_MS_LEAVE_SIGMA
        return 0

    def remaining_ms(self, mode: PlayerMode, now_ms: Optional[int] = None) -> int:
        if now_ms is None:
            now_ms = pygame.time.get_ticks()
        return max(0, int(self._until_ms.get(mode, 0) - now_ms))
