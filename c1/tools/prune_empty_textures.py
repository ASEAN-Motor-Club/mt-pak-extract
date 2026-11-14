#!/usr/bin/env python3
"""Remove empty, unreferenced Texture2D stubs from a client tree.

Base_v3 shipped 220 data-less textures. 67 of them are orphans: 66 `*_ao_data`
masks plus `T_UVTest`, none of which appear anywhere in `merged.materials.json`
and none of which have a source DDS. They exist only because an old texture tree
was packed wholesale.

Deleting them is the fix, not re-importing them. This tool makes that automatic:
for every data-less Texture2D in the tree it checks whether any material
references the name; unreferenced stubs are deleted, referenced ones are
reported and fail the run (they need real pixel data, which is a build defect,
not something to paper over).

Usage:
    prune_empty_textures.py <tree-or-pak> [--materials merged.materials.json]
                            [--dry-run] [--keep AO_MASK_PREFIX ...]

Exit: 0 when nothing referenced is empty (tree may have had orphans pruned),
      1 when a referenced texture has no pixel data, 2 on usage/IO error.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_textures import classify, unpack  # noqa: E402


def default_materials() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "source", "merged.materials.json")


def referenced_names(mat_path: str):
    """Every texture-ish token the material set mentions, lowercased."""
    if not os.path.exists(mat_path):
        sys.exit(f"FAIL: material set not found: {mat_path}")
    with open(mat_path, "r", encoding="utf-8") as fh:
        blob = fh.read()
    refs = set()
    for tok in blob.replace('"', " ").replace(",", " ").replace("/", " ").split():
        t = tok.strip().lower()
        if t and (t.startswith("mat_") or t.startswith("t_") or t.startswith("building")
                  or t.startswith("area_") or t.startswith("lamp") or t.startswith("pole")
                  or t.startswith("wire") or t.startswith("station") or t.startswith("housing")):
            refs.add(t)
    return refs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="client tree directory or .pak")
    ap.add_argument("--materials", default=default_materials())
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", action="append", default=[],
                    help="asset stem to keep even when unreferenced (repeatable)")
    args = ap.parse_args()

    tmp = None
    if os.path.isdir(args.target):
        root, pak, cleanup = args.target, None, False
    elif args.target.endswith(".pak"):
        tmp = tempfile.mkdtemp(prefix="prune-")
        unpack(args.target, tmp)
        root, pak, cleanup = tmp, args.target, True
    else:
        print("FAIL: target is neither a directory nor a .pak", file=sys.stderr)
        return 2

    try:
        refs = referenced_names(args.materials)
        keep = {k.lower() for k in args.keep}

        stubs = []
        for dirpath, _dirnames, files in os.walk(root):
            for name in files:
                if not name.endswith(".uasset"):
                    continue
                base = name[: -len(".uasset")]
                uexp = os.path.join(dirpath, base + ".uexp")
                if not os.path.exists(uexp):
                    continue
                _is_tex, stub = classify(os.path.join(dirpath, name), uexp)
                if stub:
                    stubs.append(os.path.join(dirpath, base))

        orphans, live = [], []
        for stem in stubs:
            n = os.path.basename(stem).lower()
            (live if (n in refs or n in keep) else orphans).append(stem)

        for stem in orphans:
            print(f"  prune orphan {os.path.basename(stem)}")
            if args.dry_run:
                continue
            for ext in (".uasset", ".uexp", ".ubulk"):
                p = stem + ext
                if os.path.exists(p):
                    os.remove(p)
            parent = os.path.dirname(stem)
            while True:                                  # drop empty texture dirs
                try:
                    if os.listdir(parent):
                        break
                except FileNotFoundError:
                    break
                if os.path.abspath(parent) == os.path.abspath(root):
                    break
                shutil.rmtree(parent, ignore_errors=True)
                parent = os.path.dirname(parent)

        print(f"textures: {len(stubs)} data-less | {len(orphans)} orphan(s) pruned"
              f"{' (dry run)' if args.dry_run else ''} | {len(live)} referenced")
        for stem in live:
            print(f"  FAIL referenced but empty: {os.path.basename(stem)}")

        if pak and cleanup and orphans and not args.dry_run:
            print("NOTE .pak input cannot be edited in place — repack from the pruned tree")
        return 1 if live else 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
