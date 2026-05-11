# 方程式戰士 (Math Equation Warrior)

數學方程式作為彈道的 platformer 射擊遊戲。

## 跑遊戲

```powershell
cd 方程式戰士
python game.py
```

## 跑測試

```powershell
cd 方程式戰士
python -m unittest test_game.py -v
```

## 控制

| 操作 | 動作 |
|---|---|
| `A` / `D` | 左右移動 |
| `W` | 跳躍 |
| `Esc` | 回主選單 |
| **`1`** | 切到**函數圖形**；**按住 `1`** 瞄準，放開發射（需已在模式 1） |
| **`2`** | **微分塊**：左 1/3 內**左鍵**放置下落 `d/dx`（場上最多 5）；碰自己降次方、敵人定身、敵彈消失、與積分塊互消、碰到畫筆則塊與該筆清除 |
| **`3`** | **積分模式（3a+3b 合併）**：左鍵可先觸發 **∫x/∫y**（敵彈加長、畫筆轉面積體），若沒觸發且在左 1/3 區域則放置積分塊（最多 3） |
| **`4`** | **S 型**：游標旁顯示 `S`，左鍵點敵彈 → 綠色**治療彈**（量由 logistic 決定，見 `SIGMOID_*` 常數） |
| **`5`** | **Σ**：按住左鍵蓄力（每 **0.5 秒 +1**，上限 10）；放開發射 `0…n`。**僅 n=0 時**觸發彩蛋：連發 10 個 0（間隔 0.25s） |
| **`B`** | **畫筆**：僅左 1/3 內繪製，最多 3 色、總線段長度有上限 |
| 滑鼠滾輪 | 在積分模式切換 **∫x ↔ ∫y**；函數瞄準中仍不改拋物線參數 |

### 模式冷卻（離開後僅鎖該模式）

- 離開 **微分塊** / **積分塊**：**1s** 內不可再進入同一模式。  
- 離開 **S 型**：**10s**。離開 **Σ**：**15s**。

### 次方與彈道（目前實作）

| 次方 | 放開 `1` 時行為 |
|---:|---|
| 0 | 彩蛋：**僅「啵」**（`request_pop_sound` 計數），**無子彈** |
| 1 | 線性：方向指向滑鼠，vector 等速 |
| 2 | 拋物線：滑鼠 = 頂點 `(h,k)`，`a = -k/h²` |
| 3 | 尚未實作：短暫提示，不進入瞄準 |

預設進入關卡為次方 **1**。對戰中請用 **微分／積分塊碰自己** 調整次方；測試可呼叫 `player.apply_degree_delta(n)`。

## 平衡（規格向）

- 玩家最大血量 **`10.00`**（運算與顯示四捨五入至**小數第 2 位**）。
- 敵人子彈單發 **`EnemyBullet.DAMAGE = 100`**（捱一發即死，之後靠機制擴充生存）。

## 設計重點

### 函數作為彈道

按住 **`1`** → 螢幕出現**有限長度**預覽 → 放開 = 子彈沿曲線（或次方 0 僅音效）飛出。

### 線性與拋物線（由次方決定，不再用 `2` 鍵）

- **線性（次方 1）**：原點 = 玩家。**vector 運動** — 子彈速度 = 沿單位向量 `(dx, dy)/|·|` 每 frame 走 `SPEED_PX`。
  - 滑鼠正右 → 純水平；正上/下 → 真正垂直；任意角度 → 等速。
  - 顯示 `f(x) = ax`，垂直時顯示 `f(x): vertical`
- **拋物線（次方 2）**：**滑鼠位置 = 頂點 (h, k)**；`a = -k/h²`（曲線必過玩家）。
  - 滑鼠太靠近玩家垂直線 (`|h| < 5`) → `h` 被 clamp 避免 `a` 爆炸
  - **滾輪無用**：頂點 + 過玩家已唯一決定曲線

### 為什麼這樣設計

