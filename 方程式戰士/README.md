# 方程式戰士（Math Equation Warrior）

**v1.0** — 以數學函數彈道、微積分道具、畫筆與面積體為核心的 2D 平台射擊遊戲（Pygame）。邏輯目標關卡內滾動、左側固定視角、多模式與冷卻並存。

---

## 環境與執行

- **Python 3** + **Pygame**（專案開發時約 2.6.x）
- 建議在專案根目錄執行：

```powershell
cd 方程式戰士
python game.py
```

- 單元測試：

```powershell
cd 方程式戰士
python -m unittest discover -v
```

---

## 操作總覽

| 按鍵／操作 | 功能 |
|-----------|------|
| `A` / `D` | 左右移動 |
| `W` | 跳躍 |
| `1` | **函數模式**：按住瞄準、放開發射（次方 0 僅啵聲無彈） |
| `2` | **微分塊模式**：在可放置區內左鍵放置 `d/dx` 塊 |
| `3` | **積分模式**：左鍵優先對敵彈／畫筆做 **∫x/∫y**；否則在區內放置積分塊；**滾輪**切換 ∫x ↔ ∫y |
| `4` | **Sigmoid（S）**：游標附近持續嘗試把敵彈變治療彈 |
| `5` | **Sigma（Σ）**：按住左鍵蓄力，放開依排程發射數字彈 |
| `B` | **畫筆**；**450ms 內再按一次 `B`** → **面積拖曳模式** |
| `Esc` | 遊戲中：暫停（含設定／解析度／音量）；選單內：依頁面返回 |

暫停時可調解析度與 BGM／音效；全螢幕以 **letterbox** 維持 1600×900 邏輯座標比例。

更細的規則、互動表、彩蛋與已知問題請見 **[具體遊戲玩法.md](./具體遊戲玩法.md)**。

---

## 版本重點（v1.0）

- **邏輯解析度** `1600×900`，關卡與 UI 以此座標運算；顯示可全螢幕縮放。
- **鏡頭**：玩家水平錨在約螢幕 **1/4** 寬處，世界隨位移捲動（`shift_world`）。
- **可放置區**：畫面左側 **2/3 寬**、全高（微分塊、積分塊、畫筆高亮顯示）。
- **函數次方** `0～3`：僅能靠微分／積分塊碰自機升降；**三次**尚未實作發射。
- **面積體**：mask 碰撞、擋敵彈、滑行傷害、與積分／微分互動、拖曳模式等（見玩法文件）。
- **已修**：多項移動抖動、面積上／下緣對齊、卡地圖 depenetration、積分強化子彈穿透敵人等（詳見玩法文件「已修復」）。

---

## 專案結構

```
方程式戰士/
├── game.py                 # 進入點：pygame.init → core.main.main()
├── core/
│   ├── main.py             # 主迴圈、狀態機、關卡、輸入、UI
│   ├── constants.py        # 數值與畫面常數
│   ├── enums.py            # GameState、PlayerMode、PowerType…
│   ├── soldier.py          # 玩家／敵人物理與碰撞
│   ├── projectile.py       # 我方數學彈、敵彈、Sigma 數字彈
│   ├── controller.py       # 函數瞄準與預覽
│   ├── equation.py         # f(x) 純運算
│   ├── gameplay.py         # 放置區、Sigma 排程、血量工具
│   ├── world.py            # CSV 關卡
│   ├── map_tile_loader.py  # 數字圖塊 PNG（assets/img/tile/）與 Kenney 佔位
│   ├── calculus_blocks.py  # 微分／積分塊
│   ├── brush.py            # 畫筆
│   ├── area_entity.py      # 面積體
│   ├── interactions.py     # ∫xy 點選、Sigmoid 點敵彈
│   ├── mode_cooldowns.py   # 模式離開冷卻
│   ├── ui.py               # 血條、按鈕、淡入淡出
│   ├── assets.py / fonts.py
│   └── …
├── map/                    # 關卡 CSV 備援（優先讀取同層 `map_editor/map/`）
├── test_game.py
├── README.md
├── 具體遊戲玩法.md
└── 遊戲特性.txt            # 彩蛋速記（詳見玩法文件）
```

- **地圖**：預設讀 `../map_editor/map/level{N}.csv`；若無則用本專案 `map/`。
- **玩家外觀**：`kenny_assets/kenney_tiny-dungeon/Tiles/tile_0084.png`（巫師）；若無則用 `assets/img/player/` 或幾何 fallback。
- **尺寸調整**（`core/constants.py`）：`TILE_SIZE_USER`（`None` = 螢幕高÷`ROWS`；或填像素如 `56`）、`PLAYER_VISUAL_SCALE`、`ENEMY_VISUAL_SCALE`。
- 其他可選 PNG：`assets/img/enemy/…` 等。

---

## CSV 圖塊編碼（關卡）

| 值 | 說明 |
|----|------|
| `-1` 或空白 | 空 |
| `0–8` | 實心障礙 |
| `9–10` | 水（碰到即死） |
| `11–14` | 裝飾（不碰撞） |
| `15` | 玩家出生 |
| `16` | 敵人生成 |
| `17`–`18` | 保留編號（目前關卡未使用） |
| `19` | 補血箱 |
| `20` | 出口 |
| `≥256`（未列於下表） | 灰色佔位障礙 |
| **66043** | 出生／重生點（死亡後在此復活） |
| **65834、65840、131449、131448** | 敵人生成 |
| **65850、65875** | 牆（實心） |
| **65935** | 地刺（伸出時踩住持續扣血） |
| **65904** | 愛心（拾取回復 **1/3** 最大血量） |
| **65931** | 地刺機關（碰一下收回地刺，再碰伸出） |

語意定義見 `core/tile_types.py`。可選 PNG：`assets/img/tile/<編號>.png`。

---

## 授權

MIT
