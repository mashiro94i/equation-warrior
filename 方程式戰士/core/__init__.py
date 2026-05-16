"""方程式戰士 核心模組

統一 re-export 給 game.py / test_game.py / 外部使用
"""
from .constants import *  # noqa: F401, F403
from .enums import (  # noqa: F401
    ActionTypes, AimState, CharacterTypes, GameState, IntegralAxis, PlayerMode,
    PowerType,
)
from .fonts import get_font  # noqa: F401
from .equation import Equation  # noqa: F401
from .gameplay import (  # noqa: F401
    build_sigma_shot_schedule,
    clamp_degree,
    degree_to_fire_power,
    placement_zone_around_player,
    placement_zone_left_third,
    round_hp,
    sigmoid_heal_from_damage,
)
from .projectile import EnemyBullet, MathProjectile, NumericProjectile  # noqa: F401
from .calculus_blocks import CalculusBlock, resolve_calculus_block_interactions  # noqa: F401
from .brush import BrushManager  # noqa: F401
from .area_entity import AreaBody  # noqa: F401
from .mode_cooldowns import ModeCooldowns  # noqa: F401
from .controller import EquationController, EquationDisplay  # noqa: F401
from .soldier import Enemy, Player, Soldier  # noqa: F401
from .ui import HealthBar, ScreenFade, TextButton  # noqa: F401
from .world import Decoration, Exit, HealthBox, Water, World  # noqa: F401
from .main import init_level, main  # noqa: F401
