#!/usr/bin/env python3
"""Build the corridor rows file the light author script consumes.

Source of truth: c1/source/c1_source_lights.json (from extract_source_lights.py, which reads the
BeamNG missiongroup items.level.json files).

Two rules that exist because ignoring them shipped wrong lights:

1. PLACEHOLDERS ARE NOT LAMPS. The source level has 1,116 `sign_lights` objects carrying only a
   position and texSize — no brightness, no range, no colour, no cone angles, and `isEnabled=false`
   on every one. They are inert markers. Authoring them with the class default turned 356 corridor
   rows into 62,832 lm white point lights that blew out every sign they sat next to.
   A row is kept only if it carries at least one photometric value.

2. EVERY KEPT ROW MUST CARRY ITS OWN RANGE. If a row arrives without `range_m`, do not default it —
   fail, because a silent default radius is indistinguishable from a real one in the histogram.

Field names here are the author script's contract: ue_cm, brightness, src_range_m, inner_deg,
outer_deg, src_color.
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source/c1_source_lights.json"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/data/cache/scratch/c1/corridor_rows.json")

PHOTOMETRIC = ("brightness", "range_m", "color", "inner_deg", "outer_deg")

# The source level's 1,116 `sign_lights` objects carry only position + texSize: no brightness, no
# range, no colour, no cone. They are NOT inert — levels/c1/mainlevel.lua has a partition-grid
# manager (`enableLights`, 384 m cells) that calls setLightEnabled on the sign_lights group, so in
# BeamNG they run on PointLight class defaults.
#
# Porting them at the legacy default (brightness 1 ~= 62,832 lm, the isotropic equivalent of a
# 5000 cd spot) blows out every sign they sit beside in UE. BeamNG's own guidance for a point light
# of this kind is 400-1000 lm at radius 5-12 m, so that is what a value-less sign light gets here.
SIGN_DEFAULT_LM = 800.0
SIGN_DEFAULT_RADIUS_M = 8.0


def main() -> int:
    src = json.loads(SRC.read_text())
    rows, skipped = [], []
    for light in src["lights"]:
        if not light.get("in_corridor"):
            continue
        if not any(light.get(k) is not None for k in PHOTOMETRIC):
            skipped.append(light)
            rows.append({
                "name": light["name"],
                "group": light["group"],
                "ue_cm": light["ue_cm"],
                "brightness": None,
                "src_range_m": light.get("range_m") or SIGN_DEFAULT_RADIUS_M,
                "inner_deg": light.get("inner_deg"),
                "outer_deg": light.get("outer_deg"),
                "src_color": light.get("color") or [1.0, 0.94, 0.86, 1.0],
                "sign_default": True,
            })
            continue
        rows.append({
            "name": light["name"],
            "group": light["group"],
            "ue_cm": light["ue_cm"],
            "brightness": light.get("brightness"),
            "src_range_m": light.get("range_m"),
            "inner_deg": light.get("inner_deg"),
            "outer_deg": light.get("outer_deg"),
            "src_color": light.get("color"),
        })

    missing_range = [r["name"] for r in rows if r["src_range_m"] is None]
    if missing_range:
        print(f"FAIL: {len(missing_range)} kept rows have no range: {missing_range[:5]}", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows))
    print(f"rows {len(rows)} {dict(collections.Counter(r['group'] for r in rows))}")
    print(f"value-less sign lamps given documented defaults: {len(skipped)} "
          f"{dict(collections.Counter(s['group'] for s in skipped))}")
    print(f"no brightness (source class default applies): {sum(1 for r in rows if r['brightness'] is None)}")
    print(f"no colour: {sum(1 for r in rows if r['src_color'] is None)}")
    print(f"range histogram: {collections.Counter(r['src_range_m'] for r in rows).most_common(6)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
