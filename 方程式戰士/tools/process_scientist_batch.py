#!/usr/bin/env python3
"""Batch process all scientist raw sheets into _pipeline folders."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GAME_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = GAME_ROOT / "tools" / "generate2dsprite.py"
PIPELINE = GAME_ROOT / "assets" / "img" / "player" / "scientist" / "_pipeline"
ASSETS = Path(
    r"C:\Users\O0mashiro0O\.cursor\projects\c-Users-O0mashiro0O-OneDrive-Desktop-code-Python\assets"
)

# folder, mode, raw, custom (rows,cols,prefix) or None, component, align
JOBS: list[tuple] = [
    ("Idle", "idle", ASSETS / "scientist-idle-raw-v2.png", None, "largest", "feet"),
    ("Run", "run", ASSETS / "scientist-run-raw-v2.png", None, "largest", "feet"),
    ("Cast", "cast", ASSETS / "scientist-cast-raw.png", None, "largest", "feet"),
    ("Jump", "idle", ASSETS / "scientist-jump-raw.png", (2, 2, "jump"), "largest", "feet"),
    ("Hurt", "hurt", ASSETS / "scientist-hurt-raw.png", None, "largest", "feet"),
    ("Death", "death", ASSETS / "scientist-death-raw.png", None, "largest", "feet"),
    (
        "projectile",
        "projectile",
        ASSETS / "scientist-potion-raw.png",
        (2, 2, "projectile"),
        "all",
        "center",
    ),
]


def run_job(folder: str, mode: str, raw: Path, custom, component: str, align: str) -> int:
    out = PIPELINE / folder
    out.mkdir(parents=True, exist_ok=True)
    if not raw.is_file():
        print(f"MISSING {raw}", file=sys.stderr)
        return 1
    cmd = [
        sys.executable,
        str(SCRIPT),
        "process",
        "--input",
        str(raw),
        "--target",
        "asset",
        "--mode",
        mode,
        "--output-dir",
        str(out),
        "--cell-size",
        "128",
        "--component-mode",
        component,
        "--shared-scale",
        "--align",
        align,
        "--fit-scale",
        "0.85",
    ]
    if custom:
        rows, cols, prefix = custom
        cmd.extend(["--rows", str(rows), "--cols", str(cols), "--label-prefix", prefix])
    if folder == "projectile":
        pass  # custom already sets 2x2
    for attempt, extra in enumerate([["--reject-edge-touch"], []], start=1):
        full = cmd + extra
        print(" ".join(full))
        r = subprocess.run(full, cwd=str(GAME_ROOT))
        if r.returncode == 0:
            return 0
        print(f"attempt {attempt} failed for {folder}")
    return 1


def main() -> int:
    code = 0
    for job in JOBS:
        if run_job(*job) != 0:
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
