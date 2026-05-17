"""方程式戰士 entry point

實作拆分到 core/ 子套件。本檔案：
  1. 啟動 pygame
  2. 從 core re-export 全部 public symbol (向後相容 test_game.py)
  3. __main__ 跑 main()
"""
import pygame

if __name__ == "__main__":
    pygame.init()
    from core.main import main

    main()
else:
    pygame.init()
    from core import *  # noqa: E402, F401, F403
    from core.main import main  # noqa: E402
