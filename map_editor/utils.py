"""
Shared constants and helpers for draw/button (DrawHelper, ButtonTester). Run-only constants live in run.py.
"""
import pygame

# ----- Buttons / UI (used by DrawHelper & ButtonTester) -----
LEVEL_BTN_LEFT = 10
LEVEL_BTN_W = 44
LEVEL_BTN_TOP_OFFSET = 50
SAVE_BTN_LEFT, SAVE_BTN_W = 10, 80
LOAD_BTN_LEFT, LOAD_BTN_W = 100, 80
HINT_LEFT_PAD = 10

# ----- Colors (used by DrawHelper) -----
COLOR_TOOLBAR = (50, 54, 62)
COLOR_BTN = (80, 85, 95)
COLOR_SAVE_BTN = (70, 130, 90)
COLOR_LOAD_BTN = (90, 90, 130)
COLOR_PANEL = (50, 54, 62)
COLOR_PANEL_BORDER = (70, 74, 82)
COLOR_GRIDLINE = (60, 60, 60)
COLOR_TEXT = (220, 220, 220)
COLOR_TEXT_DIM = (180, 180, 180)
COLOR_SELECTION = (255, 0, 0)
# 地圖格內 tile id 標籤（非空格）
COLOR_TILE_ID = (255, 235, 70)
COLOR_TILE_ID_SHADOW = (35, 30, 12)





class ButtonTester:
    """Hit-test for palette/map panel buttons. Params set in __init__, no config object."""

    def __init__(
        self,
        screen_h: int,
        btn_h: int,
        save_btn_left: int,
        save_btn_w: int,
        load_btn_left: int,
        load_btn_w: int,
        level_btn_left: int,
        level_btn_w: int,
        level_btn_top_offset: int,
    ):
        self._screen_h = screen_h
        self._btn_h = btn_h
        self._save_btn_left = save_btn_left
        self._save_btn_w = save_btn_w
        self._load_btn_left = load_btn_left
        self._load_btn_w = load_btn_w
        self._level_btn_left = level_btn_left
        self._level_btn_w = level_btn_w
        self._level_btn_top_offset = level_btn_top_offset

    def save_clicked(self, mx: int, my: int) -> bool:
        return (
            self._save_btn_left <= mx <= self._save_btn_left + self._save_btn_w
            and self._screen_h - self._btn_h - 10 <= my <= self._screen_h - 10
        )

    def load_clicked(self, mx: int, my: int) -> bool:
        return (
            self._load_btn_left <= mx <= self._load_btn_left + self._load_btn_w
            and self._screen_h - self._btn_h - 10 <= my <= self._screen_h - 10
        )

    def level_up_clicked(self, mx: int, my: int) -> bool:
        return (
            self._level_btn_left <= mx <= self._level_btn_left + self._level_btn_w
            and self._screen_h - self._btn_h - self._level_btn_top_offset <= my <= self._screen_h - self._btn_h - 22
        )

    def level_down_clicked(self, mx: int, my: int) -> bool:
        return (
            self._level_btn_left + self._level_btn_w + 4 <= mx <= self._level_btn_left + self._level_btn_w * 2 + 4
            and self._screen_h - self._btn_h - self._level_btn_top_offset <= my <= self._screen_h - self._btn_h - 22
        )

    @staticmethod
    def _panel_hit(mx: int, my: int, r: pygame.Rect, x1: int, x2: int, y1: int, y2: int) -> bool:
        return r.x + x1 <= mx <= r.x + x2 and r.y + y1 <= my <= r.y + y2

    def cols_plus_clicked(self, mx: int, my: int, r: pygame.Rect) -> bool:
        return self._panel_hit(mx, my, r, 134, 158, 6, 28)

    def cols_plus10_clicked(self, mx: int, my: int, r: pygame.Rect) -> bool:
        return self._panel_hit(mx, my, r, 160, 192, 6, 28)

    def cols_minus_clicked(self, mx: int, my: int, r: pygame.Rect) -> bool:
        return self._panel_hit(mx, my, r, 84, 108, 6, 28)

    def cols_minus10_clicked(self, mx: int, my: int, r: pygame.Rect) -> bool:
        return self._panel_hit(mx, my, r, 50, 82, 6, 28)

    def rows_plus_clicked(self, mx: int, my: int, r: pygame.Rect) -> bool:
        return self._panel_hit(mx, my, r, 102, 126, 36, 58)

    def rows_minus_clicked(self, mx: int, my: int, r: pygame.Rect) -> bool:
        return self._panel_hit(mx, my, r, 50, 74, 36, 58)

    def tile_size_plus_clicked(self, mx: int, my: int, r: pygame.Rect) -> bool:
        return self._panel_hit(mx, my, r, 224, 248, 36, 58)

    def tile_size_minus_clicked(self, mx: int, my: int, r: pygame.Rect) -> bool:
        return self._panel_hit(mx, my, r, 172, 196, 36, 58)



