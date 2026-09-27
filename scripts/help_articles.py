#!/usr/bin/env python3
"""Shared Motorpedia (Helps DataTable) article patching.

Adds new rows to the vanilla `DataAsset/Helps` DataTable (the Motorpedia
article index). Article bodies are written as culture-invariant FText
(UAssetTool patch `set` writes TextPropertyData as HistoryType.Base with an
empty namespace) - no StringTable changes, no locres changes.

Used by create_cargopack.py (stages Helps into the cargo CLIENT pak when
`mods/<mod>/help_articles.json` exists) and by create_helppack.py
(help-only pak).

Inputs (worktree root, gitignored / prepared by the extraction pipeline):
  <template_root>/Helps.uasset(+.uexp) - vanilla client-pak DataTable
Config: mods/<mod>/help_articles.json  [{id, title, description}]
"""

import json
import os
import shutil
import subprocess

UASSET_TOOL_REL = os.path.join(
    "csharp", "UAssetTool", "bin", "Release", "net8.0", "UAssetTool")
TEMPLATE_ROW_MATCH = {"RowName": "Housing"}


def fail(msg: str):
    raise RuntimeError(msg)


def patch_helps(repo_root: str, articles_path: str, template_root: str,
                work_dir: str) -> tuple[str, str]:
    """Patch the vanilla Helps DataTable with the configured articles.

    Returns (patched_uasset, patched_uexp) absolute paths inside work_dir.
    """
    articles = json.load(open(articles_path))
    if not articles:
        fail(f"no articles in {articles_path}")

    uat = os.path.join(repo_root, UASSET_TOOL_REL)
    if not os.path.isfile(uat):
        fail(f"UAssetTool binary not found: {uat}")
    template = os.path.join(repo_root, template_root, "Helps.uasset")
    if not os.path.isfile(template):
        fail(f"vanilla Helps.uasset not found: {template} (extract with "
             f"mt-pak-extract --get MotorTown/Content/DataAsset/Helps into "
             f"{template_root})")

    rows = []
    for a in articles:
        body = a["description"].replace("\n", "\r\n")
        rows.append({
            "row_name": a["id"],
            "patches": [
                {"op": "set", "path": "Title", "value": a["title"]},
                {"op": "set", "path": "Description", "value": body},
            ],
        })
    config = {
        "template_row_match": TEMPLATE_ROW_MATCH,
        "rows": rows,
        "output_filename": "Helps",
    }

    shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir)
    cfg_path = os.path.join(work_dir, "help_add_rows.json")
    with open(cfg_path, "w") as f:
        json.dump(config, f, indent=2)

    # UAssetTool resolves RootDir (→ Mappings.usmap) as CWD/../.., so run
    # from two levels under the repo root and use absolute paths.
    cwd = os.path.dirname(articles_path)
    result = subprocess.run(
        [uat, "--add-rows", cfg_path, template, work_dir],
        capture_output=True, text=True, cwd=cwd)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        fail(f"UAssetTool --add-rows failed:\n{result.stderr}")

    uasset = os.path.join(work_dir, "Helps.uasset.uasset")
    uexp = os.path.join(work_dir, "Helps.uasset.uexp")
    if not os.path.isfile(uasset):
        uasset = os.path.join(work_dir, "Helps.uasset")
        uexp = os.path.join(work_dir, "Helps.uexp")
    for p in (uasset, uexp):
        if not os.path.isfile(p):
            fail(f"expected output missing: {p}")

    # Round-trip check: every new row name in the name table, every body in
    # the .uexp, vanilla keys intact.
    uasset_bytes = open(uasset, "rb").read()
    uexp_bytes = open(uexp, "rb").read()
    for a in articles:
        if a["id"].encode() not in uasset_bytes:
            fail(f"row name {a['id']} missing from patched .uasset")
        probe = a["description"].split("\r\n")[0].split("\n")[0][:24]
        if probe.encode() not in uexp_bytes:
            fail(f"body text missing for {a['id']} (probe: {probe!r})")
    for key in (b"Housing_Title", b"CargoPaymentScaling",
                b"SupplyAndDemand_Title"):
        if key not in uexp_bytes:
            fail(f"vanilla key {key} missing after patch - template wrong?")
    print(f"help round-trip OK: {len(articles)} articles, vanilla keys intact")
    return uasset, uexp


def stage_helps(repo_root: str, articles_path: str, template_root: str,
                staging_dir: str) -> None:
    """Patch Helps and stage it under <staging>/MotorTown/Content/DataAsset."""
    work = os.path.join(os.path.dirname(staging_dir.rstrip("/")) or ".",
                        "help_work")
    uasset, uexp = patch_helps(repo_root, articles_path, template_root, work)
    dest = os.path.join(staging_dir, "MotorTown", "Content", "DataAsset")
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(uasset, os.path.join(dest, "Helps.uasset"))
    shutil.copy2(uexp, os.path.join(dest, "Helps.uexp"))
    print("staged: DataAsset/Helps.uasset (+.uexp) with Motorpedia articles")
