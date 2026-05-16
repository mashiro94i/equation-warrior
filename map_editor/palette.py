"""
Palette: left-side tile strip. Palette(...) receives only the params it needs in __init__.
"""
import pygame


class PaletteTile:
    """Single tile in the palette; reports its index when clicked."""

    __slots__ = ("idx", "rect")

    def __init__(self, idx: int, tile_size: int):
        self.idx = idx
        self.rect = pygame.Rect(0, 0, tile_size, tile_size)

    def update_rect(self, scroll: int, cell_w: int, cell_h: int, left: int, top: int, tiles_per_row: int) -> None:
        col = self.idx % tiles_per_row
        row = self.idx // tiles_per_row
        self.rect.x = left + col * cell_w
        self.rect.y = top + row * cell_h - scroll

    def contains(self, mx: int, my: int) -> bool:
        return self.rect.collidepoint(mx, my)

    def if_clicked_return_idx(
        self,
        mx: int,
        my: int,
        scroll: int,
        cell_w: int,
        cell_h: int,
        left: int,
        top: int,
        tiles_per_row: int,
    ) -> int | None:
        self.update_rect(scroll, cell_w, cell_h, left, top, tiles_per_row)
        return self.idx if self.contains(mx, my) else None


class Palette:
    """Left palette strip. Params set in __init__, no config object."""

    def __init__(
        self,
        palette_tile_size: int,
        palette_cell_w: int,
        palette_cell_h: int,
        palette_left: int,
        palette_top: int,
        palette_tiles_per_row: int,
    ):
        self._palette_tile_size = palette_tile_size
        self._palette_cell_w = palette_cell_w
        self._palette_cell_h = palette_cell_h
        self._palette_left = palette_left
        self._palette_top = palette_top
        self._palette_tiles_per_row = palette_tiles_per_row

    def create_tiles(self, count: int) -> list[PaletteTile]:
        return [PaletteTile(i, self._palette_tile_size) for i in range(count)]

    def get_index_at(
        self,
        mx: int,
        my: int,
        palette_tile_instances: list[PaletteTile],
        palette_scroll: int,
    ) -> int | None:
        for tile in palette_tile_instances:
            idx = tile.if_clicked_return_idx(
                mx, my, palette_scroll,
                self._palette_cell_w, self._palette_cell_h,
                self._palette_left, self._palette_top,
                self._palette_tiles_per_row,
            )
            if idx is not None:
                return idx
        return None
