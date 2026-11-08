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
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# AssetsvilleTown2, not AssetsvilleTown: the first path exists as a directory name in the pak but
# holds different masters. A wrong package path does not error at load — the instance silently
# fails to compile and the mesh draws with the engine default (grey checkerboard).
MASKED_MASTER_PKG = "/Game/AssetsvilleTown2/Materials/MasterMaterials/M_AlphaTest"
MASKED_MASTER_NAME = "M_AlphaTest"
# Names an instance may use for its base-colour texture parameter before the reparent. `BaseColor`
# is the modern convention; `Texture` is what the older M_C1_Surface-derived instances carry, and
# missing that one silently orphans the override (see finish()).
# Parameter names a masked instance may already carry before reparenting. `Color` must be in
# this list: it is the name finish() renames everything TO and the one M_AlphaTest declares, so
# an instance that already says `Color` is correct and needs no rename. Leaving it out rejected
# nine sound instances and aborted the whole build on a false positive.
COLOUR_PARAMS = ("BaseColor", "Texture", "Color")
# Rename target for every masked/bake/own-alpha instance, i.e. whatever M_AlphaTest samples.
# It is `Texture`, NOT `Color`: on that master `Color` is a vector tint, so writing the map
# there is silently ignored and the surface renders the master default (flat grey).
COLOUR_TARGET = "Texture"
DEFAULT_CLIP = 0.3333
BAKE_CLIP = 0.5


def run(cmd: list[str], cwd: str | None = None) -> str:
    # UAssetAPI used to open Mappings.usmap with FileMode.Open (exclusive FileShare.None), so a
    # second concurrent process aborted with rc=-6. Fixed in the fork (now FileShare.ReadWrite);
    # the retry stays as a cheap guard against a stale process still holding an old build.
    for attempt in range(6):
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        blob = (p.stdout or "") + (p.stderr or "")
        if p.returncode == 0 and "being used by another process" not in blob:
            break
        if "being used by another process" in blob and attempt < 5:
            time.sleep(2)
            continue
        break
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


def texture_from_dump(mi_path: str, tool: str, dotnet: str, cwd: str) -> tuple[str, str] | None:
    """Resolve the texture import via the tool.

    UE stores an FName's trailing digits as a separate number, so `area_zz_02_gtf_tex_134` shows up
    in the raw bytes as plain `area_zz_02_gtf_tex`. The dump resolves the FName properly and is the
    only reliable source for names that end in digits.
    """
    out = run([dotnet, tool, "--dump", mi_path], cwd=cwd)
    m = re.search(r"Name=/Game/Mods/C1/Textures/([A-Za-z0-9_]+)/([A-Za-z0-9_]+)", out)
    return (m.group(1), m.group(2)) if m else None


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


def _rmtree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _dump(mi_path: str, tool: str, dotnet: str, cwd: str) -> str:
    return run([dotnet, tool, "--dump", mi_path], cwd=cwd)


def _dump_many(paths: list[str], tool: str, dotnet: str, cwd: str, jobs: int = 4) -> dict[str, str]:
    """Dump many instances with `--dump-batch`: ONE process for the whole list.

    `--dump` costs ~1s of .NET startup for ~0.2s of work, and a materials iteration needs ~850
    dumps (351 masked pre-scan + 351 verify + bake/ownalpha). Batching collapses that to two
    process starts. Falls back to a bounded thread pool per file if the batch call fails or the
    list has duplicate basenames (outputs are named after the file stem).
    """
    if not paths:
        return {}
    stems = [os.path.splitext(os.path.basename(p))[0].lower() for p in paths]
    if len(paths) > 1 and len(set(stems)) == len(stems):
        tmp = tempfile.mkdtemp(prefix="middump_")
        try:
            lst = os.path.join(tmp, "list.txt")
            outdir = os.path.join(tmp, "out")
            with open(lst, "w") as f:
                f.write("\n".join(os.path.abspath(p) for p in paths) + "\n")
            text = run([dotnet, tool, "--dump-batch", lst, outdir], cwd=cwd)
            if "DUMP_BATCH_OK" in text:
                got: dict[str, str] = {}
                for p, stem in zip(paths, stems):
                    f = os.path.join(outdir, stem + ".txt")
                    if os.path.exists(f):
                        got[p] = open(f, errors="replace").read()
                if len(got) == len(paths):
                    return got
        finally:
            _rmtree(tmp)

    if jobs <= 1 or len(paths) <= 1:
        return {p: _dump(p, tool, dotnet, cwd) for p in paths}
    out: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_dump, p, tool, dotnet, cwd): p for p in paths}
        for fut in as_completed(futures):
            out[futures[fut]] = fut.result()
    return out

