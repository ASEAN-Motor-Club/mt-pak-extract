"""Delete every MotorTownRaceSection actor from the level.

They carry no component, so their transform is the only thing placing them and all
40 sat at (0,0,0) -- stacked at the origin. Not needed for the map, so remove them
rather than guess transforms.
"""
import time
import unreal

LEVEL = "/Game/Mods/C1Full/Maps/C1Full"
LOG = r"D:\remove_sections.log"

def log(m):
    unreal.log("RSEC " + str(m))
    with open(LOG, "a") as f:
        f.write(str(m) + "\n")

def main():
    open(LOG, "w").close()
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(LEVEL)

    acts = []
    for _ in range(60):
        time.sleep(2)
        acts = [a for a in eas.get_all_level_actors()
                if a.get_class().get_name() == "MotorTownRaceSection"]
        if acts:
            break
    log("found=%d" % len(acts))

    removed = 0
    for a in acts:
        try:
            eas.destroy_actor(a)
            removed += 1
        except Exception as e:
            log("destroy_fail=%s %s" % (a.get_actor_label(), e))
    log("destroyed=%d" % removed)
    les.save_current_level()

    left = [a.get_actor_label() for a in eas.get_all_level_actors()
            if a.get_class().get_name() == "MotorTownRaceSection"]
    log("GATE remaining=%d -> %s" % (len(left), "RSEC_OK" if not left else "RSEC_FAIL"))
    if left:
        log("left_sample=%s" % left[:5])

main()
