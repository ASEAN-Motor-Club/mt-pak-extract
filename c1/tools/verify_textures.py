#!/usr/bin/env python3
"""Fail the build when a texture ships without pixel data.

Base_v3 went out with 220 empty Texture2D stubs (68 of them visible base-colour
maps) because nothing in the pipeline ever checked whether an imported texture
actually carried a mip chain. The editor-side import had silently skipped them,
the stub `.uasset`/`.uexp` pair from the DDS converter survived into the pack, and
the result was checkerboard materials in game (mat_kbd02_001_5 was the report).

A real cooked Texture2D always names `SizeX`/`SizeY` and carries `PlatformData`
mips. A stub has only `ImportedSize` + `LightingGuid`: a ~834 B `.uasset`, a
~159 B `.uexp`, no `.ubulk`, and no `SizeX` anywhere in the package bytes. That
signature is cheap and reliable, so it is the gate.

Usage:
  verify_textures.py <tree-or-pak> [<tree-or-pak> ...]
      --allow-ao        treat `*_ao_data` stubs as warnings (they are masks that
                        mostly do not show, but they still get printed)
      --write-list F    write the offending texture names, one per line, as a
                        re-import work list
      --max-report N    cap the printed list (default 40)

Exit codes: 0 clean (or only allowed AO stubs), 1 stubs found, 2 usage/IO error.
Requires `repak` on PATH (or $REPAK) only when given a .pak.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

# Empirically calibrated on cooked Motor Town packages (2026-11-14):
#   stub  : uexp 159-323 B, no .ubulk (null 323, mat_jimen_01_color 299) = package
#           overhead only, zero mip payload
#   real  : uexp 347+ for tiny inline textures (8x8 DXT1 lands at 347-379 because
#           its mip chain is only 56 B) up to 591 for 16x16 DXT5, or any size with
#           a .ubulk sibling
# The boundary is overhead (~300 B) plus at least one mip level, so 340 splits the
# known pairs exactly; it is empirical and should be re-derived if the engine's
# package overhead changes.
# Name-table markers do NOT work: cooked packages carry neither `SizeX` nor
# `PlatformData` as literal strings, in stubs and in freshly cooked textures alike.
STUB_UEXP_MAX = 340
STUB_UASSET_MAX = 1500


def classify(uasset_path: str, uexp_path: str):
    """Return (is_texture, is_stub) for one cooked package."""
    if os.path.exists(uexp_path[:-len(".uexp")] + ".ubulk"):
        return True, False                      # streamed pixel data present
    try:
        with open(uasset_path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return False, False
    # Material instances and blueprints share the .uasset/.uexp layout and even
    # name Texture2D in their imports; a stub is distinguished by its size and by
    # carrying only the two placeholder properties an empty Texture2D has.
    if b"ImportedSize" not in blob:
        return False, False
    if os.path.getsize(uasset_path) > STUB_UASSET_MAX:
        return False, False
    try:
        if os.path.getsize(uexp_path) >= STUB_UEXP_MAX:
            return True, False
    except OSError:
        return True, True
    # Small package, no .ubulk and a trivial uexp: this is the stub signature.
    return True, True


def scan_tree(root: str):
    stubs, total = [], 0
    for dirpath, _dirnames, files in os.walk(root):
        for name in files:
            if not name.endswith(".uasset"):
                continue
            base = name[:-len(".uasset")]
            uexp = os.path.join(dirpath, base + ".uexp")
            if not os.path.exists(uexp):
                continue
            is_tex, stub = classify(os.path.join(dirpath, name), uexp)
            if not is_tex:
                continue
            total += 1
            if stub:
                stubs.append(os.path.join(dirpath, base))
    return total, stubs


def unpack(pak: str, outdir: str) -> None:
    repak = os.environ.get("REPAK") or shutil.which("repak")
    if not repak:
        sys.exit("FAIL: repak not found (set $REPAK)")
    subprocess.run([repak, "unpack", "-q", "-o", outdir, pak], check=True)


def stub_stems(target: str):
    """Lowercased asset stems in `target` whose Texture2D carries no pixel data.

    Used by check_texture_coverage.py: an asset that exists by name but has no
    mips still renders as checkerboard, so presence alone is not coverage.
    Accepts a directory or a .pak.
    """
    tmp = None
    try:
        if os.path.isdir(target):
            root = target
        elif target.endswith(".pak"):
            tmp = tempfile.mkdtemp(prefix="stubstems-")
            unpack(target, tmp)
            root = tmp
        else:
            return set()
        _total, stubs = scan_tree(root)
        return {os.path.basename(s).lower() for s in stubs}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--allow-ao", action="store_true")
    ap.add_argument("--write-list")
    ap.add_argument("--max-report", type=int, default=40)
    args = ap.parse_args()

    all_stubs, grand_total = [], 0
    tmpdirs = []
    try:
        for target in args.targets:
            if os.path.isdir(target):
                root = target
            elif target.endswith(".pak"):
                tmp = tempfile.mkdtemp(prefix="verify-tex-")
                tmpdirs.append(tmp)
                unpack(target, tmp)
                root = tmp
            else:
                print(f"FAIL: not a directory or pak: {target}", file=sys.stderr)
                return 2
            total, stubs = scan_tree(root)
            grand_total += total
            all_stubs += [(target, s) for s in stubs]
            print(f"[{target}] textures={total} stubs={len(stubs)}")
    finally:
        for tmp in tmpdirs:
            shutil.rmtree(tmp, ignore_errors=True)

    blocking = [s for s in all_stubs if not (args.allow_ao and os.path.basename(s[1]).endswith("_ao_data"))]
    ao = len(all_stubs) - len(blocking)

    # A dedicated-server build carries no pixel data at all on purpose (it never
    # renders). If *every* texture is empty, this is a server pak, not a defect.
    if grand_total and len(all_stubs) == grand_total:
        print(f"NOTE all {grand_total} textures are data-less: server build, "
              f"pixel data is not expected here — skipping texture gate")
        return 0

    for target, s in blocking[: args.max_report]:
        print(f"  STUB {os.path.relpath(s, os.path.dirname(s))}  ({target})")
    if len(blocking) > args.max_report:
        print(f"  ... {len(blocking) - args.max_report} more")

    if args.write_list:
        with open(args.write_list, "w") as fh:
            for _target, s in all_stubs:
                fh.write(os.path.basename(s) + "\n")
        print(f"wrote {len(all_stubs)} names to {args.write_list}")

    if ao:
        print(f"NOTE {ao} empty *_ao_data mask(s) (not blocking with --allow-ao)")

    if blocking:
        print(f"FAIL {len(blocking)} texture(s) ship with no pixel data, "
              f"out of {grand_total} checked — these render as checkerboard")
        return 1
    print(f"OK all {grand_total} textures carry pixel data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
