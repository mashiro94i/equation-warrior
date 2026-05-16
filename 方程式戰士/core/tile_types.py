"""Kenney / 地圖編輯器 CSV 格編號語意（與 map_editor 共用）。"""
from __future__ import annotations

# 出生／重生點
GID_SPAWN = 66043

# 敵人（Kenney 步行替換格見 GID_ENEMY_WALK_ALT）
GID_ENEMIES = frozenset({65834, 65838, 65840, 131449, 131448})

# 僅與主敵人格配對的動畫格，不獨立生成敵人
GID_ENEMY_WALK_ALT = frozenset({65835, 65837, 65841})

# 牆（實心碰撞）；131342 為常見 CSV 誤植（多打一個 3）
GID_WALLS = frozenset({65850, 65875, 13142, 131342})

# CSV 面積格（不當牆；關卡載入後轉成 AreaBody）
GID_AREA_TILE = 65796

# CSV 微積分符號塊（載入後轉成 CalculusBlock sprite）
GID_MAP_CALC_INTEGRAL_BLOCK = 65855
GID_MAP_CALC_DERIVATIVE_BLOCK = 65856

# 可破壞牆（面積滑行撞擊後消失；131368 為常見誤植別名）
GID_DESTRUCTIBLE_WALLS = frozenset({13168, 131368})

# 終點（與 legacy 20 相同：碰任一即過關）
GID_LEVEL_EXITS = frozenset({65992, 66019})

# 地刺（踩住持續扣血；可由機關收回）
GID_SPIKE = 65935

# 愛心（拾取回復 1/3 血量）
GID_HEART = 65904

# 機關（切換地刺伸出／收回）
GID_SPIKE_SWITCH = 65931

# 鑰匙（拾取堆疊）；鑰匙門（消耗一把鑰匙後移除該格障礙）
GID_KEY = 65880
GID_KEY_DOOR = 65881

ALL_SEMANTIC_GIDS = (
    {
        GID_SPAWN,
        GID_SPIKE,
        GID_HEART,
        GID_SPIKE_SWITCH,
        GID_AREA_TILE,
        GID_KEY,
        GID_KEY_DOOR,
        GID_MAP_CALC_INTEGRAL_BLOCK,
        GID_MAP_CALC_DERIVATIVE_BLOCK,
    }
    | GID_ENEMIES
    | GID_ENEMY_WALK_ALT
    | GID_WALLS
    | GID_DESTRUCTIBLE_WALLS
    | GID_LEVEL_EXITS
)


def classify_tile(tile_id: int) -> str:
    """回傳 spawn | enemy | enemy_walk_alt | wall | destructible_wall | area_tile | map_calc_integral | map_calc_derivative | level_exit | spike | heart | switch | key_pickup | key_door | legacy | air"""
    if tile_id < 0:
        return "air"
    if tile_id == GID_SPAWN:
        return "spawn"
    if tile_id in GID_ENEMY_WALK_ALT:
        return "enemy_walk_alt"
    if tile_id in GID_ENEMIES:
        return "enemy"
    if tile_id == GID_AREA_TILE:
        return "area_tile"
    if tile_id == GID_MAP_CALC_INTEGRAL_BLOCK:
        return "map_calc_integral"
    if tile_id == GID_MAP_CALC_DERIVATIVE_BLOCK:
        return "map_calc_derivative"
    if tile_id in GID_DESTRUCTIBLE_WALLS:
        return "destructible_wall"
    if tile_id in GID_LEVEL_EXITS:
        return "level_exit"
    if tile_id in GID_WALLS:
        return "wall"
    if tile_id == GID_SPIKE:
        return "spike"
    if tile_id == GID_HEART:
        return "heart"
    if tile_id == GID_SPIKE_SWITCH:
        return "switch"
    if tile_id == GID_KEY:
        return "key_pickup"
    if tile_id == GID_KEY_DOOR:
        return "key_door"
    if 0 <= tile_id <= 20:
        return "legacy"
    return "air"
