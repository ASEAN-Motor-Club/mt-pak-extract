import unreal, json

ar = unreal.AssetRegistryHelpers.get_asset_registry()
assets = ar.get_assets_by_path("/Game/Mods/C1/Meshes", recursive=False)

rows = []
for a in assets:
    name = str(a.asset_name)
    rec = {"name": name}
    try:
        m = unreal.load_asset(str(a.package_name) + "." + name)
        if m is None:
            rec["error"] = "load failed"
            rows.append(rec); continue
        rec["tris"] = int(m.get_num_triangles(0)) if hasattr(m, "get_num_triangles") else -1
        b = m.get_bounds()
        o = b.origin; e = b.box_extent
        rec["origin"] = [round(o.x), round(o.y), round(o.z)]
        rec["extent"] = [round(e.x), round(e.y), round(e.z)]
        rec["mats"] = len(m.get_editor_property("static_materials"))
        rec["collision"] = str(m.get_editor_property("body_setup").get_editor_property("collision_trace_flag"))
    except Exception as ex:
        rec["error"] = str(ex)[:120]
    rows.append(rec)

rows.sort(key=lambda r: r.get("tris", -1))
empty = [r for r in rows if r.get("tris", 0) <= 0 or "error" in r]
unreal.log("C1VERIFY total=%d empty=%d" % (len(rows), len(empty)))
for r in rows[:12]:
    unreal.log("C1VERIFY LOW %s" % json.dumps(r))
for r in rows[-5:]:
    unreal.log("C1VERIFY HIGH %s" % json.dumps(r))
