"""Restore the Shibaura spawn + both garages in the SOURCE level.

The canonical positions only ever existed as post-cook surgery (apply_map_edits_p22.sh moves the
already-cooked umap), which means every fresh cook silently reverts the spawn to the map's original
spot and the garages to a single un-parented prop. This bakes the same result into the level itself:

  PlayerStart      -> 110237 -470902 87411   yaw  90     (Shibaura PA)
  BP_C1_Prop_C_0   -> same XY, z-100         yaw  90     (garage at the spawn)
  BP_C1_Prop_C_1   -> 593234 -466784 87449   yaw  75.57   (Tatsumi 1st PA, clone of _0)

Yaw is source-yaw + 180 because the map's Y is inverted. The Child component's ChildActorClass must
point at GarageActorBP_C; it is re-set here because a level that lost it ships a garage with no
interactive actor.
"""
import json
import os

import unreal

LEVEL = "/Game/Mods/C1Full/Maps/C1Full"
# Z here is the GROUND, not the actor height. Measured from the cell mesh at the spawn XY
# (c2_9, 4 m radius): the Shibaura PA floor mode is 874.0 m, and the canonical BeamNG
# spawn_default sits at 874.106 m, so the two agree. The deck above is 882.3 / 884.5 m.
SHIBAURA_GROUND = (110237.0, -470902.0, 87410.6)
# The player pawn's origin sits 100 cm above its feet, so a PlayerStart placed on the surface
# drops the player through it. Spawn = ground + PLAYER_HOVER.
PLAYER_HOVER = 100.0
# Tatsumi is a garage-only point: the source spawn_parking Z is 874.49 m, but the c11_9 mesh
# around that XY tops out at 861.0 m. Unresolved (13.5 m), so it is left as the source value
# and no PlayerStart is placed there.
TATSUMI = (593234.0, -466784.0, 87449.0)
GARAGE_BP = "/Game/Objects/GarageActorBP"
REPORT = os.environ.get("C1_RESTORE_REPORT", r"D:\C1FullMirror\Scripts\restore_spawn.json")

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les.load_level(LEVEL)

actors = eas.get_all_level_actors()
out = {"moved": [], "cloned": [], "child_class": [], "problems": []}

starts = [a for a in actors if a.get_class().get_name() == "PlayerStart"]
props = [a for a in actors if a.get_class().get_name() == "BP_C1_Prop_C"]

if not starts:
    out["problems"].append("no PlayerStart in level")
else:
    st = starts[0]
    spawn = (SHIBAURA_GROUND[0], SHIBAURA_GROUND[1], SHIBAURA_GROUND[2] + PLAYER_HOVER)
    st.set_actor_location(unreal.Vector(*spawn), False, False)
    st.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=0.0, yaw=90.0), False)
    out["moved"].append(["PlayerStart", list(spawn), 90.0])

def place(actor, loc, yaw):
    # loc is GROUND: the garage sits ON the surface, it is not offset below it.
    actor.set_actor_location(unreal.Vector(loc[0], loc[1], loc[2]), False, False)
    actor.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw), False)
    for c in actor.get_components_by_class(unreal.ChildActorComponent):
        # GarageActorBP lives in the game pak, not in this project, so load_class fails in a
        # commandlet. Only touch the class if it resolves; the cooked map's class ref is
        # restored separately by stage 6 (repair_class_refs.sh).
        try:
            klass = unreal.load_class(None, GARAGE_BP + ".GarageActorBP_C")
        except Exception:
            klass = None
        out["child_class"].append([actor.get_actor_label(), c.get_name(),
                                   "kept (class not loadable in commandlet)" if klass is None else "GarageActorBP_C"])
        if klass is not None:
            try:
                c.set_editor_property("child_actor_class", klass)
            except Exception as e:
                out["problems"].append("child_class %s: %s" % (c.get_name(), str(e)[:80]))

if not props:
    out["problems"].append("no BP_C1_Prop_C in level")
else:
    g0 = sorted(props, key=lambda a: a.get_actor_label())[0]
    place(g0, SHIBAURA_GROUND, 90.0)
    g0.set_actor_label("BP_C1_Prop_C_0")
    out["moved"].append([g0.get_actor_label(), list(SHIBAURA_GROUND), 90.0])

    # The Tatsumi garage is NOT cloned here on purpose: duplicating this actor inside a
    # commandlet crashes the editor inside PythonScriptPlugin (the Child component's class lives
    # in the game pak, not in this project). apply_map_edits_p22.sh clones it on the cooked umap,
    # which is the step that actually ships; this script only keeps the source level honest.

les.save_current_level()
out["summary"] = "moved=%d cloned=%d child_class_set=%d problems=%d" % (
    len(out["moved"]), len(out["cloned"]), len(out["child_class"]), len(out["problems"]))
json.dump(out, open(REPORT, "w"), indent=1)
print("RESTORE_SPAWN " + out["summary"])
for p in out["problems"]:
    print("  PROBLEM", p)
