# 方程式戰士 — Agent 備忘

## 每次改完程式

1. **刪除**：拿掉重構後不再使用的 import、常數、變數、函式與分支；避免「少算一個變數卻仍被引用」類錯誤。
2. **檢查**：對改過的檔案看診斷；執行 `python -m unittest discover -v`（含 `TestCoreModulesCompile` 對 `core/` 語法編譯）。
3. 詳細步驟見專案 skill：`.cursor/skills/post-edit-verify/SKILL.md`。
