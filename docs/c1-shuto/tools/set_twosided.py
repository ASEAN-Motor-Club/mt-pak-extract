import unreal

TWO_SIDED = True
changed = []
checked = 0

ar = unreal.AssetRegistryHelpers.get_asset_registry()
assets = ar.get_assets_by_path("/Game/Mods/C1/Materials", recursive=True)
for a in assets:
    cls = str(a.asset_class_path.asset_name)
    if cls != "Material":
        continue          # instances inherit from masters
    checked += 1
    path = str(a.package_name)
    name = str(a.asset_name)
    full = path + "." + name
    try:
        m = unreal.load_asset(full)
        if m is None:
            continue
        cur = m.get_editor_property("two_sided")
        if cur != TWO_SIDED:
            m.set_editor_property("two_sided", TWO_SIDED)
            unreal.EditorAssetLibrary.save_loaded_asset(m, False)
            changed.append(name)
    except Exception as e:
        unreal.log("C1TWOSIDED ERR %s %s" % (name, e))

unreal.log("C1TWOSIDED checked=%d changed=%d %s" % (checked, len(changed), ",".join(changed[:12])))
