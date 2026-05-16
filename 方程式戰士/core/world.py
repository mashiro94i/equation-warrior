"""場景 sprite + 關卡資料 (CSV) 載入"""
import csv
import os
from pathlib import Path

import pygame

from .assets import (
    tile_decoration,
    tile_exit,
    tile_health_pickup,
    tile_obstacle,
    tile_water,
)
from .constants import KENNEY_TILE_BASE, TILE_SIZE
from .paths import find_map_dir_for_level
from . import game_audio
from .map_tile_loader import make_colored_stub, surface_for_gid
from .tile_types import (
    GID_AREA_TILE,
    GID_ENEMIES,
    GID_HEART,
    GID_KEY,
    GID_KEY_DOOR,
    GID_MAP_CALC_DERIVATIVE_BLOCK,
    GID_MAP_CALC_INTEGRAL_BLOCK,
    GID_SPIKE,
    GID_SPIKE_SWITCH,
    GID_SPAWN,
    classify_tile,
)

# 語意格無 PNG 時的佔位色
_SEMANTIC_RGB = {
    GID_SPAWN: (80, 200, 255),
    GID_SPIKE: (200, 60, 60),
    GID_HEART: (255, 100, 140),
    GID_SPIKE_SWITCH: (180, 160, 60),
    65834: (255, 100, 100),
    65835: (255, 115, 105),
    65837: (235, 95, 105),
    65838: (245, 85, 95),
    65840: (240, 90, 90),
    65841: (235, 88, 92),
    131449: (220, 80, 120),
    131448: (210, 70, 110),
    65850: (90, 85, 80),
    65875: (70, 70, 75),
    13142: (82, 78, 74),
    131342: (82, 78, 74),
    GID_AREA_TILE: (100, 200, 140),
    13168: (170, 110, 70),
    131368: (170, 110, 70),
    65992: (255, 220, 80),
    66019: (255, 200, 60),
    GID_KEY: (230, 200, 80),
    GID_KEY_DOOR: (120, 90, 50),
    GID_MAP_CALC_INTEGRAL_BLOCK: (90, 140, 220),
    GID_MAP_CALC_DERIVATIVE_BLOCK: (220, 140, 90),
}


def _tile_surface(tile_id: int) -> pygame.Surface | None:
    rgb = _SEMANTIC_RGB.get(tile_id)
    return surface_for_gid(tile_id, TILE_SIZE, fallback_rgb=rgb)


class HealthBox(pygame.sprite.Sprite):
    HEAL = 30

    def __init__(self, x, y):
        super().__init__()
        self.image = tile_health_pickup()
        self.rect = self.image.get_rect(topleft=(x, y))

    def update(self, player):
        if pygame.sprite.collide_rect(self, player) and player.is_alive:
            player.heal(self.HEAL)
            self.kill()


class KeyPickup(pygame.sprite.Sprite):
    """鑰匙：拾取後累加 player.key_count。"""

    def __init__(self, x, y, tile_id: int = GID_KEY):
        super().__init__()
        img = _tile_surface(tile_id) or make_colored_stub(TILE_SIZE, _SEMANTIC_RGB[GID_KEY])
        self.image = img
        self.rect = self.image.get_rect(topleft=(x, y))

    def update(self, player):
        if pygame.sprite.collide_rect(self, player) and player.is_alive:
            player.key_count += 1
            game_audio.play_pickup()
            self.kill()


class KenneyVisualTile(pygame.sprite.Sprite):
    """CSV 內 Kenney 語意未定義的格（僅顯示、無碰撞）。"""

    def __init__(self, x, y, tile_id: int):
        super().__init__()
        img = _tile_surface(tile_id) or make_colored_stub(TILE_SIZE, (140, 140, 160))
        self.image = img
        self.rect = self.image.get_rect(topleft=(x, y))


