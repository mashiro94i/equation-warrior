# Scientist 玩家精靈（側向卷軸）

橫向平台遊戲用科學家角色：白袍、眼鏡、投擲藥瓶。美術產出自 `generate2dsprite` 流程（Cursor 生圖 + `tools/generate2dsprite.py process`）。

## 交付影格

| 資料夾 | 檔案 | 格數 | 建議 cooldown (ms) |
|--------|------|------|-------------------|
| `Idle/` | `00.png`–`03.png` | 4 | 100（與引擎 `animation_cooldown` 相同） |
| `Run/` | `00`–`03` | 4 | 100 |
| `Cast/` | `00`–`05` | 6 | 80（瞄準／投擲） |
| `Jump/` | `00`–`03` | 4 | 100 |
| `Hurt/` | `00`–`03` | 4 | 80（單次播放） |
| `Death/` | `00`–`05` | 6 | 45（`death_animation_cooldown`） |
| `projectile/` | `00`–`03` | 4 | 120（彈幕自訂） |

## 除錯／原始產物

- `_pipeline/<Action>/`：`raw-sheet.png`、`sheet-transparent.png`、`animation.gif`、`pipeline-meta.json`
- `_pipeline/references/`：科學家與藥瓶參考圖
- `_pipeline/identity-lock.txt`：角色鎖定說明

## 遊戲接入（已實作）

- `core/assets.py`：存在 `player/scientist/Idle/` 時優先載入科學家圖（略過 Kenney 單格覆寫）
- `core/enums.py`：`ActionTypes.CAST`；瞄準時 `main.py` 切換 Cast 動畫
- `core/soldier.py`：Jump 僅兩格——`00`=`jump-1` 落地（`vel_y >= 0`）、`01`=`jump-2` 空中（`vel_y < 0`）
- `core/projectile.py`：方程式子彈使用 `projectile/03`、`04`（已刪 `projectile-1`）

## 重新產生

```powershell
Set-Location 方程式戰士
python tools/process_scientist_batch.py
python tools/rename_scientist_frames.py
```

替換 Cursor 產出的 raw 圖後，只重跑對應 `_pipeline` 子目錄的 `generate2dsprite.py process` 即可。

## QC 備註

- `Death` 第一版 `--reject-edge-touch` 曾報 `[0,2]` 觸邊，已改為寬鬆處理完成輸出；若遊戲內裁切異常可重生成 death raw 再 process。
- **v3（風格統一）**：`Idle` / `Cast` / `Jump` 已依 `Hurt`/`Death` 影格重新生圖（膚色 tan、眼鏡白片無瞳孔）。`Run` / `projectile` 未改。
- **v4（切格修正）**：`Idle` / `Jump` 的 raw 為 **1×4 橫列**，不可當 2×2 切；已用 `tools/reprocess_scientist_strip.py`（全體 `getbbox` + 統一身高 + 腳底對齊）。`Hurt` / `projectile` 已刪除錯誤的 `*-2.png` 並重產 GIF（各 3 格）。
- **Run v4（重畫）**：依 Hurt/Idle 風格新生 `scientist-run-raw-v4` → 1×4 切格 → `Run/00`–`03`（不再複製 Idle、不用舊洋紅線稿 raw）。
