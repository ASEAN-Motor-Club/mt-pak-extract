#!/usr/bin/env python3
"""Compile the map's material source into a per-instance plan. Analysis only: writes no pak.

Inputs
  --source    c1/source/merged.materials.json      (canonical BeamNG definitions)
  --materials dir of MI_*.uasset/.uexp             (extracted from the geometry pak)
  --textures  Mods/C1/Textures root                (what the client actually loads)
  --out       materials_plan.json

One row per instance, carrying the source's contract resolved to a REAL Motor Town master.
Nothing is applied here; `apply_plan.py` consumes the plan. Keeping the two apart is what makes
the rewrite reviewable: 1,653 decisions in a JSON file beat 1,653 unlogged edits.

The rules encoded below come from three measured facts, not from convention:

1. Every instance's parent package is ABSENT from the pak (author masters under
   /Game/Mods/C1/Materials), so every row must be reparented to a master that exists.
2. A parameter name is not a type: `M_AlphaTest` takes its colour map in `Texture` and `Color` is a
   vector tint (proved by the game's own MI_AlphaTestOneSided). `M_PolygonMaster` takes `BaseColor`.
3. MT has one texture slot per masked master and no AddAlpha blend, so separate opacity maps are
   baked into the colour texture's alpha across the whole mip chain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# --- master contracts (measured: c1/docs/MASTER_CONTRACTS.md) --------------------------------
# pkg / name / the parameter that takes the COLOUR TEXTURE on that master.
MASTERS = {
    "M_AlphaTest": {
        "pkg": "/Game/AssetsvilleTown2/Materials/MasterMaterials/M_AlphaTest",
        "name": "M_AlphaTest",
        "colour": "Texture",
        "slots": {"base": "Texture"},
    },
    "M_PolygonMaster": {
        "pkg": "/Game/Env/Materials/Master",
        "name": "M_PolygonMaster",
        "colour": "BaseColor",
        "slots": {"base": "BaseColor", "normal": "Normal", "metallic": "Metallic",
                  "roughness": "Roughness", "emissive": "Emissive", "ao": None},
        "scalars": {"emissive_tint": "Emissive_Tint", "emissive_intensity": "EmissiveIntensity"},
    },
    "M_BaseTexture": {
        "pkg": "/Game/AssetsvilleTown2/Materials/MasterMaterials/M_BaseTexture",
        "name": "M_BaseTexture",
        "colour": "Texture",
        "slots": {"base": "Texture"},
    },
    "M_BaseColor": {
        "pkg": "/Game/AssetsvilleTown2/Materials/MasterMaterials/M_BaseColor",
        "name": "M_BaseColor",
        "colour": None,          # vector only: flat colour materials land here
        "slots": {},
    },
}

DEFAULT_CLIP = 0.5        # alphaTest with no alphaRef: assumption, flagged per row
BAKE_CLIP = 0.5           # mask baked from a separate opacity map
OWNALPHA_CLIP = 0.5       # mask taken from the colour map's own alpha

# Source keys that are engine-side, not material-side. Listed per row so nothing is silently lost.
UNSUPPORTED_KEYS = {
    "groundType": "physics/audio surface, not a material",
    "useAnisotropic": "sampler setting, not an instance parameter",
    "detailMap": "needs a second UV set + blend",
    "detailNormalMap": "needs a second UV set + blend",
    "detailScale": "needs a second UV set + blend",
    "translucentZWrite": "no instance-level switch",
    "translucentRecvShadows": "no instance-level switch",
    "castShadows": "primitive flag, not a material",
    "invertBackFaceNormals": "no instance-level switch",
    "glow": "routed to emissive as an approximation",
    "glowFactor": "routed to emissive as an approximation",
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def source_key(mi: str) -> str:
    return mi.replace("MI_C1X_", "", 1).replace("MI_C1_", "", 1)


def raw_texture(mi_path: str) -> tuple[str, str] | None:
    got = raw_textures(mi_path)
    return got[0] if got else None


def raw_textures(mi_path: str) -> list[tuple[str, str]]:
    """Every /Game/Mods/C1/Textures/<sub>/<name> the instance imports, in file order."""
    blob = open(mi_path, "rb").read()
    seen, out = set(), []
    for m in re.finditer(rb"/Game/Mods/C1/Textures/([A-Za-z0-9_]+)/([A-Za-z0-9_]+)", blob):
        t = (m.group(1).decode(), m.group(2).decode())
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def texture_map(entry: dict, field: str) -> str:
    """BeamNG map path -> port texture base name (`x_d.color.png` -> `x_d_color`)."""
    stage = (entry.get("Stages") or [{}])[0]
    p = stage.get(field) or ""
    b = os.path.basename(p)
    for ext in (".color.png", ".data.png", ".normal.png", ".dds", ".png"):
        if b.endswith(ext):
            b = b[: -len(ext)]
    # BeamNG bakes variant suffixes into the filename — "x_file0(CUnet)(noise)(Level3)" — which the
    # UE import dropped. Strip them or the lookup misses a texture that is right there.
    b = re.sub(r"\([^)]*\)", "", b).strip("_")
    # BeamNG separates suffixes with dots ("x.gtf_tex_131.o" + ".png"); the port uses underscores.
    b = b.replace(".", "_").strip("_")
    return b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--materials", required=True)
    ap.add_argument("--textures", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tool", default="")
    ap.add_argument("--dotnet", default="/opt/data/dotnet10/dotnet")
    ap.add_argument("--limit", type=int, default=0, help="debug: only N instances")
    ap.add_argument("--source-zip", default="",
                    help="BeamNG source archive: consulted only when a cooked texture cannot be "
                         "decoded (inline mip data) so an alpha decision is never a guess")
    a = ap.parse_args()

    import opacity_bake
    import struct
    import zipfile

    src = json.load(open(a.source))

    zf = zipfile.ZipFile(a.source_zip) if a.source_zip else None
    znames = set(zf.namelist()) if zf else set()
    dds_cache: dict[str, dict] = {}

    def dds_facts(stem: str) -> dict:
        """Format + real alpha spread from the SOURCE dds, for cooked textures we cannot decode."""
        if stem in dds_cache:
            return dds_cache[stem]
        entry = f"levels/c1/art/textures/{stem}.dds"
        out: dict = {"exists": False, "via": "source-dds"}
        if zf and entry in znames:
            try:
                d = zf.read(entry)
                fourcc = d[84:88]
                # DDS: 12 = dwHeight, 16 = dwWidth (reading width first silently yields a
                # 32x1024 "texture" and the size validation then rejects a perfectly good file).
                h, w = struct.unpack_from("<II", d, 12)
                # texture2ddecoder SEGFAULTS (not raises) on a short buffer or absurd dimensions:
                # several source dds are odd (mip chains, 0 dims). Validate before the call.
                need = ((w + 3) // 4) * ((h + 3) // 4) * (16 if fourcc == b"DXT5" else 8)
                if not (0 < w <= 8192 and 0 < h <= 8192) or len(d) - 128 < need:
                    out["error"] = f"source dds unusable ({w}x{h}, {len(d) - 128}B < {need}B)"
                    dds_cache[stem] = out
                    return out
                if fourcc == b"DXT5":
                    import texture2ddecoder
                    px = texture2ddecoder.decode_bc3(d[128:128 + need], w, h)
                    al = px[3::4]
                    out.update({"exists": True, "fmt": "PF_DXT5", "w": w, "h": h,
                                "alpha_spread": max(al) - min(al),
                                "alpha_coverage": round(sum(1 for v in al if v > 127) / len(al), 3)})
                else:
                    out.update({"exists": True, "fmt": "PF_DXT1", "w": w, "h": h,
                                "alpha_spread": 0, "alpha_coverage": 1.0})
            except Exception as exc:
                out["error"] = str(exc)[:100]
        dds_cache[stem] = out
        return out

    # texture index: base name -> path (all subdirs of the port's texture root)
    tex_index: dict[str, str] = {}
    for dirpath, _dirs, files in os.walk(a.textures):
        for f in files:
            if f.endswith(".uasset"):
                tex_index.setdefault(f[: -len(".uasset")], os.path.join(dirpath, f[: -len(".uasset")]))

    facts: dict[str, dict] = {}

    def tex_facts(path: str) -> dict:
        if path in facts:
            return facts[path]
        f = {"exists": False}
        try:
            fmt, w, h, blob = opacity_bake.read_tex(path)
            px, _ = opacity_bake.decode_level0(fmt, w, h, blob)
            alpha = px[3::4]
            cov = sum(1 for v in alpha if v > 127) / len(alpha)
            f = {"exists": True, "fmt": fmt, "w": w, "h": h,
                 "alpha_spread": max(alpha) - min(alpha), "alpha_coverage": round(cov, 3)}
        except Exception as exc:
            f = {"exists": True, "error": str(exc)[:120]}
        facts[path] = f
        return f

    def resolve(name: str) -> str | None:
        p = tex_index.get(name)
        if p:
            return p
        # UE stores an FName's trailing digits as a separate number, so the raw bytes give the stem
        # (`area_zz_02_gtf_tex`) while the file on disk has the full name (`…_134`). Prefix-match
        # first: a dump per instance costs a second each and there are hundreds of these.
        cands = [k for k in tex_index if k.startswith(name) and k[len(name):].isdigit()]
        if len(cands) == 1:
            return tex_index[cands[0]]
        # Last resort: exactly one asset starts with this stem (`mat_x_file0` -> `mat_x_file0_color`).
        cands = [k for k in tex_index if k.startswith(name)]
        if len(cands) == 1:
            return tex_index[cands[0]]
        return None

    rows: list[dict] = []
    unresolved: list[dict] = []

    mis = sorted(f[: -len(".uasset")] for f in os.listdir(a.materials) if f.endswith(".uasset"))
    if a.limit:
        mis = mis[: a.limit]

    for n, mi in enumerate(mis, 1):
        key = source_key(mi)
        entry = src.get(key)
        row: dict = {"mi": mi, "key": key if entry else None}
        if not entry:
            row.update({"treatment": "keep_authored", "clip": None, "two_sided": None,
                        "master": None, "textures": {}, "texture_facts": {}, "source_flags": {},
                        "unsupported": [],
                        "notes": ["no entry in the source json — port-only instance, left as authored"]})
            rows.append(row)
            unresolved.append({"mi": mi, "key": key})
            continue

        stage = (entry.get("Stages") or [{}])[0]
        alpha_test = bool(entry.get("alphaTest"))
        translucent = bool(entry.get("translucent"))
        blend_op = entry.get("translucentBlendOp")
        alpha_ref = entry.get("alphaRef")
        opacity_map = stage.get("opacityMap")

        # The instance's OWN texture imports are authoritative: the author's UE import renamed the
        # BeamNG maps (suffixes like "(CUnet)(noise)(Level3)" are dropped), so a source-side basename
        # is only a fallback. Resolve per slot by suffix, which is how the port names them.
        imports = raw_textures(os.path.join(a.materials, mi + ".uasset"))
        src_base = texture_map(entry, "baseColorMap") or texture_map(entry, "colorMap")
        SUFFIX = (("base", ("_d_color", "_color")), ("normal", ("_n_normal", "_normal")),
                  ("metallic", ("_m_data",)), ("roughness", ("_r_data",)),
                  ("ao", ("_ao_data",)), ("emissive", ("_e_data", "_e_color", "_emissive")))
        imp_by_slot: dict[str, tuple[str, str]] = {}
        for slot, suffixes in SUFFIX:
            for suf in suffixes:
                hit = next((t for t in imports if t[1].endswith(suf)), None)
                if hit:
                    imp_by_slot[slot] = hit
                    break
        if "base" not in imp_by_slot and imports:
            imp_by_slot["base"] = imports[0]
        base_name = imp_by_slot["base"][1] if "base" in imp_by_slot else src_base
        base_sub = imp_by_slot["base"][0] if "base" in imp_by_slot else ""
        base_path = resolve(base_name) if base_name else None
        if not base_path and src_base:
            # Second chance with the source's own name: it keeps the trailing digits that the
            # cooked FName splits off, which is what makes an import look unresolved.
            base_path = resolve(src_base)
            if base_path:
                base_name = os.path.basename(base_path)
        if base_name and not base_path and a.tool:
            # FName trailing digits are stored as a separate number: raw bytes lose them, the
            # tool's dump resolves them. Only pay for the dump when the file is not on disk.
            out = subprocess.run([a.dotnet, a.tool, "--dump",
                                  os.path.join(a.materials, mi + ".uasset")],
                                 capture_output=True, text=True,
                                 cwd=os.path.abspath(os.path.join(os.path.dirname(a.tool), *[".."] * 3)),
                                 env={**os.environ, "DOTNET_ROLL_FORWARD": "Major",
                                      "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1"}).stdout
            m = re.search(r"Name=/Game/Mods/C1/Textures/([A-Za-z0-9_]+)/([A-Za-z0-9_]+)", out)
            if m:
                base_name = m.group(2)
                base_path = resolve(base_name)
        bf = tex_facts(base_path) if base_path else {"exists": False}
        if src_base and ("error" in bf or "alpha_spread" not in bf):
            # Cooked texture unreadable (small textures keep their mips inline, no .ubulk) — ask
            # the source dds. An alpha decision must never rest on a failed decode.
            df = dds_facts(src_base)
            if df.get("alpha_spread") is not None:
                bf = {**bf, **{k: df[k] for k in ("alpha_spread", "alpha_coverage", "fmt", "w", "h")
                               if k in df}, "via": "source-dds"}

        unsupported = [f"{k}: {v}" for k, v in UNSUPPORTED_KEYS.items() if k in entry or k in stage]
        assumptions: list[str] = []

        # ---- treatment ----------------------------------------------------------------
        if opacity_map:
            # A separate mask outranks alphaTest: 10 materials carry BOTH, and when they do the
            # opacity map is the mask the author intended (the colour map may have no alpha at
            # all). Also a cutout when the material is not flagged translucent.
            treatment = "bake"
            clip = BAKE_CLIP
            master = "M_AlphaTest"
            if alpha_test:
                assumptions.append("alphaTest + separate opacityMap: the opacity map is the mask")
            elif not translucent:
                assumptions.append("opacityMap on a non-translucent material: treated as a cutout")
        elif alpha_test:
            treatment = "masked"
            if isinstance(alpha_ref, (int, float)):
                clip = round(alpha_ref / 255.0, 4)
            else:
                clip = DEFAULT_CLIP
                assumptions.append("alphaTest with no alphaRef: clip assumed 0.5")
            master = "M_AlphaTest"
        elif translucent:
            if bf.get("alpha_spread", 0) >= 32:
                treatment = "ownalpha"
                clip = OWNALPHA_CLIP
                master = "M_AlphaTest"
                if blend_op == "AddAlpha":
                    assumptions.append("AddAlpha -> masked off own alpha (no MT additive blend)")
            else:
                treatment = "translucent_keep"
                clip = None
                master = None
                assumptions.append("translucent with no separate mask and no usable colour alpha: "
                                   "left translucent, reported")
                unsupported.append("translucent sorting over the road: cannot be fixed without a mask")
        else:
            treatment = "opaque"
            clip = None
            master = "M_BaseColor" if (not base_name) else "M_PolygonMaster"

        # ---- textures ------------------------------------------------------------------
        textures: dict[str, str] = {}
        if base_name:
            textures["base"] = base_name
        for field, slot in (("normalMap", "normal"), ("metallicMap", "metallic"),
                            ("roughnessMap", "roughness"), ("emissiveMap", "emissive"),
                            ("ambientOcclusionMap", "ao")):
            if slot in imp_by_slot:
                textures[slot] = imp_by_slot[slot][1]
                continue
            n2 = texture_map(entry, field)
            if n2:
                textures[slot] = n2
        if opacity_map:
            op = texture_map(entry, "opacityMap")
            if op:
                textures["opacity"] = op
        if "ao" in textures:
            unsupported.append("ambientOcclusionMap: no master outside foliage takes an AO map")

        mdef = MASTERS.get(master) if master else None
        if mdef and treatment == "opaque":
            for slot, name in list(textures.items()):
                if slot != "base" and mdef["slots"].get(slot) is None:
                    unsupported.append(f"{slot} map ({name}): {master} has no such slot")
                    textures.pop(slot)

        emissive = bool(stage.get("emissive") or stage.get("emissiveFactor")
                        or stage.get("instanceEmissive") or stage.get("emissiveMap"))
        if emissive and master in (None, "M_BaseColor"):
            unsupported.append("emissive: target master has no emissive slot")
        elif emissive and master == "M_AlphaTest":
            # 120 instances are emissive on materials that must be masked: the masked master has no
            # emissive parameter at all, so the glow is lost. Say so per row instead of dropping it.
            unsupported.append("emissive: the masked master exposes no emissive parameter — glow dropped")
        elif emissive and not (textures.get("emissive")):
            unsupported.append("emissive: factor only (no emissiveMap) — Emissive_Tint colour cannot be "
                               "carried through a texture slot")

        scalars: dict[str, object] = {}
        for field in ("metallicFactor", "roughnessFactor", "baseColorFactor", "emissiveFactor"):
            if stage.get(field) is not None:
                scalars[field] = stage[field]
        if stage.get("diffuseColor"):
            scalars["diffuseColor"] = stage["diffuseColor"]
        if emissive:
            scalars["emissive"] = 1.0

        for slot, name in textures.items():
            if slot == "base":
                continue          # validated above by base_path; re-resolving it here only re-reports
            p = resolve(name)
            if not p:
                unsupported.append(f"{slot} texture '{name}' not found under the port texture root")

        tfact: dict[str, dict] = {}
        for s, nm in textures.items():
            if s == "base":
                continue          # recorded below, using the facts the decision actually used
            p2 = resolve(nm)
            if p2:
                tfact[s] = tex_facts(p2)
        if base_name:
            tfact["base"] = bf

        rows.append({
            "mi": mi,
            "key": key,
            "treatment": treatment,
            "master": ({"pkg": mdef["pkg"], "name": mdef["name"],
                        "colour_param": mdef["colour"]} if mdef else None),
            "clip": clip,
            "two_sided": bool(entry.get("doubleSided")),
            "source_flags": {"alphaTest": alpha_test, "alphaRef": alpha_ref,
                             "translucent": translucent, "blendOp": blend_op,
                             "opacityMap": bool(opacity_map), "emissive": emissive},
            "textures": textures,
            "texture_facts": tfact,
            "scalars": scalars,
            "cast_shadows": entry.get("castShadows"),
            "unsupported": unsupported,
            "assumptions": assumptions,
        })
        if n % 200 == 0:
            print(f"  ... {n}/{len(mis)}", file=sys.stderr, flush=True)

    counts = Counter(r["treatment"] for r in rows)
    masters = Counter((r["master"] or {}).get("name") for r in rows)
    plan = {
        "source": {"path": os.path.abspath(a.source), "sha256": sha256_file(a.source),
                   "materials": len(src)},
        "materials_dir": os.path.abspath(a.materials),
        "counts": dict(counts),
        "masters": {k: v for k, v in masters.items() if k},
        "rows": rows,
        "unresolved": unresolved,
    }
    json.dump(plan, open(a.out, "w"), indent=1)

    print("== treatments")
    for k, v in counts.most_common():
        print(f"  {v:5d}  {k}")
    print("== target masters")
    for k, v in masters.most_common():
        print(f"  {v:5d}  {k}")
    print(f"== unresolved (keep_authored): {len(unresolved)}")
    print(f"plan -> {a.out}  rows={len(rows)}  source_sha256={plan['source']['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