class HeartPickup(pygame.sprite.Sprite):
    """愛心：拾取回復最大血量 1/3。"""

    def __init__(self, x, y, tile_id: int = GID_HEART):
        super().__init__()
        img = _tile_surface(tile_id) or make_colored_stub(TILE_SIZE, _SEMANTIC_RGB[GID_HEART])
        self.image = img
        self.rect = self.image.get_rect(topleft=(x, y))

    def update(self, player):
        if pygame.sprite.collide_rect(self, player) and player.is_alive:
            player.heal(player.max_health / 3.0)
            game_audio.play_pickup()
            self.kill()


class Decoration(pygame.sprite.Sprite):
    def __init__(self, x, y, variant=0):
        super().__init__()
        self.image = tile_decoration(variant)
        self.rect = self.image.get_rect(topleft=(x, y))


class Water(pygame.sprite.Sprite):
    def __init__(self, x, y, variant=0):
        super().__init__()
        self.image = tile_water(variant)
        self.rect = self.image.get_rect(topleft=(x, y))


class Exit(pygame.sprite.Sprite):
    """終點：legacy 20 用內建圖；65992／66019 等 Kenney 格用 tile PNG 或佔位色。"""

    def __init__(self, x, y, tile_id: int = 20):
        super().__init__()
        if tile_id == 20:
            self.image = tile_exit()
        else:
            img = _tile_surface(tile_id) or make_colored_stub(
                TILE_SIZE, _SEMANTIC_RGB.get(tile_id, (255, 220, 80))
            )
            self.image = img
        self.rect = self.image.get_rect(topleft=(x, y))


