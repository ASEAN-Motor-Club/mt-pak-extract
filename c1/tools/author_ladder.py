"""Brightness ladder: four NATIVE spot lights at known on-pole positions, one intensity each.

Runtime tuning is unreliable here (SetLightColor reads a Lua table as zero -> black; property
writes are silent no-ops), so bake the comparison instead: the player walks the road from spawn
and reports which lamp looks right. Native actors keep per-actor component values reliably, which
is the one thing that has worked every time.

Positions are the on-pole lamps from the P0c set (each within 0.8 m of lamp-head geometry),
distances 27.9 / 31.5 / 38.0 / 50.1 m from the Shibaura spawn.
"""
import json
import traceback

import unreal

LEVEL = "/Game/Mods/C1Full/Maps/C1Full_Roads"
REPORT = "D:/C1FullMirror/Scripts/author_ladder.json"
LABEL = "C1Ladder_"

# (label, ue_cm from source, intensity)
LADDER = [
    ("A_60k",    (110746.4, -470949.0, 87990.7), 60000.0),
    ("B_200k",   (110305.5, -471445.6, 87978.8), 200000.0),
    ("C_600k",   (109299.3, -470865.3, 87940.3), 600000.0),
    ("D_2M",     (111181.9, -470444.8, 88001.8), 2000000.0),
]

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out = {"placed": 0, "deleted": 0, "errors": [], "actors": []}

les.load_level(LEVEL)
for a in eas.get_all_level_actors():
    try:
        if a.get_actor_label().startswith(LABEL):
            eas.destroy_actor(a)
            out["deleted"] += 1
    except Exception:
        pass

for label, loc, inten in LADDER:
    try:
        actor = eas.spawn_actor_from_class(unreal.SpotLight, unreal.Vector(*loc),
                                           unreal.Rotator(roll=0.0, pitch=-90.0, yaw=0.0))
        actor.set_actor_label(LABEL + label)
        c = actor.light_component
        c.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        c.set_editor_property("intensity", inten)
        c.set_editor_property("attenuation_radius", 4000.0)
        c.set_editor_property("inner_cone_angle", 20.0)
        c.set_editor_property("outer_cone_angle", 60.0)
        c.set_editor_property("cast_shadows", False)
        c.set_editor_property("light_color", unreal.Color(r=255, g=214, b=170, a=255))
        out["placed"] += 1
        out["actors"].append({"label": label, "intensity": inten,
                              "z": round(loc[2], 1),
                              "readback": str(c.get_editor_property("intensity"))})
    except Exception:
        out["errors"].append({"label": label, "err": traceback.format_exc().splitlines()[-1]})

les.save_current_level()
out["summary"] = "LADDER placed=%d deleted=%d errors=%d" % (out["placed"], out["deleted"], len(out["errors"]))
json.dump(out, open(REPORT, "w"), indent=1)
print(out["summary"])
for a in out["actors"]:
    print("  ", a)
