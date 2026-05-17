"""遊戲狀態 / 類型 enum"""
from enum import Enum


class PowerType(Enum):
    LINEAR = 1
    QUADRATIC = 2
    CUBIC = 3


class AimState(Enum):
    IDLE = "idle"
    AIMING = "aiming"


class GameState(Enum):
    MENU = "menu"
    PLAYING = "playing"
    DEATH = "death"
    WIN = "win"


class CharacterTypes(Enum):
    Player = "player"
    Enemy = "enemy"


class ActionTypes(Enum):
    IDLE = "Idle"
    RUN = "Run"
    JUMP = "Jump"
    DEATH = "Death"


class PlayerMode(Enum):
    """玩家當前工具模式（數字鍵切換，實作逐步開放）"""
    FUNCTION = "function"           # 函數圖形發射
    DERIVATIVE_BLOCK = "d_block"    # 微分塊
    INTEGRAL_BLOCK = "int_block"    # 積分塊
    INTEGRAL_XY = "int_xy"          # ∫x/∫y 對敵彈／畫筆
    SIGMOID = "sigmoid"             # S 型點敵彈（舊）
    SIGMA = "sigma"                 # Σ 蓄力數字彈
    BRUSH = "brush"                 # 畫筆
    AREA_MOVE = "area_move"         # 連按兩次 B：拖曳靜止面積（不可壓進地圖）
    SQUARE_BLOCK = "square_block"   # x² 塊（關卡 3）
    SQRT_BLOCK = "sqrt_block"       # √x 塊（關卡 3）


class IntegralAxis(Enum):
    X = "x"
    Y = "y"
