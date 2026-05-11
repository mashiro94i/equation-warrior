"""方程式戰士 entry point

實作拆分到 core/ 子套件。本檔案：
  1. 啟動 pygame
  2. 從 core re-export 全部 public symbol (向後相容 test_game.py)
  3. __main__ 跑 main()
"""
import pygame
pygame.init()

from core import *  # noqa: E402, F401, F403
from core.main import main  # noqa: E402


if __name__ == "__main__":
    main()