def mi_texture_param_name(out: str) -> str | None:
    """Name of the instance's texture parameter override, or None if it has none.

    `--rename-texture-param BaseColor Color` used to be hardcoded, but not every instance speaks
    `BaseColor`: several predate that convention and name the parameter `Texture`. Missing them is
    silent (the rename writes the file unchanged and still exits 0), and the instance then gets
    reparented onto a master that declares `Color`, so its texture override no longer resolves and
    a masked material cuts everything away.
    """
    i = out.find("TextureParameterValues (Array[")
    if i < 0:
        return None
    window = out[i:i + 800]
    m = re.search(r"Name \(Name\): ([A-Za-z0-9_]+)", window)
    return m.group(1) if m else None


def mi_parent_name(out: str) -> str | None:
    """Resolve the Parent object reference against the dump's import table."""
    imports = {int(k) + 1: v for k, v in
               re.findall(r"Import\[(\d+)\]: .*?Name=([^,\s]+)", out)}
    m = re.search(r"Parent \(Object\): Index=(-?\d+)", out)
    if not m:
        return None
    idx = abs(int(m.group(1)))
    return imports.get(idx)


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
        # No separate mask: the colour map may still carry alpha (DXT5). Those panels are
        # translucent in the source, which sorts badly over an opaque road and can end up
        # invisible. Masked off their own alpha reads the same and never sorts. Whether the
        # texture really has alpha is checked at build time; if not, the instance is skipped.
        return "ownalpha", BAKE_CLIP, None
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
    ap.add_argument("--game-pak", default="", help="client pak to verify the master package path against")
    ap.add_argument("--jobs", type=int, default=4,
                    help="parallel dump processes for the fallback path (batch mode needs only one)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # UAssetTool computes RootDir as CWD/../.. and reads <RootDir>/Mappings.usmap, so it must be
    # launched from <repo>/csharp/UAssetTool (three levels up from bin/Release/net8.0). Any other
    # CWD silently picks a Mappings.usmap from a *different* repo — or none at all, which surfaces
    # as an unhandled IOException rather than "file not found".
    tool_cwd = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(a.tool)), *[".."] * 3))
    usmap = os.path.abspath(os.path.join(tool_cwd, "..", "..", "Mappings.usmap"))
    if not os.path.exists(usmap):
        raise SystemExit(f"no Mappings.usmap at {usmap} (tool CWD {tool_cwd})")

    # Preflight: a wrong master package path doesn't error anywhere - the instance fails to compile
    # and the mesh draws with the engine default (grey checkerboard). Verify against the real pak.
    if a.game_pak:
        listing = run(["bash", "/opt/data/scripts/pak.sh", "listpak", a.game_pak])
        want = "MotorTown/Content" + MASKED_MASTER_PKG.replace("/Game", "") + ".uasset"
        if want not in listing:
            raise SystemExit(f"master package not in {a.game_pak}: {want}")

    src = json.load(open(a.source))
    work = os.path.abspath(a.work)
    shutil.rmtree(work, ignore_errors=True)
    for sub in ("masked", "bake", "final", "content"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)

    groups: dict[str, list[tuple[str, float, str | None]]] = {
        "masked": [], "ownalpha": [], "bake": [], "opaque": [], "unknown": []}
    for f in sorted(os.listdir(a.materials)):
        if not f.endswith(".uasset"):
            continue
        mi = f[: -len(".uasset")]
        key = mi.replace("MI_C1_", "", 1)
        if a.family and not key.startswith(a.family):
            continue
        kind, clip, opmap = classify(src, key)
        groups[kind].append((mi, clip or 0.0, opmap))

    print(f"family={a.family or '*'} masked={len(groups['masked'])} ownalpha={len(groups['ownalpha'])} "
          f"bake={len(groups['bake'])} opaque={len(groups['opaque'])} unknown={len(groups['unknown'])}")
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
        """rename the texture param to Color, reparent to the masked master, clear overrides, set clip."""
        cur = group_dir
        if not names:
            return cur
        lst = os.path.join(work, f"{tag}_list.txt")
        open(lst, "w").write("\n".join(names) + "\n")
        clip_tsv = os.path.join(work, f"{tag}_clip.tsv")
        open(clip_tsv, "w").write("\n".join(f"{n}\t{clips.get(n, DEFAULT_CLIP):.4f}" for n in names) + "\n")

        # The colour map must land on the parameter the target master actually samples. On
        # M_AlphaTest that is `Texture`; `Color` is a *vector tint* (docs/MASTER_CONTRACTS.md,
        # measured from MI_AlphaTestOneSided). Renaming to `Color` writes nothing the shader
        # reads, so the instance keeps the master's default T_fenceMetal_01 and the surface
        # renders flat grey — exactly what the P23 ship did to every road marking on 2026-11-08.
        param_names: dict[str, list[str]] = {}
        no_param: list[str] = []
        unexpected: list[str] = []
        pre = _dump_many([os.path.join(cur, n + ".uasset") for n in names],
                         a.tool, a.dotnet, tool_cwd, a.jobs)
        for n in names:
            out = pre[os.path.join(cur, n + ".uasset")]
            pn = mi_texture_param_name(out)
            if pn is None:
                no_param.append(n)
            elif pn not in COLOUR_PARAMS:
                unexpected.append(f"{n}:{pn}")
            elif pn != COLOUR_TARGET:
                param_names.setdefault(pn, []).append(n)
        if unexpected:
            # e.g. a masked instance whose only texture parameter is `Normal` — renaming that to
            # Color would feed a normal map into base colour. Needs a human, not a guess.
            raise RuntimeError("masked instance(s) with a non-colour texture parameter: "
                               + ", ".join(unexpected))
        if no_param:
            report.setdefault("no_texture_param", []).extend(
                {"mi": n, "tag": tag} for n in no_param)
            print(f"  {tag}: WARNING {len(no_param)} instance(s) have no texture parameter: "
                  f"{', '.join(no_param[:5])}{' ...' if len(no_param) > 5 else ''}")
        print(f"  {tag}: texture params to rename -> " +
              (", ".join(f"{k}x{len(v)}" for k, v in param_names.items()) or "none"))

        steps = []
        for pn in param_names:
            steps.append(("r", ["--rename-texture-param", "@cur", "@out", pn, COLOUR_TARGET]))
        steps += [
            ("p", ["--set-mi-parent", "@cur", "@out", lst, MASKED_MASTER_PKG, MASKED_MASTER_NAME]),
            ("o", ["--clear-overrides", "@cur", "@out", lst]),
            ("c", ["--set-clip", "@cur", "@out", clip_tsv]),
        ]
        for i, step in enumerate(steps):
            letter, sargs = step[0], step[1]
            out = os.path.join(work, f"{tag}_{letter}{i if letter == 'r' else ''}")
            argv = [x.replace("@cur", cur).replace("@out", out) for x in sargs]
            text = run([a.dotnet, a.tool] + argv, cwd=tool_cwd)
            if letter == "r":
                m = re.search(r"changed=(\d+)", text)
                if m and int(m.group(1)) == 0:
                    raise RuntimeError(f"rename {sargs[3]}->{COLOUR_TARGET} matched nothing in {cur}")
            cur = out
        print(f"  {tag}: {len(names)} instances -> {os.path.basename(cur)}")

        # Post-condition: every instance must actually point at the masked master and, if it has a
        # texture override, name it `Color`. Without this check a silent no-op ships as success.
        bad = []
        post = _dump_many([os.path.join(cur, n + ".uasset") for n in names],
                          a.tool, a.dotnet, tool_cwd, a.jobs)
        for n in names:
            out = post[os.path.join(cur, n + ".uasset")]
            parent = mi_parent_name(out)
            pn = mi_texture_param_name(out)
            if parent != MASKED_MASTER_NAME:
                bad.append(f"{n}: parent={parent}")
            elif pn not in (None, COLOUR_TARGET):
                bad.append(f"{n}: texture param={pn}")
        if bad:
            raise RuntimeError(f"{tag}: {len(bad)} instance(s) failed verification: "
                               + "; ".join(bad[:10]))
        return cur

    # --- masked group -------------------------------------------------------
    masked_names = [mi for mi, _c, _o in groups["masked"]]
    masked_dir = stage(a.materials, masked_names, "masked")
    masked_final = finish(masked_dir, masked_names, "masked",
                          {mi: c for mi, c, _o in groups["masked"]})

    # --- own-alpha group (translucent with no external mask) -----------------
    ownalpha_dir = stage(a.materials, [mi for mi, _c, _o in groups["ownalpha"]], "ownalpha")
    ownalpha_names = []
    if groups["ownalpha"]:
        import opacity_bake

        for mi, _clip, _op in groups["ownalpha"]:
            mi_path = os.path.join(ownalpha_dir, mi + ".uasset")
            tex = mi_texture(mi_path)
            base_path = find_texture(a.textures, *tex) if tex else None
            if base_path is None:  # FName number was stripped from the raw bytes
                tex = texture_from_dump(mi_path, a.tool, a.dotnet, tool_cwd)
                base_path = find_texture(a.textures, *tex) if tex else None
            if not base_path:
                report["skipped"] = report.get("skipped", []) + [{"mi": mi, "why": "no texture"}]
                continue
            try:
                fmt, w, h, blob = opacity_bake.read_tex(base_path)
                px, _ = opacity_bake.decode_level0(fmt, w, h, blob)
                alpha = px[3::4]
                spread = max(alpha) - min(alpha)
            except Exception as exc:
                report["skipped"] = report.get("skipped", []) + [{"mi": mi, "why": str(exc)}]
                continue
            if spread < 32:  # no usable alpha: leave the source's translucent setup alone
                report["skipped"] = report.get("skipped", []) + [
                    {"mi": mi, "why": f"texture alpha flat (spread {spread})"}]
                continue
            ownalpha_names.append(mi)
            # Ship the verified texture with the instance: the client's geometry pak is rebuilt
            # between sessions and its copy of this map may no longer carry alpha, in which case a
            # masked instance cuts everything and the panel disappears entirely.
            for ext in (".uasset", ".uexp", ".ubulk"):
                srcf = base_path + ext
                if os.path.exists(srcf):
                    dstdir = os.path.join(work, "content", "Mods/C1/Textures", tex[0])
                    os.makedirs(dstdir, exist_ok=True)
                    shutil.copy(srcf, dstdir)
    ownalpha_final = (finish(ownalpha_dir, ownalpha_names, "ownalpha",
                             {mi: BAKE_CLIP for mi in ownalpha_names})
                      if ownalpha_names else None)

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
    for d in (masked_final, ownalpha_final, bake_final):
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
