import unreal, json

MESH_DIR = "/Game/Mods/C1Full/Meshes"
SAMPLE = ["c0_-1", "c-10_-22", "c-16_-33", "c5_7", "c-3_-40"]

reg = unreal.AssetRegistryHelpers.get_asset_registry()
subs = unreal.StaticMeshEditorSubsystem()
out = {"samples": [], "summary": {}}

names = [a.asset_name for a in reg.get_assets_by_path(MESH_DIR, True)]
total = 0
with_simple = 0
with_complex_as_simple = 0
with_any_body = 0

for n in names:
    path = "%s/%s" % (MESH_DIR, n)
    sm = unreal.EditorAssetLibrary.load_asset(path)
    if sm is None:
        continue
    total += 1
    try:
        simple = subs.get_simple_collision_count(sm)
    except Exception:
        simple = -1
    try:
        body = sm.get_editor_property("body_setup")
    except Exception:
        body = None
    flag = None
    if body is not None:
        with_any_body += 1
        try:
            flag = str(body.get_editor_property("collision_trace_flag"))
        except Exception:
            flag = "?"
    if simple > 0:
        with_simple += 1
    if flag and "COMPLEX_AS_SIMPLE" in flag.upper():
        with_complex_as_simple += 1
    if str(n) in SAMPLE or len(out["samples"]) < 5:
        out["samples"].append({"mesh": str(n), "simple": simple,
                               "body": body is not None, "flag": flag})

out["summary"] = {"meshes": total, "with_simple_collision": with_simple,
                  "with_body_setup": with_any_body,
                  "complex_as_simple": with_complex_as_simple}
open(r"D:\probe_col.json", "w").write(json.dumps(out, indent=1))
unreal.log("PROBE_COL_DONE %s" % json.dumps(out["summary"]))
