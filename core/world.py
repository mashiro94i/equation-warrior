"""場景 sprite + 關卡資料 (CSV) 載入"""
import csv
import os
import pygame

from .assets import (
    fallback_tile_decoration, fallback_tile_dirt, fallback_tile_exit,
    fallback_tile_health_box, fallback_tile_water,
)
from .constants import COLS, ROWS, TILE_SIZE


class HealthBox(pygame.sprite.Sprite):
    HEAL = 30

    def __init__(self, x, y):
        super().__init__()
        self.image = fallback_tile_health_box()
        self.rect = self.image.get_rect(topleft=(x, y))

    def update(self, player):
        if pygame.sprite.collide_rect(self, player) and player.is_alive:
            player.heal(self.HEAL)
            self.kill()


class Decoration(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = fallback_tile_decoration()
        self.rect = self.image.get_rect(topleft=(x, y))


class Water(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = fallback_tile_water()
        self.rect = self.image.get_rect(topleft=(x, y))


class Exit(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image = fallback_tile_exit()
        self.rect = self.image.get_rect(topleft=(x, y))


class World:
    """純資料容器，sprite 由 init_level() 建立"""

    def __init__(self):
        self.obstacle_list = []  # [(img, rect)]
        self.player_spawn = (TILE_SIZE * 1, TILE_SIZE * 12)
        self.enemy_spawns = []
        self.water_tiles = []
        self.decorations = []
        self.exit_pos = None
        self.health_box_positions = []

    def process_csv(self, level, base_dir="."):
        path = os.path.join(base_dir, f"level{level}_data.csv")
        world_data = [[-1 for _ in range(COLS)] for _ in range(ROWS)]
        if not os.path.exists(path):
            print(f"WARN: {path} not found")
            return
        with open(path, newline="") as f:
            reader = csv.reader(f, delimiter=",")
            for y, row in enumerate(reader):
                if y >= ROWS:
                    break
                for x, cell in enumerate(row):
                    if x >= COLS:
                        break
                    cell = cell.strip()
                    if not cell:
                        continue
                    try:
                        world_data[y][x] = int(cell)
                    except ValueError:
                        pass
        for y, row in enumerate(world_data):
            for x, tile in enumerate(row):
                if tile < 0:
                    continue
                wx, wy = x * TILE_SIZE, y * TILE_SIZE
                if 0 <= tile <= 8:
                    img = fallback_tile_dirt()
                    rect = img.get_rect(topleft=(wx, wy))
                    self.obstacle_list.append((img, rect))
                elif 9 <= tile <= 10:
                    self.water_tiles.append((wx, wy))
                elif 11 <= tile <= 14:
                    self.decorations.append((wx, wy))
                elif tile == 15:
                    self.player_spawn = (wx + TILE_SIZE // 2, wy + TILE_SIZE // 2)
                elif tile == 16:
                    self.enemy_spawns.append((wx + TILE_SIZE // 2, wy + TILE_SIZE // 2))
                elif tile == 19:
                    self.health_box_positions.append((wx, wy))
                elif tile == 20:
                    self.exit_pos = (wx, wy)

    def draw_obstacles(self, surface):
        for img, rect in self.obstacle_list:
            surface.blit(img, rect)