class DrawHelper:
    """Drawing and map view hit-test. __init__ only receives layout from run (no colors/button positions)."""

    def __init__(
        self,
        palette_w: int,
        map_view_w: int,
        map_view_h: int,
        toolbar_h: int,
        screen_h: int,
        btn_h: int,
        panel_w: int,
        panel_h: int,
        panel_inset: int,
        palette_tile_size: int,
        palette_cell_w: int,
        palette_cell_h: int,
        palette_left: int,
        palette_top: int,
        palette_tiles_per_row: int,
    ):
        self._palette_w = palette_w
        self._map_view_w = map_view_w
        self._map_view_h = map_view_h
        self._toolbar_h = toolbar_h
        self._screen_h = screen_h
        self._btn_h = btn_h
        self._panel_w = panel_w
        self._panel_h = panel_h
        self._panel_inset = panel_inset
        self._palette_tile_size = palette_tile_size
        self._palette_cell_w = palette_cell_w
        self._palette_cell_h = palette_cell_h
        self._palette_left = palette_left
        self._palette_top = palette_top
        self._palette_tiles_per_row = palette_tiles_per_row
        self._tile_id_font_cache: dict[int, pygame.font.Font] = {}

    def _tile_id_font(self, tile_size: int) -> pygame.font.Font:
        pt = max(7, min(18, tile_size * 3 // 10))
        if pt not in self._tile_id_font_cache:
            self._tile_id_font_cache[pt] = pygame.font.SysFont("consolas", pt, bold=True)
        return self._tile_id_font_cache[pt]

    def draw_map_view(
        self,
        surf: pygame.Surface,
        grid: list,
        flip_x_grid: list,
        tiles: dict,
        tile_size: int,
        scroll_x: int,
        scroll_y: int,
    ) -> None:
        tw, th = tile_size, tile_size
        rows, cols = len(grid), len(grid[0]) if grid else 0
        content_h = rows * th
        offset_y = (self._map_view_h - content_h) if content_h < self._map_view_h else 0
        use_scroll_y = scroll_y if offset_y == 0 else 0
        for y in range(rows):
            for x in range(cols):
                tid = grid[y][x]
                img = tiles.get(tid, tiles.get(-1))
                if y < len(flip_x_grid) and x < len(flip_x_grid[0]) and flip_x_grid[y][x]:
                    img = pygame.transform.flip(img, True, False)
                px = x * tw - scroll_x
                py = y * th - use_scroll_y + offset_y
                if px + tw < 0 or py + th < 0 or px > self._map_view_w or py > self._map_view_h:
                    continue
                surf.blit(img, (px, py))
        for col in range(0, cols + 1):
            vx = col * tw - scroll_x
            if 0 <= vx <= self._map_view_w:
                pygame.draw.line(surf, COLOR_GRIDLINE, (vx, 0), (vx, self._map_view_h))
        for row in range(0, rows + 1):
            vy = row * th - use_scroll_y + offset_y
            if 0 <= vy <= self._map_view_h:
                pygame.draw.line(surf, COLOR_GRIDLINE, (0, vy), (self._map_view_w, vy))
        # 非空格：格內黃色 id（蓋在格線之上）
        id_font = self._tile_id_font(tile_size)
        for y in range(rows):
            for x in range(cols):
                tid = grid[y][x]
                if tid < 0:
                    continue
                px = x * tw - scroll_x
                py = y * th - use_scroll_y + offset_y
                if px + tw < 0 or py + th < 0 or px > self._map_view_w or py > self._map_view_h:
                    continue
                text = str(tid)
                shadow = id_font.render(text, True, COLOR_TILE_ID_SHADOW)
                main = id_font.render(text, True, COLOR_TILE_ID)
                tx = px + (tw - main.get_width()) // 2
                ty = py + th - main.get_height() - max(1, tw // 16)
                for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                    surf.blit(shadow, (tx + ox, ty + oy))
                surf.blit(main, (tx, ty))

    def get_cell_at_screen(
        self,
        mx: int,
        my: int,
        grid: list,
        tile_size: int,
        scroll_x: int,
        scroll_y: int,
        panel_rect: pygame.Rect,
    ) -> tuple[int, int] | None:
        if mx < self._palette_w or mx >= self._palette_w + self._map_view_w or my < self._toolbar_h or my >= self._toolbar_h + self._map_view_h:
            return None
        if panel_rect.collidepoint(mx, my):
            return None
        rows, cols = len(grid), len(grid[0]) if grid else 0
        content_h = rows * tile_size
        offset_y = (self._map_view_h - content_h) if content_h < self._map_view_h else 0
        use_scroll_y = scroll_y if offset_y == 0 else 0
        local_x = mx - self._palette_w
        local_y = my - self._toolbar_h
        gx = (local_x + scroll_x) // tile_size
        gy = (local_y + use_scroll_y - offset_y) // tile_size
        if 0 <= gx < cols and 0 <= gy < rows:
            return (gx, gy)
        return None

    def map_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self._palette_w + self._map_view_w - self._panel_w - self._panel_inset,
            self._screen_h - self._panel_h - self._panel_inset,
            self._panel_w,
            self._panel_h,
        )

    def in_map_control(self, mx: int, my: int, panel_rect: pygame.Rect) -> bool:
        return panel_rect.collidepoint(mx, my)

    def draw_palette(
        self,
        screen: pygame.Surface,
        palette_tile_instances: list,
        palette_ids: list,
        palette_tiles: dict,
        selected_id: int,
        selected_flip_x: bool,
        palette_scroll: int,
        palette_view_h: int,
    ) -> None:
        clip_rect = pygame.Rect(0, 0, self._palette_w, palette_view_h)
        screen.set_clip(clip_rect)
        for tile in palette_tile_instances:
            tile.update_rect(
                palette_scroll, self._palette_cell_w, self._palette_cell_h,
                self._palette_left, self._palette_top, self._palette_tiles_per_row,
            )
            x, y = tile.rect.x, tile.rect.y
            if y + self._palette_tile_size < 0 or y > palette_view_h:
                continue
            tid = palette_ids[tile.idx]
            img = palette_tiles.get(tid, palette_tiles.get(-1))
            if tid == selected_id and selected_flip_x:
                img = pygame.transform.flip(img, True, False)
            screen.blit(img, (x, y))
            if tid == selected_id:
                pygame.draw.rect(
                    screen, COLOR_SELECTION,
                    (x - 2, y - 2, self._palette_tile_size + 4, self._palette_tile_size + 4), 3
                )
        screen.set_clip(None)

    def draw_level_selector(self, screen: pygame.Surface, font: pygame.font.Font, level: int) -> None:
        y_level = self._screen_h - self._btn_h - LEVEL_BTN_TOP_OFFSET
        pygame.draw.rect(screen, COLOR_BTN, (LEVEL_BTN_LEFT, y_level, LEVEL_BTN_W, 28))
        screen.blit(font.render("+", True, COLOR_TEXT), (LEVEL_BTN_LEFT + 14, y_level + 4))
        pygame.draw.rect(screen, COLOR_BTN, (LEVEL_BTN_LEFT + LEVEL_BTN_W + 4, y_level, LEVEL_BTN_W, 28))
        screen.blit(font.render("-", True, COLOR_TEXT), (LEVEL_BTN_LEFT + LEVEL_BTN_W + 4 + 14, y_level + 4))
        level_text = font.render(f"Level: {level}", True, COLOR_TEXT)
        screen.blit(level_text, (LEVEL_BTN_LEFT + LEVEL_BTN_W * 2 + 8, y_level + 4))

    def draw_save_load_buttons(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        y_btn = self._screen_h - self._btn_h - 10
        pygame.draw.rect(screen, COLOR_SAVE_BTN, (SAVE_BTN_LEFT, y_btn, SAVE_BTN_W, self._btn_h))
        screen.blit(font.render("Save", True, (255, 255, 255)), (SAVE_BTN_LEFT + 18, y_btn + 4))
        pygame.draw.rect(screen, COLOR_LOAD_BTN, (LOAD_BTN_LEFT, y_btn, LOAD_BTN_W, self._btn_h))
        screen.blit(font.render("Load", True, (255, 255, 255)), (LOAD_BTN_LEFT + 18, y_btn + 4))

    def draw_toolbar_hint(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(screen, COLOR_TOOLBAR, (self._palette_w, 0, self._map_view_w, self._toolbar_h))
        hint = font.render(
            "Ctrl+S/L Save/Load | R Reset | Space Flip | [ ] Pack | Palette: wheel zoom, MMB drag | Map wheel=size | WASD | LMB paint RMB clear",
            True, COLOR_TEXT_DIM,
        )
        screen.blit(hint, (self._palette_w + HINT_LEFT_PAD, 10))

    def draw_map_panel(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        cols: int,
        rows: int,
        tile_size: int,
        r: pygame.Rect,
    ) -> None:
        pygame.draw.rect(screen, COLOR_PANEL, r)
        pygame.draw.rect(screen, COLOR_PANEL_BORDER, r, 1)
        screen.blit(font.render("Cols", True, COLOR_TEXT), (r.x + 10, r.y + 8))
        pygame.draw.rect(screen, COLOR_BTN, (r.x + 50, r.y + 6, 32, 22))
        screen.blit(font.render("-10", True, COLOR_TEXT), (r.x + 53, r.y + 8))
        pygame.draw.rect(screen, COLOR_BTN, (r.x + 84, r.y + 6, 24, 22))
        screen.blit(font.render("-", True, COLOR_TEXT), (r.x + 91, r.y + 8))
        screen.blit(font.render(str(cols), True, (255, 255, 200)), (r.x + 110, r.y + 8))
        pygame.draw.rect(screen, COLOR_BTN, (r.x + 134, r.y + 6, 24, 22))
        screen.blit(font.render("+", True, COLOR_TEXT), (r.x + 141, r.y + 8))
        pygame.draw.rect(screen, COLOR_BTN, (r.x + 160, r.y + 6, 32, 22))
        screen.blit(font.render("+10", True, COLOR_TEXT), (r.x + 163, r.y + 8))
        screen.blit(font.render("Rows", True, COLOR_TEXT), (r.x + 10, r.y + 38))
        pygame.draw.rect(screen, COLOR_BTN, (r.x + 50, r.y + 36, 24, 22))
        screen.blit(font.render("-", True, COLOR_TEXT), (r.x + 57, r.y + 38))
        screen.blit(font.render(str(rows), True, (255, 255, 200)), (r.x + 78, r.y + 38))
        pygame.draw.rect(screen, COLOR_BTN, (r.x + 102, r.y + 36, 24, 22))
        screen.blit(font.render("+", True, COLOR_TEXT), (r.x + 109, r.y + 38))
        screen.blit(font.render("Size:", True, COLOR_TEXT), (r.x + 132, r.y + 38))
        pygame.draw.rect(screen, COLOR_BTN, (r.x + 172, r.y + 36, 24, 22))
        screen.blit(font.render("-", True, COLOR_TEXT), (r.x + 179, r.y + 38))
        screen.blit(font.render(str(tile_size), True, (255, 255, 200)), (r.x + 200, r.y + 38))
        pygame.draw.rect(screen, COLOR_BTN, (r.x + 224, r.y + 36, 24, 22))
        screen.blit(font.render("+", True, COLOR_TEXT), (r.x + 231, r.y + 38))
