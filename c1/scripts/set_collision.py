import unreal, json

MESH_DIR = "/Game/Mods/C1Full/Meshes"
FLAG = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE

reg = unreal.AssetRegistryHelpers.get_asset_registry()
names = [a.asset_name for a in reg.get_assets_by_path(MESH_DIR, True)]
done = 0
failed = []

for n in names:
    path = "%s/%s" % (MESH_DIR, n)
    sm = unreal.EditorAssetLibrary.load_asset(path)
    if sm is None:
        failed.append([str(n), "load"])
        continue
    try:
        body = sm.get_editor_property("body_setup")
    except Exception as e:
        failed.append([str(n), "body:%s" % e])
        continue
    if body is None:
        failed.append([str(n), "no_body"])
        continue
    try:
        body.set_editor_property("collision_trace_flag", FLAG)
        unreal.EditorAssetLibrary.save_loaded_asset(sm, only_if_is_dirty=False)
        done += 1
    except Exception as e:
        failed.append([str(n), "apply:%s" % e])

out = {"meshes": len(names), "collision_set": done, "failed": failed[:20],
       "failed_count": len(failed)}
open(r"D:\set_collision.json", "w").write(json.dumps(out, indent=1))
unreal.log("SET_COLLISION_DONE %d/%d failed=%d" % (done, len(names), len(failed)))
