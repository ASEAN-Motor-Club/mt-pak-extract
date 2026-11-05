#!/usr/bin/env python3
"""Build the map's material pak from the SOURCE material definitions, not by hand.

The BeamNG map ships its intent as data (`levels/c1/art/models/merged.materials.json`), and every
material there states its own blend contract: `alphaTest` + `alphaRef`, or `translucent` +
`translucentBlendOp`, plus an optional separate `opacityMap`. The port has to reproduce that
contract on a Motor Town master, and the only reliable way is to derive it per material.

    build_materials.py --source merged.materials.json \
                       --materials <dir: MI_*.uasset/.uexp extracted from the geometry pak> \
                       --textures  <dir: Mods/C1/Textures root> \
                       --tool      <UAssetTool.dll> --work <scratch> --pak <out.pak> \
                       [--family mat_mj] [--dry-run]

Classification (from the source json):

  masked   alphaTest true                 -> masked master, clip = alphaRef/255
  bake     translucent + opacityMap       -> bake opacity into BaseColor alpha, then masked at 0.5
  opaque   translucent, no opacityMap     -> left alone (nothing to cut with)
  skip     everything else                -> not in this family's scope

Why bake instead of binding: MT's masked master takes ONE texture (`Color`); there is no
two-sampler masked master, and BeamNG's `AddAlpha` blend has no MT equivalent at all.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MASKED_MASTER_PKG = "/Game/AssetsvilleTown/Materials/MasterMaterials/M_AlphaTest"
MASKED_MASTER_NAME = "M_AlphaTest"
DEFAULT_CLIP = 0.3333
BAKE_CLIP = 0.5


def run(cmd: list[str], cwd: str | None = None) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    out = (p.stdout or "") + (p.stderr or "")
    # UAssetTool exits 0 even when it rejects an argument or cannot find its mappings, printing a
    # usage banner instead — treat those as failures or a silent no-op stage looks like success.
    # (the usage banner is printed on every run, so only "Error:" marks a rejected invocation)
    bad = p.returncode != 0 or "Error:" in out
    if bad:
        raise RuntimeError(f"{' '.join(cmd[:3])}... failed rc={p.returncode}\n{out[-1500:]}")
    return out.strip()


def mi_texture(mi_path: str) -> tuple[str, str] | None:
    """First /Game/Mods/C1/Textures/<dir>/<name> the instance imports."""
    blob = open(mi_path, "rb").read()
    m = re.search(rb"/Game/Mods/C1/Textures/([A-Za-z0-9_]+)/([A-Za-z0-9_]+)", blob)
    return (m.group(1).decode(), m.group(2).decode()) if m else None


def find_texture(textures_root: str, sub: str, name: str) -> str | None:
    for cand in (os.path.join(textures_root, sub, name), None):
        if cand and os.path.exists(cand + ".uexp"):
            return cand
    for dirpath, _dirs, files in os.walk(textures_root):
        if name + ".uexp" in files:
            return os.path.join(dirpath, name)
    return None


def opacity_name(base: str) -> list[str]:
    """BeamNG names the pair <x>_d.color + <x>_o.data; the port flattens dots to underscores."""
    cands = []
    if "_d_color" in base:
        cands.append(base.replace("_d_color", "_o_data"))
    if "_color" in base:
        cands.append(base.replace("_color", "_o_data"))
    cands.append(base + "_o_data")
    return cands


def classify(src: dict, key: str) -> tuple[str, float | None, str | None]:
    entry = src.get(key)
    if not entry:
        return "unknown", None, None
    stage = (entry.get("Stages") or [{}])[0]
    if entry.get("alphaTest"):
        ref = entry.get("alphaRef")
        clip = (ref / 255.0) if isinstance(ref, (int, float)) else DEFAULT_CLIP
        return "masked", clip, None
    if entry.get("translucent"):
        op = stage.get("opacityMap")
        if op:
            return "bake", BAKE_CLIP, op
        return "opaque", None, None
    return "opaque", None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="merged.materials.json")
    ap.add_argument("--materials", required=True, help="dir of MI_*.uasset/.uexp from the geometry pak")
    ap.add_argument("--textures", required=True, help="Mods/C1/Textures root")
    ap.add_argument("--tool", required=True, help="UAssetTool.dll")
    ap.add_argument("--dotnet", default="dotnet")
    ap.add_argument("--work", required=True)
    ap.add_argument("--pak", required=True)
    ap.add_argument("--family", default="", help="only instances whose source key starts with this")
    ap.add_argument("--texture-subdir", default="other", help="where baked textures live in the pak")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # UAssetTool resolves Mappings.usmap relative to its CWD, not to the DLL path, so every
    # invocation has to run from the tool repo root (…/csharp/UAssetTool/bin/Release/net8.0/X.dll
    # -> five levels up). Running from anywhere else fails with "Access to the path
    # '/opt/data/Mappings.usmap' is denied" and the pipeline dies on the first stage.
    tool_cwd = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(a.tool)), *[".."] * 5))

    src = json.load(open(a.source))
    work = os.path.abspath(a.work)
    shutil.rmtree(work, ignore_errors=True)
    for sub in ("masked", "bake", "final", "content"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)

    groups: dict[str, list[tuple[str, float, str | None]]] = {"masked": [], "bake": [], "opaque": [], "unknown": []}
    for f in sorted(os.listdir(a.materials)):
        if not f.endswith(".uasset"):
            continue
        mi = f[: -len(".uasset")]
        key = mi.replace("MI_C1_", "", 1)
        if a.family and not key.startswith(a.family):
            continue
        kind, clip, opmap = classify(src, key)
        groups[kind].append((mi, clip or 0.0, opmap))

    print(f"family={a.family or '*'} masked={len(groups['masked'])} bake={len(groups['bake'])} "
          f"opaque={len(groups['opaque'])} unknown={len(groups['unknown'])}")
    if a.dry_run:
        for kind in ("masked", "bake", "opaque", "unknown"):
            for mi, clip, _ in groups[kind][:40]:
                print(f"  {kind:8s} {mi:40s} clip={clip:.3f}")
        return 0

    report: dict = {"family": a.family, "counts": {k: len(v) for k, v in groups.items()}, "baked": []}

    def stage(src_dir: str, names: list[str], tag: str) -> str:
        out = os.path.join(work, tag)
        os.makedirs(out, exist_ok=True)
        for n in names:
            for ext in (".uasset", ".uexp"):
                s = os.path.join(src_dir, n + ext)
                if os.path.exists(s):
                    shutil.copy(s, out)
        return out

    def finish(group_dir: str, names: list[str], tag: str, clips: dict[str, float]) -> str:
        """rename BaseColor->Color, reparent to the masked master, clear overrides, set per-material clip."""
        cur = group_dir
        if not names:
            return cur
        lst = os.path.join(work, f"{tag}_list.txt")
        open(lst, "w").write("\n".join(names) + "\n")
        clip_tsv = os.path.join(work, f"{tag}_clip.tsv")
        open(clip_tsv, "w").write("\n".join(f"{n}\t{clips.get(n, DEFAULT_CLIP):.4f}" for n in names) + "\n")

        steps = [
            ("r", ["--rename-texture-param", "@cur", "@out", "BaseColor", "Color"]),
            ("p", ["--set-mi-parent", "@cur", "@out", lst, MASKED_MASTER_PKG, MASKED_MASTER_NAME]),
            ("o", ["--clear-overrides", "@cur", "@out", lst]),
            ("c", ["--set-clip", "@cur", "@out", clip_tsv]),
        ]
        for letter, sargs in steps:
            out = os.path.join(work, f"{tag}_{letter}")
            argv = [x.replace("@cur", cur).replace("@out", out) for x in sargs]
            run([a.dotnet, a.tool] + argv, cwd=tool_cwd)
            cur = out
        print(f"  {tag}: {len(names)} instances -> {os.path.basename(cur)}")
        return cur

    # --- masked group -------------------------------------------------------
    masked_names = [mi for mi, _c, _o in groups["masked"]]
    masked_dir = stage(a.materials, masked_names, "masked")
    masked_final = finish(masked_dir, masked_names, "masked",
                          {mi: c for mi, c, _o in groups["masked"]})

    # --- bake group ---------------------------------------------------------
    bake_names = [mi for mi, _c, _o in groups["bake"]]
    bake_dir = stage(a.materials, bake_names, "bake")
    bake_clips = {mi: c for mi, c, _o in groups["bake"]}
    if bake_names:
        import opacity_bake  # local module; needs texture2ddecoder/etcpak

        for mi, _clip, _opmap in groups["bake"]:
            tex = mi_texture(os.path.join(bake_dir, mi + ".uasset"))
            if not tex:
                report["baked"].append({"mi": mi, "error": "no texture import"})
                continue
            sub, base = tex
            base_path = find_texture(a.textures, sub, base)
            op_path = None
            for cand in opacity_name(base):
                op_path = find_texture(a.textures, sub, cand)
                if op_path:
                    break
            if not base_path or not op_path:
                report["baked"].append({"mi": mi, "texture": base,
                                        "error": "missing base or opacity texture"})
                continue
            try:
                stats = opacity_bake.bake(base_path, op_path, os.path.join(work, "content"),
                                          os.path.join("Mods/C1/Textures", sub))
                stats["mi"] = mi
                report["baked"].append(stats)
            except Exception as exc:  # keep going, report per material
                report["baked"].append({"mi": mi, "texture": base, "error": str(exc)})
    bake_final = finish(bake_dir, bake_names, "bake", bake_clips) if bake_names else None

    # --- merge --------------------------------------------------------------
    final = os.path.join(work, "final")
    for d in (masked_final, bake_final):
        if not d:
            continue
        for f in os.listdir(d):
            shutil.copy(os.path.join(d, f), final)

    extra = os.path.join(work, "content")
    has_extra = os.path.isdir(extra) and any(os.scandir(extra))
    pak_cmd = ["bash", os.path.join(HERE, "build_matspak.sh"), final, a.pak]
    if has_extra:
        pak_cmd.append(extra)
    pak_out = run(pak_cmd, cwd=os.path.dirname(HERE))
    print(pak_out)

    report["pak"] = a.pak
    report["instances_in_pak"] = len([f for f in os.listdir(final) if f.endswith(".uasset")])
    report["textures_baked"] = len([x for x in report["baked"] if "error" not in x])
    report_path = os.path.join(work, "materials_report.json")
    json.dump(report, open(report_path, "w"), indent=1)
    print(f"report {report_path} instances={report['instances_in_pak']} baked={report['textures_baked']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