讓玩家覺得自己在「算」，而不是用視覺直接對位。預覽曲線只給一段，玩家要在腦中延伸函數來預測落點。

### 抗抖動

滑鼠位置會量化到 8px grid（`MOUSE_QUANTIZE = 8`），所以微小手抖不會讓顯示的數字 / 曲線跳。代價是曲線會「卡格子」更新，但比抖動好看。

## 檔案結構

```
方程式戰士/
├── game.py             entry point (薄殼，re-export core 給 test 用)
├── core/               核心模組
│   ├── __init__.py     統一 re-export
│   ├── constants.py    尺寸 / 物理 / 顏色
│   ├── enums.py        PowerType, AimState, GameState 等
│   ├── fonts.py        get_font (CJK 自動 fallback)
│   ├── assets.py       sprite 載入 + 幾何 fallback
│   ├── equation.py     純函式 f(x) (無 pygame，最易測)
│   ├── gameplay.py       血量、次方、放置區、Sigma 排程、Sigmoid 公式
│   ├── calculus_blocks.py  下落微分／積分塊
│   ├── brush.py          畫筆
│   ├── area_entity.py    面積體（擋彈、被推動）
│   ├── mode_cooldowns.py 模式冷卻
│   ├── interactions.py   ∫xy / Sigmoid 點擊
│   ├── projectile.py   MathProjectile + EnemyBullet + NumericProjectile
│   ├── controller.py   EquationController + EquationDisplay
│   ├── soldier.py      Soldier base + Player + Enemy
│   ├── world.py        World (csv) + HealthBox/Decoration/Water/Exit
│   ├── ui.py           HealthBar, TextButton, ScreenFade
│   └── main.py         主迴圈 + state machine + init_level
├── test_game.py        單元測試
├── level1_data.csv
├── level2_data.csv
├── README.md
└── assets/
    └── img/
        ├── player/{Idle,Run,Jump,Death}/
        ├── enemy/{Idle,Run,Jump,Death}/
        ├── tile/
        └── icons/
```

**依賴方向**（無循環）：  
`constants/enums` → `gameplay` → `equation` → `projectile` / `soldier` / `world` / `brush` / `calculus_blocks` / `area_entity` / `mode_cooldowns` / `interactions` / `ui` → `controller` → `main`

## CSV Tile 編碼

| ID | 含義 |
|---|---|
| `-1` 或空白 | 空（透明） |
| `0-8` | 牆 (dirt) |
| `9-10` | 水（碰到死） |
| `11-14` | 裝飾（不擋路） |
| `15` | 玩家出生點 |
| `16` | 敵人出生點 |
| `19` | 補血箱 (+30 HP) |
| `20` | 出口 |

## Sprite 資源 swap

把 `.png` 動畫幀放進 `assets/img/player/Idle/0.png, 1.png, ...` 等資料夾，遊戲會自動讀取並取代幾何 placeholder。**code 一個字不用改**。

## 未來擴充點

### 彈力球（Bouncy Ball）
`MathProjectile` 已預留 `on_wall_hit()` hook。未來新增 `BouncyMathProjectile(MathProjectile)` subclass，override `on_wall_hit()` 改為計算反射方向、不 `kill()`，即可實作彈力球。

```python
class BouncyMathProjectile(MathProjectile):
    BOUNCES = 3

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.bounces_left = self.BOUNCES

    def on_wall_hit(self):
        if self.bounces_left > 0:
            self.bounces_left -= 1
            self.facing *= -1
            self.origin = self.rect.center
            self.world_x = 0
        else:
            self.kill()
```

### 三次函數 (Cubic)
次方 **3** 時按 `1` 會提示 TODO；未來實作 `ax³` / `ax³-bx` 等形式。

## 已知限制

- 單一螢幕關卡（無 side-scrolling）
- 啵聲僅計數占位，尚未接 `pygame.mixer` 音檔
- 敵人 AI 簡單巡邏 + 視野發現開槍

## License

MIT
