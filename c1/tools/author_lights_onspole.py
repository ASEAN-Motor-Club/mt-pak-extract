"""P0c: 12 lamps that are PROVABLY mounted on pole geometry.

Selection rule: nearest lamp-material head within 1.5 m in XY and 1.5 m in Z, so each light
sits on a fitting (measured 0.03-0.78 m). All within 28-106 m of the Shibaura spawn.

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
  "name": "onspole_PointLight_5766",
  "ue_cm": [
   112400.3,
   -469144.1,
   88754.1
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_5767",
  "ue_cm": [
   112653.0,
   -472930.3,
   88599.9
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_6630",
  "ue_cm": [
   110397.8,
   -474695.5,
   89280.9
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_5768",
  "ue_cm": [
   112640.3,
   -475164.1,
   88511.2
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_6631",
  "ue_cm": [
   110456.0,
   -465898.4,
   89369.3
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_5765",
  "ue_cm": [
   112424.6,
   -465582.5,
   88895.0
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_6629",
  "ue_cm": [
   110385.5,
   -477377.1,
   89254.5
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_5769",
  "ue_cm": [
   112346.0,
   -477967.1,
   88409.3
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_6632",
  "ue_cm": [
   110794.9,
   -461567.8,
   89407.0
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_5764",
  "ue_cm": [
   112444.9,
   -461574.8,
   89054.9
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_6628",
  "ue_cm": [
   110364.6,
   -480698.6,
   89220.9
  ],
  "yaw": 0.0,
  "group": "streetlamps"
 },
 {
  "name": "onspole_PointLight_5770",
  "ue_cm": [
   112227.5,
   -481279.5,
   88341.9
  ],
  "yaw": 0.0,
  "group": "streetlamps"
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
