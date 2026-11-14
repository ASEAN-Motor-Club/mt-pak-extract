#!/usr/bin/env python3
"""Fail the build when a source material's texture is not in the tree that is about to be packed.

Why this exists: nothing in the pipeline ever asked "does every material's colour map resolve to an
asset?". The compiler only looks *up* names — an unresolved map silently falls back to a sibling or
to nothing, so a material ships bound to its normal map (or to no map at all) and renders white.
That is how `mat_PA_siba_lord01` shipped with only a Normal override, and how the Shibaura bollards
shipped with no colour binding whatsoever. A material can be 100% correct in the source JSON and
still render wrong because its map never reached the pak.

What it checks: every `*Map` path in `merged.materials.json` (all stages) is mapped through the same
`texture_map()` transform the compiler uses, then resolved against the asset names in --textures the
same way the compiler resolves them (exact -> FName trailing-digit -> unique prefix).

Exit codes: 0 clean; 1 hard gap (a colour map has a source image but no asset); 2 only warnings
(sub-maps or colour maps with no source image at all — art was never exported, nothing to build).

Usage:
  check_texture_coverage.py --textures <dir|pak> [--materials c1/source/merged.materials.json]
                            [--srczip c1src.zip] [--json out.json] [--strict]
"""
import argparse
import collections
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile_materials import texture_map  # noqa: E402  (single source of truth for naming)
from verify_textures import stub_stems  # noqa: E402  (presence != pixel data)


def port_name(field, val):
    """Route a raw map path through the compiler's own transform (it takes entry+field)."""
    return texture_map({"Stages": [{field: val}]}, field)


COLOUR_FIELDS = ("colorMap", "baseColorMap", "diffuseMap")
EXTS = (".color.png", ".data.png", ".normal.png", ".dds", ".png")


def asset_names_from_dir(path):
    out = {}
    for root, _d, files in os.walk(path):
        for f in files:
            if f.endswith(".uasset"):
                out[f[:-7].lower()] = os.path.relpath(os.path.join(root, f[:-7]), path)
    return out


def asset_names_from_pak(path):
    import subprocess
    exe = os.environ.get("MOD_EXPLORE", "/opt/data/workspace/mt-pak-wt-c1commit/target/release/mod_explore")
    lst = subprocess.run([exe, path, "--list"], capture_output=True, text=True).stdout
    out = {}
    for line in lst.splitlines():
        line = line.strip()
        if not line.endswith(".uasset"):
            continue
        stem = line[: -len(".uasset")]
        out[os.path.basename(stem).lower()] = stem
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", default=None)
    ap.add_argument("--textures", required=True, help="cooked texture tree or base .pak")
    ap.add_argument("--srczip", default="", help="source zip, to tell 'not imported' from 'never exported'")
    ap.add_argument("--json", default="")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    a = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    matjson = a.materials or os.path.join(root, "source/merged.materials.json")
    mats = json.load(open(matjson))
    names = asset_names_from_pak(a.textures) if a.textures.endswith(".pak") else asset_names_from_dir(a.textures)
    keys = list(names)
    # An asset that exists by name but carries no pixel data renders as
    # checkerboard: that is a gap, not coverage (Base_v3 shipped 220 of these).
    stubs = stub_stems(a.textures)

    def resolve(n):
        if n in names:
            return "exact"
        c = [k for k in keys if k.startswith(n) and k[len(n):].isdigit()]
        if len(c) == 1:
            return "fname"
        c = [k for k in keys if k.startswith(n)]
        return "prefix" if len(c) == 1 else None

    zsrc = collections.defaultdict(list)
    if a.srczip and os.path.exists(a.srczip):
        z = zipfile.ZipFile(a.srczip)
        for e in z.namelist():
            if e.lower().endswith(EXTS):
                zsrc[port_name("colorMap", e)].append(e)

    want = collections.defaultdict(lambda: {"mats": set(), "fields": set()})
    for name, m in mats.items():
        for stage in (m.get("Stages") or []):
            if not isinstance(stage, dict):
                continue
            for field, val in stage.items():
                if field.endswith("Map") and isinstance(val, str) and val:
                    tn = port_name(field, val)
                    if tn:
                        want[tn]["mats"].add(name)
                        want[tn]["fields"].add(field)

    tiers = collections.Counter()
    gaps = []
    for tn, info in sorted(want.items()):
        how = resolve(tn)
        empty = tn in stubs
        if how and not empty:
            tiers[how] += 1
            continue
        tiers["EMPTY" if empty else "UNRESOLVED"] += 1
        is_colour = bool({"colorMap", "baseColorMap", "diffuseMap"} & info["fields"])
        cands = zsrc.get(tn, [])
        gaps.append({
            "texture": tn, "colour": is_colour, "empty": empty,
            "fields": sorted(info["fields"]),
            "materials": sorted(info["mats"]), "source": cands[:3],
        })

    # An empty texture is hard even without a source zip: the asset is in the
    # tree but renders as the engine checkerboard.
    hard = [g for g in gaps if g["colour"] and (g["source"] or g["empty"])]
    warn = [g for g in gaps if g not in hard]

    print("textures requested by source materials:", len(want))
    for k, v in tiers.most_common():
        print("   %-11s %5d" % (k, v))
    print("gaps:", len(gaps), "| hard (colour map exists upstream but not in tree):", len(hard),
          "| warnings:", len(warn))
    for g in hard:
        print("   HARD %-44s%s fields=%s src=%s" % (
            g["texture"], " EMPTY-ASSET" if g.get("empty") else "",
            ",".join(g["fields"]), g["source"][0] if g["source"] else "-"))
    for g in warn[:20]:
        print("   warn %-44s fields=%-22s src=%s" % (
            g["texture"], ",".join(g["fields"]), "yes" if g["source"] else "none exported"))
    if len(warn) > 20:
        print("   ... %d more warnings" % (len(warn) - 20))

    if a.json:
        json.dump(gaps, open(a.json, "w"), indent=1)
    if hard or (a.strict and warn):
        print("FAIL: texture coverage incomplete")
        return 1
    if warn:
        print("WARN: sub-maps missing (does not fail; see --strict)")
        return 2
    print("OK: every source material texture resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
