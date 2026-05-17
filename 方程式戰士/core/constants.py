"""遊戲常數：尺寸、物理、顏色"""

# ========== 尺寸 ==========
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900
ROWS = 16
COLS = 20

# 地圖一格邊長（像素）
# - 設為 None：自動 = 螢幕高度 ÷ ROWS（格數填滿直向）
# - 設為正整數：強制使用該邊長（例如 48、64）
TILE_SIZE_USER: int | None = None


def _tile_size_px() -> int:
    if TILE_SIZE_USER is not None:
        return max(8, int(TILE_SIZE_USER))
    return SCREEN_HEIGHT // ROWS


TILE_SIZE = _tile_size_px()
FPS = 60

# 鏡頭：玩家靠近螢幕左右緣時捲動世界（與 practice/game.py 相同概念）
SCROLL_THRESH = max(120, int(200 * SCREEN_WIDTH / 800))

# 與 map_editor 一致：CSV 內 >= 此值視為 Kenney 等自訂圖塊（主遊戲以佔位障礙顯示）
KENNEY_TILE_BASE = 256

# 地刺：踩住每秒扣最大血量 1/10；傷害／顯示區為格底向上約 0.7 格高
SPIKE_DAMAGE_INTERVAL_MS = 1000
SPIKE_DAMAGE_HEIGHT_FRAC = 0.7

# ========== 玩家／平衡（規格 v3）==========
# 血量：調整玩家／敵人強度請改此處；Enemy(x,y,max_hp=…) 可覆寫單體血量
PLAYER_MAX_HP = 200.0
ENEMY_DEFAULT_MAX_HP = 100.0

HP_DECIMAL_PLACES = 2

# 角色貼圖縮放（Kenney / assets 動畫相對原圖；數字越大角色越大）
PLAYER_VISUAL_SCALE = 3.0
ENEMY_VISUAL_SCALE = 1.0

# 模式冷卻（毫秒）：離開該模式後鎖定
COOLDOWN_MS_LEAVE_DERIV_BLOCK = 1000
COOLDOWN_MS_LEAVE_INT_BLOCK = 1000
COOLDOWN_MS_LEAVE_SIGMOID = 10000
COOLDOWN_MS_LEAVE_SIGMA = 15000

# 微積分塊
CALC_BLOCK_W = 44
CALC_BLOCK_H = 28
CALC_BLOCK_INTEGRAL_H = CALC_BLOCK_H * 3
CALC_BLOCK_GRAVITY = 0.55
DERIVATIVE_BLOCKS_MAX = 1
INTEGRAL_BLOCKS_MAX = 3
# 達上限時是否自動刪除最舊的一塊以容納新塊；False = 達上限則無法再放置
CALC_DERIVATIVE_EVICT_OLDEST_WHEN_FULL = False
CALC_INTEGRAL_EVICT_OLDEST_WHEN_FULL = True
SQUARE_BLOCKS_MAX = 3
SQRT_BLOCKS_MAX = 3
SQUARE_SPLIT_ANGLE_DEG = 15

# 關卡 3：治療 Sigmoid（切換後攻擊改為回復敵人）
HEAL_SIGMOID_HEAL_AMOUNT = 1.0

# 積分塊碰到我方方程式子彈：視覺與傷害倍率（僅第一次生效）
INTEGRAL_HIT_BULLET_RADIUS_MULT = 1.85
INTEGRAL_HIT_BULLET_DAMAGE_MULT = 1.5

# 連按兩次 B 進入面積拖曳模式（毫秒內）
DOUBLE_B_AREA_MOVE_MS = 450

# ∫x/∫y 對敵彈加長（像素上限）
INTEGRAL_XY_EXTEND_MAX_PX = 140

# 畫筆
BRUSH_MAX_STROKES = 5
BRUSH_MAX_TOTAL_LENGTH_PX = 1800
BRUSH_MIN_SEGMENT = 3

# 面積體（擋彈）
AREA_BODY_ALPHA_LAYERS = (220, 150, 80)  # 被擊中 0→1→2 後碎裂
AREA_BODY_PUSH_SPEED = 5.0
# 面積拖曳：左鍵放開瞬間，游標與「上一幀結束時」邏輯座標距離 ≥ 門檻 → 沿該位移方向甩出
AREA_THROW_RELEASE_MIN_DIST = 4.5
AREA_THROW_RELEASE_SPEED_MULT = 2.35
AREA_THROW_MIN_SPEED = 0.85
AREA_THROW_MAX_SPEED = 26.0
AREA_THROW_AIR_FRICTION = 0.988
AREA_DAMAGE_MIN = 50
AREA_DAMAGE_MAX = 500
AREA_DAMAGE_ANCHOR_RATIO = 2.0      # 半徑倍率 2x
AREA_DAMAGE_ANCHOR_DAMAGE = 100.0   # 對應傷害 100
AREA_DAMAGE_TARGET_RATIO = 4.0      # 半徑倍率 4x
AREA_DAMAGE_TARGET_DAMAGE = 350.0   # 對應傷害 350

# CSV 65796：∫dy 淺藍填充（僅地圖生成面積體啟用）
MAP_AREA_FILL_RGBA = (165, 225, 255, 215)
MAP_AREA_OUTLINE_RGB = (85, 155, 205)

# Sigmoid 治療（測試可覆寫）
SIGMOID_HEAL_MAX = 4.0
SIGMOID_ALPHA = 0.05

# Sigma
SIGMA_CHARGE_STEP_MS = 500
SIGMA_CHARGE_STEP_VALUE = 1
SIGMA_CHARGE_MAX = 10.0
SIGMA_FIRE_INTERVAL_MS = 250
SIGMA_ZERO_BURST_COUNT = 10

# 我方攻擊：基礎傷害 × 倍率（方程式子彈、Σ 數字彈等）
PLAYER_PROJECTILE_DAMAGE = 25
PLAYER_ATTACK_POWER_MULT = 1.0

# 敵彈命中玩家時扣血（Sigmoid 互動亦用此值估算治療）
ENEMY_BULLET_DAMAGE = 10.0
# 65834 等近戰怪碰玩家扣血（間隔避免每幀連刷）；傷害預設與敵彈相同
ENEMY_MELEE_CONTACT_INTERVAL_MS = 550


def player_attack_hit_damage() -> float:
    """實際方程式／Σ 對敵造成傷害的基準值。"""
    return float(PLAYER_PROJECTILE_DAMAGE) * float(PLAYER_ATTACK_POWER_MULT)


# ========== 物理 ==========
GRAVITY = 0.6
JUMP_IMPULSE = -14
MAX_LEVEL = 3

# ========== 顏色 ==========
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (220, 60, 60)
GREEN = (60, 200, 80)
BLUE = (60, 130, 220)
PURPLE = (150, 50, 200)
GOLD = (240, 200, 50)
GRAY = (90, 90, 90)
DARK_GRAY = (50, 50, 50)
SKY = (135, 180, 220)
YELLOW = (250, 220, 60)
PINK = (235, 65, 54)
WATER_BLUE = (50, 100, 200)