class World:
    """純資料容器，sprite 由 init_level() 建立"""

    def __init__(self):
        self._wall_obstacles: list[tuple[pygame.Surface, pygame.Rect]] = []
        # 每格獨立 surface；玩家碰觸瞬間水平 flip
        self._spike_obstacles: list[dict] = []
        self._spike_touch_prev: set[tuple[int, int]] = set()
        self.obstacle_list: list[tuple[pygame.Surface, pygame.Rect]] = []
        self.player_spawn = (TILE_SIZE * 1, TILE_SIZE * 12)
        self.respawn_point: tuple[int, int] | None = None
        self.enemy_spawns: list[tuple[int, int, int]] = []
        self.water_tiles: list[tuple[int, int, int]] = []
        self.decorations: list[tuple[int, int, int]] = []
        self.exit_pos: tuple[int, int] | None = None
        self.exit_tiles: list[tuple[int, int, int]] = []
        self.grid_data: list[list[int]] = []
        self._destructible_wall_entries: list[tuple[pygame.Surface, pygame.Rect, int, int]] = []
        self.health_box_positions: list[tuple[int, int]] = []
        self.heart_pickups: list[tuple[int, int, int]] = []
        self.key_pickups: list[tuple[int, int, int]] = []
        self._key_door_entries: list[tuple[pygame.Surface, pygame.Rect, int, int]] = []
        self.kenney_visual_tiles: list[tuple[int, int, int]] = []
        self.calculus_derivative_spawns: list[tuple[int, int]] = []
        self.calculus_integral_spawns: list[tuple[int, int, str]] = []
        self._spike_switch_tiles: list[tuple[pygame.Surface, pygame.Rect]] = []
        self.spikes_extended = True
        self._switch_latch = False
        self.level_cols = 0
        self.level_rows = 0
        # 關卡 CSV 欄數（整體最右 tile 欄位 +1），與 practice/game.py 的 world_length 相同
        self.world_length = 1
        self.map_csv_path: str | None = None

    def set_world_length_from_csv(self, world_data: list[list[int]]) -> None:
        """整關水平長度 = 地圖資料最寬一列的欄數（含空白格）。"""
        self.world_length = max((len(row) for row in world_data), default=1)
        self.level_cols = self.world_length

    def scroll_max_px(self, screen_w: int) -> int:
        return max(0, self.world_length * TILE_SIZE - screen_w)

    def rebuild_obstacle_list(self) -> None:
        # 地刺不進 obstacle_list：角色／面積可穿過該格，僅靠 spike_damage_rects() 扣血
        self.obstacle_list = list(self._wall_obstacles)

    def remove_destructible_walls_hitting(self, area) -> bool:
        """面積體與可破壞牆像素重疊時移除該格並更新碰撞。回傳是否有移除。"""
        if not self._destructible_wall_entries:
            return False
        removed = False
        for i in range(len(self._destructible_wall_entries) - 1, -1, -1):
            _img, rect, gx, gy = self._destructible_wall_entries[i]
            if not area.intersects_rect(rect):
                continue
            self._destructible_wall_entries.pop(i)
            self._wall_obstacles = [pair for pair in self._wall_obstacles if pair[1] is not rect]
            if self.grid_data and 0 <= gy < len(self.grid_data):
                row = self.grid_data[gy]
                if 0 <= gx < len(row):
                    row[gx] = -1
            removed = True
        if removed:
            self.rebuild_obstacle_list()
            game_audio.play_break()
        return removed

    def toggle_spikes(self) -> None:
        """機關：伸出 ↔ 收回地刺。"""
        self.spikes_extended = not self.spikes_extended
        self.rebuild_obstacle_list()

    def try_toggle_spike_switch(
        self,
        player_rect: pygame.Rect,
        area_group=None,
        integral_group=None,
        derivative_group=None,
    ) -> None:
        """玩家／面積／積分塊／微分塊碰機關格時切換（皆離開後才可再觸發）。"""
        switches = self._spike_switch_tiles
        touching = any(player_rect.colliderect(r) for _img, r in switches)
        if not touching and area_group is not None:
            for area in area_group:
                if not area.alive():
                    continue
                if any(area.intersects_rect(r) for _img, r in switches):
                    touching = True
                    break
        if not touching and integral_group is not None:
            for ib in integral_group:
                if not ib.alive() or ib.kind != "integral":
                    continue
                if any(ib.rect.colliderect(r) for _img, r in switches):
                    touching = True
                    break
        if not touching and derivative_group is not None:
            for db in derivative_group:
                if not db.alive():
                    continue
                if any(db.rect.colliderect(r) for _img, r in switches):
                    touching = True
                    break
        if touching:
            if not self._switch_latch:
                self.toggle_spikes()
                game_audio.play_flip()
                self._switch_latch = True
        else:
            self._switch_latch = False

    def try_consume_key_for_doors(self, player) -> None:
        """玩家持有鑰匙且與鑰匙門重疊時消耗一把並移除該門格（碰撞稍放大以免貼牆時無法觸發）。"""
        if player.key_count <= 0 or not self._key_door_entries or not player.is_alive:
            return
        probe = player.rect.inflate(14, 20)
        for i in range(len(self._key_door_entries) - 1, -1, -1):
            _img, rect, gx, gy = self._key_door_entries[i]
            if not probe.colliderect(rect):
                continue
            player.key_count -= 1
            self._key_door_entries.pop(i)
            self._wall_obstacles = [pair for pair in self._wall_obstacles if pair[1] is not rect]
            if self.grid_data and 0 <= gy < len(self.grid_data):
                row = self.grid_data[gy]
                if 0 <= gx < len(row):
                    row[gx] = -1
            self.rebuild_obstacle_list()
            game_audio.play_flip()
            return

    def spike_damage_rects(self) -> list[pygame.Rect]:
        if not self.spikes_extended:
            return []
        return [sp["rect"] for sp in self._spike_obstacles]

    def update_spike_flip_on_player_contact(self, player_rect: pygame.Rect) -> None:
        """玩家進入地刺格瞬間（上升沿）將該格圖像水平翻轉。"""
        if not self.spikes_extended:
            self._spike_touch_prev.clear()
            return
        touching: set[tuple[int, int]] = set()
        for sp in self._spike_obstacles:
            rect = sp["rect"]
            key = (rect.x, rect.y)
            if player_rect.colliderect(rect):
                touching.add(key)
                if key not in self._spike_touch_prev:
                    sp["flipped"] = not sp["flipped"]
                    if sp["flipped"]:
                        sp["image"] = pygame.transform.flip(sp["base"], True, False)
                    else:
                        sp["image"] = sp["base"].copy()
        self._spike_touch_prev = touching

    def draw_spikes(self, surface: pygame.Surface) -> None:
        for sp in self._spike_obstacles:
            img = sp["image"]
            rect = sp["rect"]
            if self.spikes_extended:
                surface.blit(img, rect)
            else:
                dim = img.copy()
                dim.set_alpha(90)
                surface.blit(dim, rect)

    def draw_spike_switches(self, surface: pygame.Surface) -> None:
        for img, rect in self._spike_switch_tiles:
            surface.blit(img, rect)

    def process_csv(self, level, base_dir=None):
        """
        讀取 `level{level}.csv` 或 `level{level}_data.csv`。
        base_dir 為 None 時：優先 `map_editor/map/`，其次 `方程式戰士/map/`。
        """
        self._wall_obstacles.clear()
        self._spike_obstacles.clear()
        self._spike_touch_prev.clear()
        self.obstacle_list.clear()
        self.enemy_spawns.clear()
        self.water_tiles.clear()
        self.decorations.clear()
        self.exit_pos = None
        self.exit_tiles.clear()
        self.grid_data.clear()
        self._destructible_wall_entries.clear()
        self.health_box_positions.clear()
        self.heart_pickups.clear()
        self.key_pickups.clear()
        self._key_door_entries.clear()
        self.kenney_visual_tiles.clear()
        self.calculus_derivative_spawns.clear()
        self.calculus_integral_spawns.clear()
        self._spike_switch_tiles.clear()
        self.spikes_extended = True
        self._switch_latch = False
        self.respawn_point = None

        if base_dir is None:
            map_dir = find_map_dir_for_level(level)
            base_dir = str(map_dir)
        path = None
        for name in (f"level{level}.csv", f"level{level}_data.csv"):
            candidate = os.path.join(base_dir, name)
            if os.path.isfile(candidate):
                path = candidate
                break
        self.map_csv_path = path
        world_data: list[list[int]] = []
        if path is None:
            print(f"WARN: no level file for level {level} in {base_dir}")
            self.grid_data.clear()
            self.set_world_length_from_csv([])
            self.rebuild_obstacle_list()
            return
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=",")
            for row in reader:
                parsed: list[int] = []
                for cell in row:
                    cell = cell.strip()
                    if not cell:
                        parsed.append(-1)
                        continue
                    try:
                        parsed.append(int(cell))
                    except ValueError:
                        parsed.append(-1)
                world_data.append(parsed)

        map_rows = len(world_data)
        map_cols = max((len(r) for r in world_data), default=0)
        use_rows = map_rows
        use_cols = map_cols
        self.level_rows = use_rows
        self.level_cols = use_cols

        for y in range(use_rows):
            row = world_data[y]
            for x in range(use_cols):
                if x >= len(row):
                    continue
                tile = row[x]
                if tile < 0:
                    continue
                wx, wy = x * TILE_SIZE, y * TILE_SIZE
                kind = classify_tile(tile)

                if kind == "spawn":
                    cx, cy = wx + TILE_SIZE // 2, wy + TILE_SIZE // 2
                    self.player_spawn = (cx, cy)
                    self.respawn_point = (cx, cy)
                elif kind == "enemy":
                    self.enemy_spawns.append((wx + TILE_SIZE // 2, wy + TILE_SIZE // 2, tile))
                elif kind == "enemy_walk_alt":
                    pass
                elif kind == "area_tile":
                    pass
                elif kind == "map_calc_derivative":
                    cx = wx + TILE_SIZE // 2
                    cy = wy + TILE_SIZE // 2
                    self.calculus_derivative_spawns.append((cx, cy))
                elif kind == "map_calc_integral":
                    cx = wx + TILE_SIZE // 2
                    cy = wy + TILE_SIZE // 2
                    self.calculus_integral_spawns.append((cx, cy, "y"))
                elif kind == "destructible_wall":
                    img = _tile_surface(tile) or make_colored_stub(
                        TILE_SIZE, _SEMANTIC_RGB.get(tile, (170, 110, 70))
                    )
                    rect = img.get_rect(topleft=(wx, wy))
                    self._wall_obstacles.append((img, rect))
                    self._destructible_wall_entries.append((img, rect, x, y))
                elif kind == "level_exit":
                    self.exit_tiles.append((wx, wy, tile))
                elif kind == "wall":
                    img = _tile_surface(tile) or make_colored_stub(
                        TILE_SIZE, _SEMANTIC_RGB.get(tile, (88, 85, 82))
                    )
                    self._wall_obstacles.append((img, img.get_rect(topleft=(wx, wy))))
                elif kind == "spike":
                    img0 = _tile_surface(tile) or make_colored_stub(
                        TILE_SIZE, _SEMANTIC_RGB[GID_SPIKE]
                    )
                    base = img0.copy()
                    rect = base.get_rect(topleft=(wx, wy))
                    self._spike_obstacles.append(
                        {
                            "base": base,
                            "image": base.copy(),
                            "rect": rect,
                            "flipped": False,
                        }
                    )
                elif kind == "heart":
                    self.heart_pickups.append((wx, wy, tile))
                elif kind == "key_pickup":
                    self.key_pickups.append((wx, wy, tile))
                elif kind == "key_door":
                    img = _tile_surface(tile) or make_colored_stub(
                        TILE_SIZE, _SEMANTIC_RGB.get(tile, (120, 90, 50))
                    )
                    rect = img.get_rect(topleft=(wx, wy))
                    self._wall_obstacles.append((img, rect))
                    self._key_door_entries.append((img, rect, x, y))
                elif kind == "switch":
                    img = _tile_surface(tile) or make_colored_stub(
                        TILE_SIZE, _SEMANTIC_RGB[GID_SPIKE_SWITCH]
                    )
                    self._spike_switch_tiles.append((img, img.get_rect(topleft=(wx, wy))))
                elif kind == "legacy":
                    if 0 <= tile <= 8:
                        img = surface_for_gid(tile, TILE_SIZE) or tile_obstacle()
                        if img is not None:
                            self._wall_obstacles.append((img, img.get_rect(topleft=(wx, wy))))
                    elif 9 <= tile <= 10:
                        self.water_tiles.append((wx, wy, tile - 9))
                    elif 11 <= tile <= 14:
                        self.decorations.append((wx, wy, tile - 11))
                    elif tile == 15:
                        cx, cy = wx + TILE_SIZE // 2, wy + TILE_SIZE // 2
                        self.player_spawn = (cx, cy)
                        if self.respawn_point is None:
                            self.respawn_point = (cx, cy)
                    elif tile == 16:
                        self.enemy_spawns.append((wx + TILE_SIZE // 2, wy + TILE_SIZE // 2, 65834))
                    elif tile == 19:
                        self.health_box_positions.append((wx, wy))
                    elif tile == 20:
                        self.exit_tiles.append((wx, wy, 20))
                elif kind == "air" and tile >= KENNEY_TILE_BASE:
                    self.kenney_visual_tiles.append((wx, wy, tile))

        self.grid_data = [row[:] for row in world_data]
        self.set_world_length_from_csv(world_data)
        self.exit_pos = (self.exit_tiles[0][0], self.exit_tiles[0][1]) if self.exit_tiles else None
        self.rebuild_obstacle_list()

    def draw_obstacles(self, surface):
        for img, rect in self.obstacle_list:
            surface.blit(img, rect)
