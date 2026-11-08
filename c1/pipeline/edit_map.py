"""Editor-side authoring for the C1 map (run inside D:\\UEProjects\\C1).

Does actor/level edits only. It deliberately does NOT set ChildActorClass or
DefaultGameMode: setting a child class makes the editor instantiate the child
actor, which cook then bakes as a real export, and the game dies on load with
UObjectArchetype.cpp:175 RF_NeedLoad. Those three references are restored after
cook by pipeline/repair_class_refs.sh instead.

Usage:
    UnrealEditor-Cmd.exe <C1.uproject> -run=pythonscript -script=<this file>
"""
import json
import unreal

MAP = "/Game/Mods/C1/Maps/C1"
SKY_Z = 300000.0          # geometry tops out at Z 121,200
REPORT = r"D:\C1Mirror\edit_map.json"

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out = {"steps": []}


def step(k, v):
    out["steps"].append([k, str(v)])


les.load_level(MAP)

for a in eas.get_all_level_actors():
    if a.get_actor_label() == "BP_C1_Sky":
        t = a.get_actor_transform()
        t.translation.z = SKY_Z
        a.set_actor_transform(t, False, False)
        step("sky_z", a.get_actor_transform().translation.z)

step("saved", bool(les.save_current_level()))
open(REPORT, "w").write(json.dumps(out, indent=1))
