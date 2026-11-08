#!/usr/bin/env python3
"""Pak-set ownership checker: no two paks may ship the same asset.

Why this exists: pak mounting keeps exactly ONE copy of each asset path and silently drops the
rest, so a duplicate is not a conflict the engine reports — it is a silent eviction decided by
filename sort. That has already cost two features (lights v7 evicted by a nav pak; the whole-map
light sublevel reference dropped by a pak that also carried C1Full.umap).

The rule this enforces, by construction: ONE ASSET, ONE PAK.

  manifest <pak> <outdir>   write <outdir>/<pak-basename>.json {pak, bytes, sha256, assets[]}
  check <outdir>            fail if any asset path appears in more than one manifest, or if two
                            manifests share a version-less stem (v10 and v11 installed together)

Exit codes: 0 clean, 2 usage, 3 duplicate asset, 4 duplicate stem, 5 unreadable manifest.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

REPAK = os.environ.get("REPAK", "/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak")
# Paks that legitimately ship no runtime assets of their own.
STEM_RE = re.compile(r"^(?P<stem>.+?)(?:_v\d+)?_P\.pak$")


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def assets_of(pak):
    out = subprocess.run([REPAK, "list", pak], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200] or "repak list failed")
    return sorted({line.strip() for line in out.stdout.splitlines() if line.strip()})


def cmd_manifest(pak, outdir):
    os.makedirs(outdir, exist_ok=True)
    rec = {"pak": os.path.basename(pak), "bytes": os.path.getsize(pak),
           "sha256": sha256(pak), "assets": assets_of(pak)}
    path = os.path.join(outdir, rec["pak"][:-4] + ".json")
    with open(path, "w") as f:
        json.dump(rec, f, indent=0)
    print("MANIFEST %s assets=%d bytes=%d sha=%s" %
          (rec["pak"], len(rec["assets"]), rec["bytes"], rec["sha256"][:16]))
    return 0


def cmd_check(outdir):
    recs = []
    for f in sorted(os.listdir(outdir)):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(outdir, f)) as fh:
            recs.append(json.load(fh))
    if not recs:
        print("FAIL: no manifests in %s" % outdir)
        return 5

    owner = {}
    dupes = {}
    for rec in recs:
        for a in rec["assets"]:
            if a in owner and owner[a] != rec["pak"]:
                dupes.setdefault(a, {owner[a]}).add(rec["pak"])
            else:
                owner[a] = rec["pak"]

    stems = {}
    for rec in recs:
        m = STEM_RE.match(rec["pak"])
        stem = m.group("stem") if m else rec["pak"][:-4]
        stems.setdefault(stem, []).append(rec["pak"])
    stem_dupes = {k: v for k, v in stems.items() if len(v) > 1}

    total = sum(r["bytes"] for r in recs)
    print("PAKSET %d paks, %d assets, %.1f MB" % (len(recs), len(owner), total / 1e6))
    for rec in recs:
        print("  %-46s %10d B  %5d assets  %s" %
              (rec["pak"], rec["bytes"], len(rec["assets"]), rec["sha256"][:16]))

    if stem_dupes:
        print("\nFAIL(stem): more than one version of the same pak installed")
        for stem, paks in stem_dupes.items():
            print("  %s -> %s" % (stem, ", ".join(paks)))
        return 4

    if dupes:
        print("\nFAIL(duplicate): %d asset paths claimed by more than one pak" % len(dupes))
        for a, paks in list(dupes.items())[:15]:
            print("  %s  <-  %s" % (a, ", ".join(sorted(paks))))
        if len(dupes) > 15:
            print("  ... %d more" % (len(dupes) - 15))
        return 3

    print("\nOK: every asset has exactly one owner")
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "manifest" and len(argv) == 4:
        return cmd_manifest(argv[2], argv[3])
    if cmd == "check" and len(argv) == 3:
        return cmd_check(argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
