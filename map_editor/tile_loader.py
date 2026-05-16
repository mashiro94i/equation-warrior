"""
地圖編輯器用圖塊載入器（隸屬 map_editor）
- 優先使用 map_editor/img/tile/<id>.png（若存在）
- 否則使用程式產生的 placeholder 色塊
"""
import pygame
from pathlib import Path


# 與方程式戰士關卡 CSV 語意一致（-1 空，0-8 地板/牆，9-10 水，11-14 裝飾，15 玩家，16 敵人，17-19 道具，20 出口/核心）
TILE_NAMES = {
    -1: "Air",
    0: "Ground_1", 1: "Ground_2", 2: "Ground_3", 3: "Ground_4", 4: "Ground_5", 5: "Ground_6", 6: "Ground_7", 7: "Ground_8", 8: "Ground_9",
    9: "水_1", 10: "水_2",
    11: "Decoration_1", 12: "Decoration_2", 13: "Decoration_3", 14: "Decoration_4",
    15: "Spawn_A",
    16: "Spawn_B",
    17: "Ammo_Box", 18: "Grenade_Box", 19: "Heal_Box",
    20: "Core",
}


def _make_placeholder(surface: pygame.Surface, tile_id: int, size: int) -> pygame.Surface:
    """產生單一 tile 的 placeholder 色塊。"""
    colors = {
        -1: (40, 44, 52),
        0: (139, 90, 43),
        1: (120, 80, 40),
        2: (100, 70, 35),
        3: (110, 75, 38),
        4: (130, 85, 45),
        5: (125, 82, 42),
        6: (115, 78, 39),
        7: (105, 72, 36),
        8: (95, 65, 32),
        9: (64, 164, 223),
        10: (54, 154, 213),
        11: (80, 120, 80),
        12: (90, 130, 90),
        13: (70, 110, 70),
        14: (100, 140, 100),
        15: (80, 200, 255),
        16: (255, 100, 100),
        17: (200, 180, 80),
        18: (180, 160, 60),
        19: (255, 120, 120),
        20: (255, 200, 0),
    }
    color = colors.get(tile_id, (80, 80, 80))
    s = pygame.Surface((size, size))
    s.fill(color)
    if tile_id == -1:
        pygame.draw.rect(s, (60, 64, 72), (0, 0, size, size), 1)
    else:
        pygame.draw.rect(s, (30, 30, 30), (0, 0, size, size), 1)
    if tile_id == 15:
        pygame.draw.rect(s, (255, 255, 255), (size//4, size//4, size//2, size//2), 2)
    elif tile_id == 16:
        pygame.draw.circle(s, (255, 255, 255), (size//2, size//2), size//4, 2)
    elif tile_id == 20:
        pygame.draw.rect(s, (200, 160, 0), (4, 4, size-8, size-8), 2)
    return s


def load_tile_set(tile_size: int) -> dict:
    """
    回傳 { tile_id: Surface }，僅包含會用於編輯器的 id（-1, 0-20）。
    """
    out = {}
    base = Path(__file__).resolve().parent
    tile_dir = base / "img" / "tile"

    for tid in list(TILE_NAMES.keys()):
        if tid < 0:
            out[tid] = _make_placeholder(pygame.Surface((1, 1)), tid, tile_size)
            continue
        path = tile_dir / f"{tid}.png"
        if path.is_file():
            try:
                img = pygame.image.load(str(path)).convert_alpha()
                out[tid] = pygame.transform.scale(img, (tile_size, tile_size))
            except Exception:
                out[tid] = _make_placeholder(pygame.Surface((1, 1)), tid, tile_size)
        else:
            out[tid] = _make_placeholder(pygame.Surface((1, 1)), tid, tile_size)

    return out
