"""Place a NATIVE unreal.SpotLight at Shibaura spawn — independent of BP_C1_Lamp.

Why: the BP-based lamp is fully configured (Intensity 20000, Mobility=2, bVisible=true,
bAffectsWorld=true) and still renders nothing. A native spot light actor has no blueprint
construction path at all: if this one lights the road, the defect is in BP_C1_Lamp; if it
does not, the level/materials are the problem and no lamp will ever work.

Placed 8 m above the PlayerStart so the player spawns underneath it.
"""
import os
import traceback

import unreal

LEVEL = "/Game/Mods/C1Full/Maps/C1Full_Roads"
REPORT = "D:/C1FullMirror/Scripts/author_native_lights.json"
LABEL_PREFIX = "C1NativeLight_"

# Shibaura PlayerStart (P22): 110237, -470902, 87411 -> light 8 m up
SPOTS = [
    {"name": "spawn", "loc": (110237.0, -470902.0, 88211.0)},
]

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

out = {"deleted": 0, "placed": 0, "errors": [], "actors": []}


def log(m):
    unreal.log("[C1NATIVELIGHT] " + str(m))


les.load_level(LEVEL)
log("level loaded: " + LEVEL)

# idempotent
for a in eas.get_all_level_actors():
    try:
        if a.get_actor_label().startswith(LABEL_PREFIX):
            eas.destroy_actor(a)
            out["deleted"] += 1
    except Exception:
        pass

for spot in SPOTS:
    try:
        actor = eas.spawn_actor_from_class(unreal.SpotLight, unreal.Vector(*spot["loc"]),
                                           unreal.Rotator(roll=0.0, pitch=-90.0, yaw=0.0))
        actor.set_actor_label(LABEL_PREFIX + spot["name"])
        comp = actor.light_component
        comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        comp.set_editor_property("intensity", 20000.0)
        comp.set_editor_property("attenuation_radius", 2000.0)
        comp.set_editor_property("inner_cone_angle", 25.0)
        comp.set_editor_property("outer_cone_angle", 170.0)
        comp.set_editor_property("cast_shadows", False)
        comp.set_editor_property("light_color", unreal.Color(r=255, g=100, b=0, a=255))
        out["placed"] += 1
        out["actors"].append({
            "label": LABEL_PREFIX + spot["name"],
            "class": str(actor.get_class().get_name()),
            "component": str(comp.get_class().get_name()),
            "intensity": str(comp.get_editor_property("intensity")),
            "mobility": str(comp.get_editor_property("mobility")),
            "pitch": str(comp.get_editor_property("relative_rotation").pitch),
        })
    except Exception:
        out["errors"].append({"spot": spot["name"], "err": traceback.format_exc()})

les.save_current_level()
out["summary"] = "NATIVELIGHT placed=%d deleted=%d errors=%d" % (
    out["placed"], out["deleted"], len(out["errors"]))

import json
with open(REPORT, "w") as f:
    json.dump(out, f, indent=1)
print(out["summary"])
for a in out["actors"]:
    print("  ", a)
for e in out["errors"]:
    print("  ERR", e["spot"], e["err"].splitlines()[-1])
