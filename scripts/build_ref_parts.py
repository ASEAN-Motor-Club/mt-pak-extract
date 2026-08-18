#!/usr/bin/env python3
"""Enrich ref_parts.json stats from OUR pipeline (mt-pak-extract).

The existing ref_parts.json (name / cost / mass / restrict / variant-key /
type structure) is correct and preserved. This script fills the gaps the
wiki review flagged against the old extractor output:

  1. Engine parts  -> merge the fully-resolved EngineProperty (StarterRPM,
                      FuelType, EngineType, HeatingPower, FrictionCoulombCoeff,
                      BlipDurationSeconds, IntakeSpeedEfficency,
                      MaxJakeBrakeStep, ...) from out/<EngineAsset>_parsed.json.
  2. LSD parts     -> merge ClutchPackAccel / ClutchPackBrake from the
                      resolved MTLSDDataAsset.
  3. Parts with no stats (Brake Pad, Coolant Radiator, Taxi License, ...)
                      -> emit their own inline struct (BrakePad / CoolantRadiator
                      / Taxi / ...) even at the editor default.

Anything already correct is left untouched, so we never regress variant rows.

Usage:
  python3 scripts/build_ref_parts.py [ref_parts.json] [out_dir] [--write]
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Per-type inline stat struct to fill when a part has no stats at all.
PER_TYPE_INLINE_STRUCTS = {
    'Angle Kit': ['AngleKit'],
    'Anti-roll Bar': ['AntiRollBar'],
    'Brake Balance': ['BrakeBalance'],
    'Brake Pad': ['BrakePad'],
    'Brake Power': ['BrakePower'],
    'Cargo Bed': ['CargoBed'],
    'Coolant Radiator': ['CoolantRadiator'],
    'Final Drive Ratio': ['FinalDriveRatio'],
    'Headlight': ['Headlight'],
    'Intake': ['Intake'],
    'Roof Rack': ['RoofRack'],
    'Suspension Damper': ['SuspensionDamper'],
    'Suspension Ride Height': ['SuspensionRideHeight'],
    'Suspension Spring': ['SuspensionSpring'],
    'Taxi License': ['Taxi'],
    'Trailer Hitch': ['TrailerHitch'],
    'Turbocharger': ['Turbocharger'],
    'Utility': ['ItemInventory', 'FuelTank'],
    'Wheel': ['Wheel'],
    'Wheel Spacer': ['WheelSpacer'],
    'Winch': ['Winch'],
}


def load_master(out_dir):
    """Return {RowName: [row, ...]} from the master VehicleParts table.

    Some part families (SmallRadiator, WheelSpacer, ...) carry multiple rows
    under the same RowName, each a distinct tuning variant. We keep them all.
    """
    for cand in (ROOT / "VehicleParts_parsed.json",
                 ROOT / "out" / "VehicleParts_parsed.json",
                 Path(out_dir) / "VehicleParts_parsed.json"):
        if cand.exists():
            data = json.loads(cand.read_text())
            break
    else:
        raise FileNotFoundError("VehicleParts_parsed.json not found")
    rows = data["Data"]["Rows"]
    if isinstance(rows, dict):
        rows = list(rows.values())
    out = defaultdict(list)
    for r in rows:
        out[r["RowName"]].append(r)
    return dict(out)


def load_pertype(out_dir):
    pertype = defaultdict(list)
    for f in sorted(os.listdir(out_dir)):
        if not f.endswith("_parsed.json"):
            continue
        try:
            data = json.loads((Path(out_dir) / f).read_text())
        except Exception:
            continue
        if data.get("Data", {}).get("Type") != "DataTable":
            continue
        rows = data["Data"]["Rows"]
        if isinstance(rows, dict):
            rows = list(rows.values())
        src = f[: -len("_parsed.json")]
        for r in rows:
            pertype[r["RowName"]].append((src, r))
    return pertype


def clean_struct(struct):
    if not isinstance(struct, dict):
        return struct
    out = {}
    for k, v in struct.items():
        if k == "_StructType":
            continue
        if v is None or v == "":
            continue
        if isinstance(v, dict) and ("_Type" in v or v.get("Type") in ("Import", "Export")):
            continue  # asset ref / map plumbing
        out[k] = v
    return out


def physics_assets(out_dir, asset):
    """Return the exported Properties dict of out/<asset>_parsed.json, or {}."""
    p = Path(out_dir) / f"{asset}_parsed.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    exports = data.get("Data", {}).get("Exports", [])
    for e in exports:
        props = e.get("Properties", {})
        if props:
            return props
    return {}


def resolve_engine_physics(out_dir, row):
    ea = row.get("EngineAsset")
    if not ea or ea == "None":
        return {}
    props = physics_assets(out_dir, ea)
    ep = props.get("EngineProperty", {})
    if isinstance(ep, dict) and ep.get("_StructType") == "MTEngineProperty":
        ep = dict(ep)
        ep.pop("_StructType", None)
        if isinstance(ep.get("TorqueCurve"), dict):
            ep.pop("TorqueCurve", None)
        return ep
    return {}


def resolve_lsd_physics(out_dir, row, variant_key):
    la = row.get("LSDAsset")
    if not la or la == "None":
        return {}
    # Variant LSD parts (LSD_Clutch_2_100) reference a suffixed physics asset
    # (2WayClutchPackLSD_100) even though the row's LSDAsset is the base name.
    m = re.search(r"_(\d+(?:\.\d+)?)$", variant_key)
    if m:
        cand = f"{la}_{m.group(1)}"
        if (Path(out_dir) / f"{cand}_parsed.json").exists():
            la = cand
    return physics_assets(out_dir, la)


def fill_inline_structs(type_name, row):
    """Emit the type's own inline tuning struct(s) even at editor default."""
    stats = {}
    wanted = PER_TYPE_INLINE_STRUCTS.get(type_name, [])
    for sk in wanted:
        sv = row.get(sk)
        if isinstance(sv, dict):
            cleaned = clean_struct(sv)
            if cleaned:
                stats[sk] = cleaned
    return stats


