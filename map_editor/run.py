"""
Map editor main loop.
左欄素材來自與專案同層的 kenny_assets（若無此資料夾則使用新增資料夾）；滾輪縮放、中鍵拖曳；[ ] 換包。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pygame
from tkinter import Tk, messagebox

_MAP_EDITOR_DIR = Path(__file__).resolve().parent
if not __package__:
    if str(_MAP_EDITOR_DIR) not in sys.path:
        sys.path.insert(0, str(_MAP_EDITOR_DIR))
    from tile_loader import load_tile_set  # noqa: E402
    from asset_packs import (  # noqa: E402
        PACK_STRIDE,
        gid_for,
        KENNEY_TILE_BASE,
        list_pack_dirs,
        new_assets_root,
    )
    from map_io import get_map_dir, load_csv, load_flip_csv, save_csv  # noqa: E402
    from sheet_palette import extract_tile_surface, fit_zoom, load_page_state, PageState  # noqa: E402
    from utils import ButtonTester, DrawHelper  # noqa: E402
else:
    from .tile_loader import load_tile_set
    from .asset_packs import PACK_STRIDE, gid_for, KENNEY_TILE_BASE, list_pack_dirs, new_assets_root
    from .map_io import save_csv, load_csv, load_flip_csv, get_map_dir
    from .sheet_palette import extract_tile_surface, fit_zoom, load_page_state, PageState
    from .utils import DrawHelper, ButtonTester

SCREEN_W = 1280
SCREEN_H = 720
PALETTE_W = 200
PALETTE_TILE_SIZE = 40
PALETTE_TILE_PAD = 4
PALETTE_TILES_PER_ROW = 4
PALETTE_LEFT = 8
PALETTE_TOP = 40
TOOLBAR_H = 36
BTN_H = 32
LEVEL_BTN_LEFT = 10
LEVEL_BTN_W = 44
LEVEL_BTN_TOP_OFFSET = 50
SAVE_BTN_LEFT, SAVE_BTN_W = 10, 80
LOAD_BTN_LEFT, LOAD_BTN_W = 100, 80
PANEL_W = 268
PANEL_H = 72
PANEL_INSET = 10
PALETTE_CELL_W = PALETTE_TILE_SIZE + PALETTE_TILE_PAD
PALETTE_CELL_H = PALETTE_TILE_SIZE + PALETTE_TILE_PAD
MAP_VIEW_W = SCREEN_W - PALETTE_W
MAP_VIEW_H = SCREEN_H - TOOLBAR_H
DEFAULT_TILE_SIZE = 40
DEFAULT_ROWS = 16
DEFAULT_COLS = 80
SCROLL_SPEED = 14
TILE_SIZE_MIN = 12
TILE_SIZE_MAX = 80
TILE_SIZE_STEP = 4
WHEEL_ZOOM_STEP = 4
PALETTE_ZOOM_MIN = 0.12
PALETTE_ZOOM_MAX = 6.0
COLOR_BG = (36, 40, 48)
COLOR_MAP_BG = (40, 44, 52)

_MAP_EDITOR_FILE = Path(__file__)

map_dir = get_map_dir()
os.makedirs(map_dir, exist_ok=True)


def _do_load(path: str, grid: list, flip_x_grid: list, default_cols: int):
    loaded = load_csv(path)
    if loaded is None:
        return None
    grid.clear()
    grid.extend(loaded)
    rows = len(grid)
    cols = len(grid[0]) if grid else default_cols
    loaded_flip = load_flip_csv(path)
    if loaded_flip is not None and len(loaded_flip) == rows and len(loaded_flip[0]) == cols:
        flip_x_grid.clear()
        flip_x_grid.extend(r[:] for r in loaded_flip)
    else:
        flip_x_grid.clear()
        flip_x_grid.extend([[False] * cols for _ in range(rows)])
    return rows, cols


def confirm_reset_canvas() -> bool:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    result = messagebox.askyesno("Confirm", "Reset current canvas?")
    root.destroy()
    return result


def _placeholder_pack_tile(gid: int, px: int, font: pygame.font.Font) -> pygame.Surface:
    s = pygame.Surface((px, px), pygame.SRCALPHA)
    s.fill((70, 74, 88, 255))
    pygame.draw.rect(s, (200, 200, 210), s.get_rect(), 2)
    t = font.render(str(gid), True, (230, 230, 240))
    s.blit(t, ((px - t.get_width()) // 2, (px - t.get_height()) // 2))
    return s


def main():
    draw_helper = DrawHelper(
        palette_w=PALETTE_W,
        map_view_w=MAP_VIEW_W,
        map_view_h=MAP_VIEW_H,
        toolbar_h=TOOLBAR_H,
        screen_h=SCREEN_H,
        btn_h=BTN_H,
        panel_w=PANEL_W,
        panel_h=PANEL_H,
        panel_inset=PANEL_INSET,
        palette_tile_size=PALETTE_TILE_SIZE,
        palette_cell_w=PALETTE_CELL_W,
        palette_cell_h=PALETTE_CELL_H,
        palette_left=PALETTE_LEFT,
        palette_top=PALETTE_TOP,
        palette_tiles_per_row=PALETTE_TILES_PER_ROW,
    )
    button_tester = ButtonTester(
        screen_h=SCREEN_H,
        btn_h=BTN_H,
        save_btn_left=SAVE_BTN_LEFT,
        save_btn_w=SAVE_BTN_W,
        load_btn_left=LOAD_BTN_LEFT,
        load_btn_w=LOAD_BTN_W,
        level_btn_left=LEVEL_BTN_LEFT,
        level_btn_w=LEVEL_BTN_W,
        level_btn_top_offset=LEVEL_BTN_TOP_OFFSET,
    )

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Map Editor - Left Paint / Right Clear")
    font = pygame.font.SysFont("arial", 14)
    font_header = pygame.font.SysFont("microsoftyahei", 13)

    pack_dirs = list_pack_dirs(_MAP_EDITOR_FILE)
    if not pack_dirs:
        na = new_assets_root(_MAP_EDITOR_FILE)
        pack_dirs = [na] if na.is_dir() else [_MAP_EDITOR_DIR]

    page_states: dict[int, PageState] = {}
    gid_surface_cache: dict[tuple[int, int], pygame.Surface] = {}
    # load_tile_set 每幀呼叫會重複讀檔與縮放，改為依 tile_size 快取一次
    base_tiles_by_size: dict[int, dict[int, pygame.Surface]] = {}

    def clear_gid_surface_cache() -> None:
        gid_surface_cache.clear()

    def base_tiles_for_size(sz: int) -> dict[int, pygame.Surface]:
        d = base_tiles_by_size.get(sz)
        if d is None:
            d = load_tile_set(sz)
            base_tiles_by_size[sz] = d
        return d

    def get_page_state(pi: int) -> PageState:
        pi = pi % len(pack_dirs)
        if pi not in page_states:
            page_states[pi] = load_page_state(pack_dirs[pi])
        return page_states[pi]

    def reset_page_view(st: PageState, vp_w: int, vp_h: int) -> tuple[float, float, float]:
        z = fit_zoom(st, vp_w, vp_h)
        return 0.0, 0.0, float(z)

    tile_size = DEFAULT_TILE_SIZE
    rows, cols = DEFAULT_ROWS, DEFAULT_COLS
    grid = [[-1 for _ in range(cols)] for _ in range(rows)]
    flip_x_grid = [[False for _ in range(cols)] for _ in range(rows)]
    page_index = 0
    palette_view_h = SCREEN_H - TOOLBAR_H - BTN_H - 50
    vp_h = palette_view_h - PALETTE_TOP
    vp_w = PALETTE_W - 4

    st0 = get_page_state(0)
    pal_pan_x, pal_pan_y, pal_zoom = reset_page_view(st0, vp_w, vp_h)
    selected_id = gid_for(0, 0)
    selected_flip_x = False
    scroll_x, scroll_y = 0, 0
    level = 1
    paint_armed = True

    running = True
    clock = pygame.time.Clock()
    while running:
        mx, my = pygame.mouse.get_pos()
        panel_rect = draw_helper.map_panel_rect()
        palette_vp = pygame.Rect(0, PALETTE_TOP, PALETTE_W, palette_view_h - PALETTE_TOP)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_LEFTBRACKET:
                    page_index = (page_index - 1) % len(pack_dirs)
                    st = get_page_state(page_index)
                    pal_pan_x, pal_pan_y, pal_zoom = reset_page_view(st, vp_w, vp_h)
                    selected_id = gid_for(page_index, 0)
                    clear_gid_surface_cache()
                elif event.key == pygame.K_RIGHTBRACKET:
                    page_index = (page_index + 1) % len(pack_dirs)
                    st = get_page_state(page_index)
                    pal_pan_x, pal_pan_y, pal_zoom = reset_page_view(st, vp_w, vp_h)
                    selected_id = gid_for(page_index, 0)
                    clear_gid_surface_cache()
                elif event.key == pygame.K_r:
                    if confirm_reset_canvas():
                        grid[:] = [[-1 for _ in range(cols)] for _ in range(rows)]
                        flip_x_grid[:] = [[False for _ in range(cols)] for _ in range(rows)]
                        print("Canvas reset")
                elif event.key == pygame.K_SPACE and not getattr(event, "repeat", False):
                    selected_flip_x = not selected_flip_x
                elif event.mod & pygame.KMOD_CTRL:
                    path = os.path.join(map_dir, f"level{level}.csv")
                    if event.key == pygame.K_s:
                        save_csv(path, grid, flip_x_grid)
                        print(f"Saved {path}")
                    elif event.key == pygame.K_l:
                        result = _do_load(path, grid, flip_x_grid, DEFAULT_COLS)
                        if result:
                            rows, cols = result
                            print(f"Loaded {path}")
                        else:
                            print(f"File not found: {path}")
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if mx < PALETTE_W:
                        if palette_vp.collidepoint(mx, my):
                            paint_armed = False
                            st = get_page_state(page_index)
                            lx = (mx - PALETTE_LEFT - pal_pan_x) / max(0.001, pal_zoom)
                            ly = (my - PALETTE_TOP - pal_pan_y) / max(0.001, pal_zoom)
                            col = int(lx // st.cell_px)
                            row = int(ly // st.cell_px)
                            if 0 <= col < st.ncols and 0 <= row < st.nrows:
                                idx = row * st.ncols + col
                                if idx < st.cell_count():
                                    selected_id = gid_for(page_index, idx)
                        elif button_tester.level_up_clicked(mx, my):
                            level = max(1, level + 1)
                        elif button_tester.level_down_clicked(mx, my):
                            level = max(1, level - 1)
                        elif button_tester.save_clicked(mx, my):
                            path = os.path.join(map_dir, f"level{level}.csv")
                            save_csv(path, grid, flip_x_grid)
                            print(f"Saved {path}")
                        elif button_tester.load_clicked(mx, my):
                            path = os.path.join(map_dir, f"level{level}.csv")
                            result = _do_load(path, grid, flip_x_grid, DEFAULT_COLS)
                            if result:
                                rows, cols = result
                                print(f"Loaded {path}")
                            else:
                                print(f"File not found: {path}")
                    elif draw_helper.in_map_control(mx, my, panel_rect):
                        if button_tester.cols_plus_clicked(mx, my, panel_rect):
                            cols += 1
                            for row in grid:
                                row.append(-1)
                            for row in flip_x_grid:
                                row.append(False)
                        elif button_tester.cols_plus10_clicked(mx, my, panel_rect):
                            cols += 10
                            for row in grid:
                                row.extend([-1] * 10)
                            for row in flip_x_grid:
                                row.extend([False] * 10)
                        elif button_tester.cols_minus_clicked(mx, my, panel_rect) and cols > 1:
                            cols -= 1
                            for row in grid:
                                row.pop()
                            for row in flip_x_grid:
                                row.pop()
                        elif button_tester.cols_minus10_clicked(mx, my, panel_rect) and cols > 1:
                            delta = min(10, cols - 1)
                            cols -= delta
                            for row in grid:
                                for _ in range(delta):
                                    row.pop()
                            for row in flip_x_grid:
                                for _ in range(delta):
                                    row.pop()
                        elif button_tester.rows_plus_clicked(mx, my, panel_rect):
                            rows += 1
                            grid.append([-1] * cols)
                            flip_x_grid.append([False] * cols)
                        elif button_tester.rows_minus_clicked(mx, my, panel_rect) and rows > 1:
                            rows -= 1
                            grid.pop()
                            flip_x_grid.pop()
                        elif button_tester.tile_size_plus_clicked(mx, my, panel_rect):
                            tile_size = min(TILE_SIZE_MAX, tile_size + TILE_SIZE_STEP)
                            clear_gid_surface_cache()
                            scroll_y = min(scroll_y, max(0, rows * tile_size - MAP_VIEW_H))
                        elif button_tester.tile_size_minus_clicked(mx, my, panel_rect):
                            tile_size = max(TILE_SIZE_MIN, tile_size - TILE_SIZE_STEP)
                            clear_gid_surface_cache()
                            scroll_y = min(scroll_y, max(0, rows * tile_size - MAP_VIEW_H))
                    else:
                        paint_armed = True
                        cell = draw_helper.get_cell_at_screen(mx, my, grid, tile_size, scroll_x, scroll_y, panel_rect)
                        if cell:
                            gx, gy = cell
                            grid[gy][gx] = selected_id
                            flip_x_grid[gy][gx] = selected_flip_x
            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    paint_armed = True
            if event.type == pygame.MOUSEMOTION:
                if event.buttons[1] and mx < PALETTE_W and palette_vp.collidepoint(mx, my):
                    pal_pan_x += event.rel[0]
                    pal_pan_y += event.rel[1]
                elif event.buttons[0] and paint_armed:
                    cell = draw_helper.get_cell_at_screen(mx, my, grid, tile_size, scroll_x, scroll_y, panel_rect)
                    if cell:
                        gx, gy = cell
                        grid[gy][gx] = selected_id
                        flip_x_grid[gy][gx] = selected_flip_x
                elif event.buttons[2] and mx >= PALETTE_W:
                    cell = draw_helper.get_cell_at_screen(mx, my, grid, tile_size, scroll_x, scroll_y, panel_rect)
                    if cell:
                        gx, gy = cell
                        grid[gy][gx] = -1
                        flip_x_grid[gy][gx] = False
            if event.type == pygame.MOUSEWHEEL:
                if mx < PALETTE_W and palette_vp.collidepoint(mx, my):
                    st = get_page_state(page_index)
                    old_z = pal_zoom
                    pal_zoom = float(
                        max(PALETTE_ZOOM_MIN, min(PALETTE_ZOOM_MAX, pal_zoom * (1.12 ** event.y)))
                    )
                    if old_z > 0.0001:
                        ax = (mx - PALETTE_LEFT - pal_pan_x) / old_z
                        ay = (my - PALETTE_TOP - pal_pan_y) / old_z
                        pal_pan_x = mx - PALETTE_LEFT - ax * pal_zoom
                        pal_pan_y = my - PALETTE_TOP - ay * pal_zoom
                elif mx >= PALETTE_W and my >= TOOLBAR_H and not draw_helper.in_map_control(mx, my, panel_rect):
                    if event.y > 0:
                        tile_size = min(TILE_SIZE_MAX, tile_size + WHEEL_ZOOM_STEP)
                        clear_gid_surface_cache()
                    elif event.y < 0:
                        tile_size = max(TILE_SIZE_MIN, tile_size - WHEEL_ZOOM_STEP)
                        clear_gid_surface_cache()
                    scroll_y = min(scroll_y, max(0, rows * tile_size - MAP_VIEW_H))

        max_scroll_y = max(0, rows * tile_size - MAP_VIEW_H)
        keys = pygame.key.get_pressed()
        ctrl_held = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
        if not ctrl_held:
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                scroll_x = max(0, scroll_x - SCROLL_SPEED)
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                scroll_x = min(max(0, cols * tile_size - MAP_VIEW_W), scroll_x + SCROLL_SPEED)
            if keys[pygame.K_UP] or keys[pygame.K_w]:
                scroll_y = max(0, scroll_y - SCROLL_SPEED)
            if keys[pygame.K_DOWN] or keys[pygame.K_s]:
                scroll_y = min(max_scroll_y, scroll_y + SCROLL_SPEED)
        scroll_y = min(scroll_y, max_scroll_y)

        tiles = dict(base_tiles_for_size(tile_size))
        for row in grid:
            for tid in row:
                if tid < 0 or tid in tiles:
                    continue
                rel = tid - KENNEY_TILE_BASE
                if rel < 0:
                    continue
                pg = rel // PACK_STRIDE
                loc = rel % PACK_STRIDE
                st = get_page_state(pg)
                if loc >= st.cell_count():
                    continue
                trow, tcol = divmod(loc, st.ncols)
                key = (tid, tile_size)
                if key not in gid_surface_cache:
                    gid_surface_cache[key] = extract_tile_surface(st, tcol, trow, tile_size)
                tiles[tid] = gid_surface_cache[key]

        screen.fill(COLOR_BG)
        st_cur = get_page_state(page_index)
        sw, sh = st_cur.surf.get_size()
        zw = max(1, int(sw * pal_zoom))
        zh = max(1, int(sh * pal_zoom))
        scaled = pygame.transform.scale(st_cur.surf, (zw, zh))
        screen.set_clip(palette_vp)
        screen.blit(scaled, (PALETTE_LEFT + pal_pan_x, PALETTE_TOP + pal_pan_y))
        rel_sel = selected_id - KENNEY_TILE_BASE
        cur_page = rel_sel // PACK_STRIDE
        loc_sel = rel_sel % PACK_STRIDE
        if cur_page == page_index % len(pack_dirs):
            sr, sc = divmod(loc_sel, st_cur.ncols)
            if 0 <= sr < st_cur.nrows and 0 <= sc < st_cur.ncols:
                sx = PALETTE_LEFT + pal_pan_x + sc * st_cur.cell_px * pal_zoom
                sy = PALETTE_TOP + pal_pan_y + sr * st_cur.cell_px * pal_zoom
                rw = st_cur.cell_px * pal_zoom
                pygame.draw.rect(screen, (255, 60, 60), (sx, sy, rw, rw), 2)
        screen.set_clip(None)

        pack = pack_dirs[page_index % len(pack_dirs)]
        hdr = f"{page_index + 1}/{len(pack_dirs)} {pack.name}"[:28]
        screen.blit(font_header.render(hdr, True, (220, 220, 230)), (PALETTE_LEFT, 6))
        hint2 = "滾輪縮放 中鍵拖移圖集"
        screen.blit(font_header.render(hint2, True, (170, 175, 190)), (PALETTE_LEFT, 22))
        draw_helper.draw_level_selector(screen, font, level)
        draw_helper.draw_save_load_buttons(screen, font)
        draw_helper.draw_toolbar_hint(screen, font)

        map_surf = pygame.Surface((MAP_VIEW_W, MAP_VIEW_H))
        map_surf.fill(COLOR_MAP_BG)
        draw_helper.draw_map_view(map_surf, grid, flip_x_grid, tiles, tile_size, scroll_x, scroll_y)
        screen.blit(map_surf, (PALETTE_W, TOOLBAR_H))
        draw_helper.draw_map_panel(screen, font, cols, rows, tile_size, panel_rect)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
