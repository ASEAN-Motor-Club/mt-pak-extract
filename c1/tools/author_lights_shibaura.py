"""P0b: 12 lamps clustered around the Shibaura spawn (4.6-18 m away).

The first P0 run placed 3 lamps at c1_20 / c-1_18 / c4_15 — hundreds of metres from spawn —
so "no lights visible" was a false negative, not a broken light. These sit where the player
actually stands at map load.

Rows are EMBEDDED (same convention as author_traffic_spawner.py — a sibling JSON is not read).

Idempotent: every actor whose label starts with C1Lamp_ is destroyed before spawning, so a
second run cannot double the lamp count.

Positions come from c1/source/c1_source_lights.json (corridor lamps), converted with the one
rule: ue_cm = (x*100, -y*100, z*100) from the source's BeamNG metres. The Y negation is the
map's mirror — the same rule that made the P22 actors need a 180 deg yaw correction.
"""
import json
import os
import traceback

import unreal

LEVEL = os.environ.get("C1_LEVEL", "/Game/Mods/C1Full/Maps/C1Full_Roads")
REPORT = os.environ.get("C1_AUTHOR_REPORT", "D:/C1FullMirror/Scripts/author_lights.json")
LAMP_BP = "/Game/Mods/C1Full/Blueprints/BP_C1_Lamp.BP_C1_Lamp_C"
LABEL_PREFIX = "C1Lamp_"

# P0 test rows: one loop lamp (c1_20), one tunnel lamp (c-1_18), one from the densest pocket
# (c4_15, 19 lamps within 20 m).
ROWS = json.loads(r"""
[
 {
  "name": "shibaura_PointLight_7223",
  "ue_cm": [
   110291.7,
   -470443.9,
   87990.0
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 4.6
 },
 {
  "name": "shibaura_PointLight_7189",
  "ue_cm": [
   110746.4,
   -470949.0,
   87990.7
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 5.1
 },
 {
  "name": "shibaura_PointLight_7222",
  "ue_cm": [
   110305.5,
   -471445.6,
   87978.8
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 5.5
 },
 {
  "name": "shibaura_PointLight_7215",
  "ue_cm": [
   109299.3,
   -470865.3,
   87940.3
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 9.4
 },
 {
  "name": "shibaura_PointLight_7190",
  "ue_cm": [
   111181.9,
   -470444.8,
   88001.8
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 10.5
 },
 {
  "name": "shibaura_PointLight_7191",
  "ue_cm": [
   110742.6,
   -469939.3,
   88001.2
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 10.9
 },
 {
  "name": "shibaura_PointLight_7188",
  "ue_cm": [
   111191.5,
   -471454.6,
   87991.6
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 11.0
 },
 {
  "name": "shibaura_PointLight_7187",
  "ue_cm": [
   110753.5,
   -471944.8,
   87979.7
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 11.6
 },
 {
  "name": "shibaura_PointLight_7224",
  "ue_cm": [
   110301.5,
   -469433.1,
   88000.9
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 14.7
 },
 {
  "name": "shibaura_PointLight_7221",
  "ue_cm": [
   110313.1,
   -472449.7,
   87967.4
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 15.5
 },
 {
  "name": "shibaura_PointLight_7192",
  "ue_cm": [
   111200.3,
   -469440.6,
   88012.1
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 17.5
 },
 {
  "name": "shibaura_PointLight_7186",
  "ue_cm": [
   111185.4,
   -472453.8,
   87981.1
  ],
  "yaw": 0.0,
  "group": "streetlamps",
  "src_dist_m": 18.2
 }
]
""")


def log(m):
    unreal.log("[C1LIGHTS] " + str(m))


out = {"placed": 0, "failed": 0, "deleted": 0, "first": None, "last": None, "errors": []}

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

les.load_level(LEVEL)
log("level loaded: " + LEVEL)

lamp_cls = unreal.load_class(None, LAMP_BP)
if lamp_cls is None:
    out["errors"].append("BP class not found: " + LAMP_BP)
else:
    log("lamp class: %s" % lamp_cls)

    # idempotent: clear our own previous output
    for actor in eas.get_all_level_actors():
        try:
            label = actor.get_actor_label()
        except Exception:
            continue
        if label.startswith(LABEL_PREFIX):
            eas.destroy_actor(actor)
            out["deleted"] += 1
    log("deleted %d previous lamps" % out["deleted"])

    for row in ROWS:
        try:
            x, y, z = row["ue_cm"]
            loc = unreal.Vector(float(x), float(y), float(z))
            rot = unreal.Rotator(0.0, float(row.get("yaw", 0.0)), 0.0)
            actor = eas.spawn_actor_from_class(lamp_cls, loc, rot)
            if actor is None:
                raise RuntimeError("spawn returned None")
            actor.set_actor_label(LABEL_PREFIX + row["name"])
            # P0 only: light ON so the lamp is visible in-game without the manager/night gate
            comp = actor.get_component_by_class(unreal.SpotLightComponent)
            if comp is not None:
                comp.set_editor_property("visible", True)
                try:
                    comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
                except Exception:
                    pass
            else:
                out["errors"].append(row["name"] + ": no SpotLightComponent on the instance")
            out["placed"] += 1
            if out["first"] is None:
                out["first"] = row["name"]
            out["last"] = row["name"]
        except Exception:
            out["failed"] += 1
            out["errors"].append(row.get("name", "?") + ": " + traceback.format_exc()[-400:])

    les.save_current_level()
    log("saved current level")

out["summary"] = "AUTHORED placed=%d failed=%d deleted=%d" % (
    out["placed"], out["failed"], out["deleted"])
with open(REPORT, "w") as f:
    json.dump(out, f, indent=1)
print(out["summary"])