def pick_variant_row(base, rows, variant_suffix):
    """Among the duplicate master rows for `base`, pick the one whose tuning
    value encodes to the variant suffix (e.g. SmallRadiator_100 -> the row
    with CoolingPower 1.0, since CoolingPower*100 == 100).

    Returns the best-matching row, or the first row if no numeric match.
    """
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    try:
        suffix = float(variant_suffix)
    except (TypeError, ValueError):
        return rows[0]
    # Each row's candidate signature: the first tunable scalar field.
    best, best_err = rows[0], None
    for r in rows:
        for v in r.values():
            if isinstance(v, dict) and "_StructType" in v:
                for fv in v.values():
                    if isinstance(fv, (int, float)):
                        candidates = [fv, fv * 100, fv * 10]
                        for c in candidates:
                            err = abs(c - suffix)
                            if best_err is None or err < best_err:
                                best_err, best = err, r
                        break
                break
    return best


def main():
    write = "--write" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ref_path = Path(args[0]) if args else ROOT / "ref_parts.json"
    out_dir = Path(args[1]) if len(args) > 1 else ROOT / "out"

    ref = json.loads(ref_path.read_text())
    parts = ref["parts"]
    master = load_master(out_dir)

    changed = 0
    for key, part in parts.items():
        ptype = part.get("type")
        base = key if key in master else re.sub(r"_\d+(?:\.\d+)?$", "", key)
        rows = master.get(base)
        if not rows:
            continue

        m = re.search(r"_(\d+(?:\.\d+)?)$", key)
        variant_suffix = m.group(1) if m else None
        row = pick_variant_row(base, rows, variant_suffix) if len(rows) > 1 else rows[0]

        stats = part.get("stats") or {}

        # --- Engine: merge the fully-resolved physics (adds new fields) ---
        if ptype == "Engine":
            ep = resolve_engine_physics(out_dir, row)
            if ep:
                merged = dict(stats.get("engine") or {})
                merged.update(ep)
                if merged != stats.get("engine"):
                    stats["engine"] = merged
                    part["stats"] = stats
                    changed += 1
            continue

        # --- LSD: merge ClutchPackAccel / ClutchPackBrake ---
        if ptype == "LSD":
            lp = resolve_lsd_physics(out_dir, row, key)
            if lp:
                merged = dict(stats.get("lsd") or {})
                merged.update(lp)
                if merged != stats.get("lsd"):
                    stats["lsd"] = merged
                    part["stats"] = stats
                    changed += 1
            continue

        # --- Parts with no stats: fill their own inline struct ---
        if not stats:
            filled = fill_inline_structs(ptype, row)
            if filled:
                part["stats"] = filled
                changed += 1

    print(f"Updated stats for {changed} parts out of {len(parts)}")
    if write:
        ref_path.write_text(json.dumps(ref, indent=1, ensure_ascii=False))
        print(f"Wrote {ref_path}")


if __name__ == "__main__":
    main()
