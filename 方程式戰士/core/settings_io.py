"""讀寫使用者設定（JSON）。"""
from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"

DEFAULTS = {
    "bgm_volume": 0.5,
    "sfx_volume": 0.5,
    "resolution": [1600, 900],
}


def load_settings() -> dict:
    data = dict(DEFAULTS)
    if not _SETTINGS_PATH.is_file():
        return data
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data.update(raw)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return data


def save_settings(data: dict) -> None:
    out = dict(DEFAULTS)
    out.update(data)
    try:
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
