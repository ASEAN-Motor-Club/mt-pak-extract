#!/usr/bin/env python3
"""Build the WHOLE-MAP light rows file the light author script consumes.

Same contract as build_corridor_rows.py (ue_cm, brightness, src_range_m, inner_deg, outer_deg,
src_color, sign_default) but with no corridor filter: every light in the source level.

Rules carried from the corridor pass, because each one was learned the hard way:

1. SPOT lights (streetlamps 8,087 + tunnel 1,148) carry range 20 m and a cone; brightness is
   2 / 1.5 / 0.3 or absent. Absent brightness means the source class default, which the port
   expresses as brightness 1.0 -> 5,000 cd (BeamNG: 1 brightness ~= 5,000 cd spot).
2. POINT lights (sign_lights 1,116 + rainbow_bridge 123) carry NO range and NO cone, and mostly
   no brightness. BeamNG runs them on PointLight class defaults via mainlevel.lua's partition
   manager, but the legacy default (~62,832 lm) is ~60x too bright for a small fixture. They get
   the documented small-point-light default (800 lm / 8 m) and keep their source colour, which is
   the only photometric-ish thing they actually declare (rainbow_bridge = green).
3. NEVER default a missing range for a spot: fail instead. A silent default radius is
   indistinguishable from a real one in the histogram, and range is the only thing that controls
   where a lamp is visible.
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source/c1_source_lights.json"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/data/cache/scratch/c1/map_rows.json")

POINT_DEFAULT_LM = 800.0
POINT_DEFAULT_RADIUS_M = 8.0
WARM_WHITE = [1.0, 0.94, 0.86, 1.0]


def main() -> int:
    src = json.loads(SRC.read_text())
    rows = []
    for light in src["lights"]:
        is_point = light.get("class") == "PointLight"
        row = {
            "name": light["name"],
            "group": light["group"],
            "ue_cm": light["ue_cm"],
            "inner_deg": light.get("inner_deg"),
            "outer_deg": light.get("outer_deg"),
        }
        if is_point:
            row.update({
                "brightness": None,
                "src_range_m": light.get("range_m") or POINT_DEFAULT_RADIUS_M,
                "src_color": light.get("color") or WARM_WHITE,
                "sign_default": True,
            })
        else:
            row.update({
                "brightness": light.get("brightness"),
                "src_range_m": light.get("range_m"),
                "src_color": light.get("color"),
                "sign_default": False,
            })
        rows.append(row)

    missing_range = [r["name"] for r in rows if r["src_range_m"] is None]
    if missing_range:
        print(f"FAIL: {len(missing_range)} rows have no range: {missing_range[:5]}", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows))
    print(f"rows {len(rows)} {dict(collections.Counter(r['group'] for r in rows))}")
    print(f"point lights on documented default (800 lm/8 m): {sum(1 for r in rows if r['sign_default'])}")
    print(f"spot without brightness (source class default -> 5,000 cd): "
          f"{sum(1 for r in rows if not r['sign_default'] and r['brightness'] is None)}")
    print(f"range histogram: {collections.Counter(r['src_range_m'] for r in rows).most_common(4)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
