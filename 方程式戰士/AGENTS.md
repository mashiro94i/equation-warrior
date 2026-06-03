# 方程式戰士 — Agent 備忘

## 文件（改版請同步）

| 檔案 | 用途 |
|------|------|
| [README.md](./README.md) | 執行、操作表、版本重點、GID 摘要 |
| [核心玩法.md](./核心玩法.md) | 核心機制概念（微積分語意、面積、敵人概覽） |
| [具體遊戲玩法.md](./具體遊戲玩法.md) | 玩法、關卡模式、機關、音效（v1.2） |
| [enemy.md](./enemy.md) | 各怪物 GID、AI、代數與數值 |

## 每次改完程式

1. **刪除**：拿掉重構後不再使用的 import、常數、變數、函式與分支；避免「少算一個變數卻仍被引用」類錯誤。
2. **檢查**：對改過的檔案看診斷；執行 `python -m unittest discover -v`（含 `TestCoreModulesCompile` 對 `core/` 語法編譯）。
3. 詳細步驟見專案 skill：`.cursor/skills/post-edit-verify/SKILL.md`。
