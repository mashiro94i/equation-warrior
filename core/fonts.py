"""字體載入：自動找系統 CJK 字體 + cache"""
import pygame

# Windows 內建 CJK 字體 priority chain，最後 fallback Arial
_CJK_FONT_CHAIN = (
    "Microsoft JhengHei",   # 微軟正黑體 (繁中)
    "Microsoft YaHei",      # 微軟雅黑 (簡中)
    "DengXian",             # 等線
    "PMingLiU",             # 新細明體
    "MingLiU",              # 細明體
    "SimHei",               # 黑體
    "Arial Unicode MS",
)
_FONT_CACHE = {}


def get_font(size, bold=True):
    """回傳支援中文的 Font 物件 (用過會 cache)"""
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    font = None
    for name in _CJK_FONT_CHAIN:
        path = pygame.font.match_font(name)
        if path:
            font = pygame.font.Font(path, size)
            font.set_bold(bold)
            break
    if font is None:
        font = pygame.font.SysFont("arial", size, bold=bold)
    _FONT_CACHE[key] = font
    return font
