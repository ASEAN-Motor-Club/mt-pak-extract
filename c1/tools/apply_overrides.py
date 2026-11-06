#!/usr/bin/env python3
"""Apply c1/config/plan_overrides.json on top of the compiled plan.

The compiled plan is derived from the source JSON and is reproducible. Some port decisions are
not source facts — e.g. "this shell must be two-sided so the sun's shadow pass can see it" — and
overwriting the compiled output would lose that distinction on the next recompile. So overrides
are applied here, into a separate effective plan, and the reason travels with the override.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    plan_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out/materials_plan.json"
    over_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "config/plan_overrides.json"
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "out/materials_plan_effective.json"

    plan = json.loads(plan_path.read_text())
    ov = json.loads(over_path.read_text())

    rows = {r["mi"]: r for r in plan["rows"]}
    plan["overrides_applied"] = {}
    applied, missing = [], []

    for mi, why in ov.get("two_sided", {}).items():
        row = rows.get(mi)
        if row is None:
            missing.append(mi)
            continue
        row["two_sided"] = True
        row.setdefault("overrides", []).append({"kind": "two_sided", "reason": why})
        applied.append(mi)

    # Master defaults are part of the material, not of the instance. M_AlphaTest is BLEND_Masked
    # AND TwoSided, so every masked instance inheriting from it renders two-sided whether or not
    # the canonical says so. Rows the canonical does not mark double-sided go to the one-sided twin.
    split = ov.get("masked_master_split")
    if split:
        one = split["one_sided_master"]
        moved = []
        for row in plan["rows"]:
            if row.get("treatment") not in ("masked", "bake", "ownalpha"):
                continue
            if row.get("two_sided"):
                continue
            row["master"] = {"pkg": one["pkg"], "name": one["name"], "colour_param": one["colour_param"]}
            row.setdefault("overrides", []).append({
                "kind": "masked_master_split",
                "reason": split.get("_why", "canonical does not mark this material double-sided"),
            })
            moved.append(row["mi"])
        plan["overrides_applied"]["masked_master_split"] = len(moved)

    plan["overrides_applied"]["two_sided"] = applied

    # Rows the compiler could not match to a canonical material were copied straight from the
    # author's pak, untextured. Some of them are one suffix away from a real source material
    # (mat_mat_wall_siro2_sh_001 -> mat_mat_wall_siro2_sh); a rekey turns them into normal compiled
    # rows so they get a texture binding instead of falling back to the master's white default.
    rekey = ov.get("rekey")
    if rekey:
        src_path = ROOT / "source/merged.materials.json"
        src = json.loads(src_path.read_text())
        rekeyed = []
        for mi, spec in rekey.items():
            if mi.startswith("_"):
                continue
            row = rows.get(mi)
            key = spec.get("source_key")
            if row is None or key is None or key not in src:
                missing.append(mi)
                continue
            stage0 = (src[key].get("Stages") or [{}])[0]
            cmap = stage0.get("colorMap")
            base = None
            if cmap:
                stem = Path(cmap).name.rsplit(".", 1)[0]
                base = "".join(c if (c.isalnum() or c == "_") else "_" for c in stem)
            row["key"] = key
            row["treatment"] = "opaque"
            row["clip"] = None
            row["two_sided"] = bool(src[key].get("doubleSided"))
            row["master"] = {"pkg": "/Game/Env/Materials/Master/M_PropMaster", "name": "M_PropMaster", "colour_param": "BaseColor"}
            row["textures"] = {"base": base}
            row["texture_facts"] = {}
            row.setdefault("overrides", []).append({"kind": "rekey", "reason": spec.get("why", ""), "source_key": key})
            rekeyed.append(mi)
        plan["overrides_applied"]["rekey"] = rekeyed
    if missing:
        plan["overrides_missing"] = missing
    out_path.write_text(json.dumps(plan, indent=1))

    print(f"effective plan -> {out_path}")
    print(f"two_sided overrides applied: {len(applied)}")
    for mi in applied:
        print(f"  + {mi}")
    for mi in missing:
        print(f"  ! {mi} not in plan")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
