import json
import time
import unreal

LEVEL = "/Game/Mods/C1Full/Maps/C1Full"
OUT = r"D:\probe_spline.json"

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
les.load_level(LEVEL)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

acts = []
for _ in range(60):
    time.sleep(2)
    acts = [a for a in eas.get_all_level_actors()
            if a.get_class().get_name() == "MotorTownRoad"]
    if acts:
        break

res = {"roads": len(acts), "detail": []}
for a in acts[:4]:
    d = {"label": a.get_actor_label(),
         "loc": [round(v / 100.0, 1) for v in (a.get_actor_location().x,
                                               a.get_actor_location().y,
                                               a.get_actor_location().z)]}
    for c in a.get_components_by_class(unreal.SplineComponent):
        try:
            n = c.get_number_of_spline_points()
            d["points"] = n
            if n:
                for space, tag in ((unreal.SplineCoordinateSpace.WORLD, "world"),
                                   (unreal.SplineCoordinateSpace.LOCAL, "local")):
                    p0 = c.get_location_at_spline_point(0, space)
                    pn = c.get_location_at_spline_point(n - 1, space)
                    d[tag] = [[round(p0.x / 100.0, 1), round(p0.y / 100.0, 1), round(p0.z / 100.0, 1)],
                              [round(pn.x / 100.0, 1), round(pn.y / 100.0, 1), round(pn.z / 100.0, 1)]]
        except Exception as e:
            d["err"] = str(e)
    res["detail"].append(d)

unreal.log("SPLINE " + json.dumps(res))
with open(OUT, "w") as f:
    json.dump(res, f, indent=1)
