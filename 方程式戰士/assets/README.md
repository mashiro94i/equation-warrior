# 方程式戰士 — 資源目錄

執行期**只讀**本目錄；Kenney 敵人／地圖大 GID 來自 workspace 同層 `kenny_assets/`。

## 目錄結構

```
assets/
├── audio/                 音效、BGM
│   ├── bgm/
│   ├── monster_attack/
│   └── player_take_damage/
├── background/            視差背景 PNG
└── img/
    ├── player/scientist/  玩家動畫（Idle、Run、Cast、Jump、Death、Hurt、projectile）
    ├── tile/              磚覆寫（有檔案才建立；<GID>.png 或 obstacle.png 等）
    └── ui/                  游標 PNG
```

## 不在 assets 內的資源

| 位置 | 用途 |
|------|------|
| `tools/scientist_pipeline/` | 科學家素材生成管線（raw-sheet、GIF、meta；非執行期） |
| `../kenny_assets/` | Kenney 原始包（敵人、地圖格 GID） |
| `../map_editor/map/` | 關卡 CSV 主檔（存檔時同步至 `方程式戰士/map/`） |
| `map/` | 關卡 CSV 鏡像（與編輯器同步） |

## 路徑解析

- `core/paths.py` — 根目錄常數
- `core/assets.py` — 玩家、UI、語意磚
- `core/map_tile_loader.py` — CSV 格 `img/tile/<id>.png`
- `core/kenney/` — Kenney GID 貼圖

## 地圖

在 map_editor 按 **Save** 會同時寫入：

1. `map_editor/map/level{N}.csv` + `level{N}_flip.csv`
2. `方程式戰士/map/`（同名鏡像）

主遊戲讀檔優先 `map_editor/map/`，其次 `方程式戰士/map/`。

一次性同步既有地圖：

```bash
python -c "import sys; sys.path.insert(0, 'map_editor'); from map_io import sync_all_maps_to_game; print(sync_all_maps_to_game())"
```
