#!/usr/bin/env python3
"""Restore source non-opaque materials, then apply canonical two-sided flags.

The emissive rollout correctly changed opaque instances, but it also replaced some
masked/translucent instances with an opaque emissive parent. Restore every changed
non-opaque row from the compiled Base_v3 instances (which carry the canonical parent,
blend mode and alpha clip), then run UAssetTool --set-sidedness over the full set.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import shutil
import subprocess


def paired_sha(stem: str) -> str:
    h = hashlib.sha256()
    for ext in (".uasset", ".uexp"):
        path = stem + ext
        if os.path.exists(path):
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="c1/out/materials_plan_effective.json")
    ap.add_argument("--base", required=True, help="compiled Base_v3 Materials directory")
    ap.add_argument("--current", required=True, help="merged/current Materials directory")
    ap.add_argument("--out", required=True, help="output Materials directory")
    ap.add_argument("--tool", required=True, help="UAssetTool.dll")
    ap.add_argument("--tool-cwd", required=True, help="directory containing Mappings.usmap")
    ap.add_argument("--dotnet", default="/opt/data/dotnet10/dotnet")
    args = ap.parse_args()

    plan = json.load(open(args.plan))
    rows = plan if isinstance(plan, list) else plan.get("rows", plan.get("materials", []))
    by_name = {row["mi"]: row for row in rows}
    work = os.path.abspath(args.out) + ".restore-work"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(args.current, work)

    restored = []
    for mi, row in by_name.items():
        if row["treatment"] == "opaque":
            continue
        old = os.path.join(args.base, mi)
        new = os.path.join(args.current, mi)
        if not os.path.exists(old + ".uasset") or not os.path.exists(new + ".uasset"):
            continue
        if paired_sha(old) == paired_sha(new):
            continue
        for ext in (".uasset", ".uexp"):
            shutil.copyfile(old + ext, os.path.join(work, mi + ext))
        restored.append(mi)

    two_sided = sorted(mi for mi, row in by_name.items() if row.get("two_sided"))
    list_path = os.path.join(os.path.abspath(args.out) + ".two-sided.txt")
    with open(list_path, "w") as fh:
        fh.write("\n".join(two_sided) + "\n")
    shutil.rmtree(args.out, ignore_errors=True)
    env = {**os.environ, "DOTNET_ROLL_FORWARD": "Major",
           "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1"}
    subprocess.run([args.dotnet, args.tool, "--set-sidedness", work, args.out, list_path],
                   cwd=args.tool_cwd, env=env, check=True)
    report = os.path.join(os.path.abspath(args.out) + ".restored.json")
    json.dump(sorted(restored), open(report, "w"), indent=2)
    print("restored", len(restored), dict(collections.Counter(by_name[mi]["treatment"] for mi in restored)))
    print("two_sided", len(two_sided), "report", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
