"""地圖裝飾格動畫：成對切換、65850 獨立累積、序列格。"""
from __future__ import annotations

import random
from typing import Any

# 兩格來回（地圖裝飾用；與敵人 GID 可重號但此處僅負責貼圖切換）
TILE_ANIM_PAIRS: tuple[tuple[int, int], ...] = (
    (65887, 65888),
    (65914, 65915),
    (65942, 65941),
    (65820, 65819),
    (65821, 65822),
    (65823, 65824),
)

TILE_ANIM_SEQUENCE: tuple[int, ...] = (131417, 131418, 131419, 131420)
DERIVATIVE_UNLOCK_GIDS = frozenset(TILE_ANIM_SEQUENCE)

TILE_ANIM_INTERVAL_MS = 350
GID_65850_CYCLE = (65850, 65851, 65877, 65878, 65985)
GID_65850_CHANGE_CHANCE = 0.30
GID_65850_THRESHOLD = 15.0

UNDERWATER_AMBIENT_GIDS = frozenset({65887, 65888, 65914, 65915, 65942, 65941})

_PAIR_LOOKUP: dict[int, tuple[int, int]] = {}
for _a, _b in TILE_ANIM_PAIRS:
    _PAIR_LOOKUP[_a] = (_a, _b)
    _PAIR_LOOKUP[_b] = (_a, _b)

PAIR_ANIM_GIDS = frozenset(_PAIR_LOOKUP.keys())
_SEQ_LOOKUP = frozenset(TILE_ANIM_SEQUENCE)


def init_tile_anim_state(source_gid: int, now_ms: int | None = None) -> dict[str, Any] | None:
    """每格獨立狀態（相位／累積速率皆隨機）。"""
    g = int(source_gid)
    if g == 65850:
        return {
            "kind": "65850",
            "accum": random.uniform(0.0, 7.0),
            "accum_rate": random.uniform(0.0007, 0.0014),
            "display_gid": 65850,
        }
    if g in PAIR_ANIM_GIDS:
        phase = random.randint(0, max(1, TILE_ANIM_INTERVAL_MS - 1))
        return {"kind": "pair", "pair_phase_ms": phase}
    if g in _SEQ_LOOKUP:
        phase = random.randint(0, max(1, TILE_ANIM_INTERVAL_MS - 1))
        return {"kind": "seq", "pair_phase_ms": phase}
    if g == 66016:
        return {
            "kind": "66016",
            "accum": random.uniform(0.0, 7.0),
            "accum_rate": random.uniform(0.0007, 0.0014),
            "display_gid": 66016,
            "resolved": False,
        }
    if g == 66012:
        return {
            "kind": "66012",
            "accum": random.uniform(0.0, 7.0),
            "accum_rate": random.uniform(0.0007, 0.0014),
            "display_gid": 66012,
            "resolved": False,
        }
    return None


def _tick_65850(state: dict[str, Any], dt_ms: int) -> None:
    state["accum"] = float(state["accum"]) + max(0, dt_ms) * float(state["accum_rate"])
    while state["accum"] >= GID_65850_THRESHOLD:
        state["accum"] -= GID_65850_THRESHOLD
        if random.random() < GID_65850_CHANGE_CHANCE:
            state["display_gid"] = random.choice(GID_65850_CYCLE)


def _tick_66016_66012(state: dict[str, Any], dt_ms: int) -> None:
    if state.get("resolved"):
        return
    state["accum"] = float(state["accum"]) + max(0, dt_ms) * float(state["accum_rate"])
    if state["accum"] < 15.0:
        return
    state["resolved"] = True
    if state["kind"] == "66016":
        state["display_gid"] = 66017 if random.random() < 0.5 else 66016
    else:
        state["display_gid"] = 66013 if random.random() < 0.5 else 66012


def tile_has_animation(gid: int) -> bool:
    g = int(gid)
    return g in PAIR_ANIM_GIDS or g in _SEQ_LOOKUP or g == 65850 or g in (66016, 66012)


def resolve_display_gid(
    source_gid: int,
    anim_state: dict[str, Any] | None,
    now_ms: int,
    dt_ms: int = 0,
) -> int:
    if anim_state is not None:
        kind = anim_state.get("kind")
        if kind == "65850":
            _tick_65850(anim_state, dt_ms)
            return int(anim_state["display_gid"])
        if kind in ("66016", "66012"):
            _tick_66016_66012(anim_state, dt_ms)
            return int(anim_state["display_gid"])

    gid = int(source_gid)
    phase = int(anim_state.get("pair_phase_ms", 0)) if anim_state else 0
    t_ms = now_ms + phase

    if gid in _PAIR_LOOKUP:
        a, b = _PAIR_LOOKUP[gid]
        return a if (t_ms // TILE_ANIM_INTERVAL_MS) % 2 == 0 else b
    if gid in _SEQ_LOOKUP:
        n = len(TILE_ANIM_SEQUENCE)
        cycle = max(1, 2 * (n - 1))
        step = (t_ms // TILE_ANIM_INTERVAL_MS) % cycle
        idx = step if step < n else cycle - step
        return TILE_ANIM_SEQUENCE[idx]
    if anim_state is not None and "display_gid" in anim_state:
        return int(anim_state["display_gid"])
    return gid


def animated_gid_at(gid: int, now_ms: int) -> int:
    return resolve_display_gid(gid, None, now_ms, 0)
