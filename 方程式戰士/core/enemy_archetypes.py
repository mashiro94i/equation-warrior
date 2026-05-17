"""特殊敵人 GID 數值與初始設定。"""
from __future__ import annotations

import math
from dataclasses import dataclass

GID_AREA_SPRAYER = 65822
GID_TINY_FRACTION = 65820
GID_NEGATIVE_ONE = 65823
GID_GIANT_256 = 131437
GID_EXP_X = 131449
GID_KEY_TANK = 65840
GID_SIN_WAVE = 65843
GID_SIN_WAVE_LEGACY = 131448  # 僅載入舊 CSV 時轉成 65843，勿列入 GID_ENEMIES
GID_SIN_WAVE_WALK_ALTS = frozenset({65844, 65845})
SIN_WAVE_GIDS = frozenset({GID_SIN_WAVE, *GID_SIN_WAVE_WALK_ALTS})
GID_CHASHER = 65834
GID_SHOOTER = 65838

ALL_SPECIAL_ENEMY_GIDS = frozenset({
    GID_AREA_SPRAYER,
    GID_TINY_FRACTION,
    GID_NEGATIVE_ONE,
    GID_GIANT_256,
    GID_EXP_X,
    GID_KEY_TANK,
    GID_SIN_WAVE,
    *GID_SIN_WAVE_WALK_ALTS,
    GID_CHASHER,
    GID_SHOOTER,
})


@dataclass(frozen=True)
class EnemyArchetype:
    max_hp: float
    head_label: str | None = None
    speed_mult: float = 1.0
    shoot_cd_mult: float = 1.0
    scale_mult: float = 1.0
    alpha: int = 255
    ghost_walls: bool = False
    ghost_area: bool = False
    chase_aggressive: bool = False
    ai: str = "default"
    calculus_immune: bool = False
    only_heal_bullet_hurt: bool = False
    invincible: bool = False
    melee_bump: bool = False


def normalize_enemy_spawn_gid(gid: int) -> int:
    """舊格 131448、動畫格 65844/65845 皆視為 sin 怪本體 65843。"""
    g = int(gid)
    if g == GID_SIN_WAVE_LEGACY or g in SIN_WAVE_GIDS:
        return GID_SIN_WAVE
    return g


def create_enemy(x: int, y: int, enemy_gid: int):
    from .enemy_special import configure_calc_tank_algebra_state
    from .soldier import Enemy

    gid = normalize_enemy_spawn_gid(enemy_gid)
    arch = archetype_for_gid(gid)
    hp = arch.max_hp if arch is not None else None
    enemy = Enemy(x, y, max_hp=hp, enemy_gid=gid)
    configure_calc_tank_algebra_state(enemy, force=True)
    return enemy


def archetype_for_gid(gid: int) -> EnemyArchetype | None:
    g = int(gid)
    if g == GID_AREA_SPRAYER:
        return EnemyArchetype(75.0, alpha=178, ghost_walls=True, ghost_area=True, ai="area_spray", chase_aggressive=True)
    if g == GID_TINY_FRACTION:
        return EnemyArchetype(
            0.01, head_label="0.01", speed_mult=10.0, shoot_cd_mult=1.0 / 3.0,
            scale_mult=0.1, alpha=178, chase_aggressive=True, ai="tiny_fraction",
        )
    if g == GID_NEGATIVE_ONE:
        return EnemyArchetype(
            1.0, head_label="-1", alpha=153, chase_aggressive=True, ai="neg_one",
            only_heal_bullet_hurt=True,
        )
    if g == GID_GIANT_256:
        return EnemyArchetype(256.0, head_label="256", speed_mult=0.25, ai="giant_256", chase_aggressive=True)
    if g == GID_EXP_X:
        return EnemyArchetype(
            math.exp(5),
            head_label="e^x",
            alpha=int(255 * 0.7),
            ghost_walls=True,
            ghost_area=True,
            speed_mult=1.1,
            calculus_immune=True,
            chase_aggressive=True,
            ai="exp_flyer",
            melee_bump=True,
        )
    if g == GID_KEY_TANK:
        return EnemyArchetype(
            99999.0, head_label="99999", speed_mult=0.7, ai="melee_tank",
            chase_aggressive=True, melee_bump=True,
        )
    if g == GID_SIN_WAVE:
        return EnemyArchetype(
            150.0,
            head_label="sin(x)",
            speed_mult=3.0,
            scale_mult=1.0,
            ghost_walls=False,
            ai="sin_wave",
            chase_aggressive=True,
        )
    if g == GID_CHASHER:
        return EnemyArchetype(100.0, chase_aggressive=True, ai="chase_melee", melee_bump=True)
    if g == GID_SHOOTER:
        return EnemyArchetype(100.0, ai="default")
    return None
