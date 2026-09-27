#!/usr/bin/env python3
"""Build a help-only Motorpedia client pak (debug/staging helper).

The normal ship path is the schedule-i CLIENT pak: create_cargopack.py picks
up `mods/schedule-i/help_articles.json` automatically and stages the patched
Helps DataTable. This standalone builder exists only to iterate on the
articles without a full cargo build.

Requires at repo root: Helps.uasset (+.uexp) extracted from the client pak,
the prebuilt UAssetTool binary, Mappings.usmap, and target/release/mod_pack.
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_DIR = os.path.join(ROOT, "mods", "schedule-i")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from help_articles import patch_helps, fail  # noqa: E402

MOD_VERSION = "0.1.0"
GAME_VERSION = "0.7.19"


def main():
    mod_pack = os.path.join(ROOT, "target", "release", "mod_pack")
    if not os.path.isfile(mod_pack):
        fail(f"mod_pack binary not found: {mod_pack}")

    work = os.path.join(MOD_DIR, "builds", "help_only_work")
    uasset, uexp = patch_helps(
        ROOT, os.path.join(MOD_DIR, "help_articles.json"), ".", work)

    staging = os.path.join(work, "pak_staging", "MotorTown", "Content",
                           "DataAsset")
    os.makedirs(staging, exist_ok=True)
    shutil.copy2(uasset, os.path.join(staging, "Helps.uasset"))
    shutil.copy2(uexp, os.path.join(staging, "Helps.uexp"))

    out_path = os.path.join(
        MOD_DIR, "builds",
        f"Schedule_I_Help_v{MOD_VERSION}_{GAME_VERSION}_CLIENT_P.pak")
    result = subprocess.run(
        [mod_pack, os.path.dirname(staging), out_path],
        capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode != 0:
        fail(f"mod_pack failed:\n{result.stderr}")
    print(f"\n=== Built {out_path} ({os.path.getsize(out_path):,} bytes) ===")


if __name__ == "__main__":
    main()
