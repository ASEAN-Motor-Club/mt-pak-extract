import unreal

LOG_FILE = 'D:/UEProjects/assign_material.log'

def log(msg):
    with open(LOG_FILE, 'a') as f:
        f.write(msg + '\n')

def main():
    open(LOG_FILE, 'w').close()
    log("=== Assign Material Slot Name ===")
    
    mesh_path = '/Game/Models/MyMod/Meshes/SM_MoneyPallet_5'
    
    # Scan to register our mesh
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    reg.scan_paths_synchronous(['/Game/Models/MyMod/Meshes'], True)
    
    # Load our mesh
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if not mesh:
        log(f"ERROR: Could not load {mesh_path}")
        return
    log(f"Loaded mesh: {mesh.get_name()}")
    
    # Get current materials
    mats = mesh.get_editor_property('static_materials')
    log(f"Current materials: {len(mats) if mats else 0}")
    
    # Create new material slot with correct name and material path reference
    new_materials = unreal.Array(unreal.StaticMaterial)
    sm = unreal.StaticMaterial()
    # Set the slot name to match the game's material instance name
    sm.set_editor_property('material_slot_name', unreal.Name('MI_PolygonHeist_01_A'))
    # Don't set material_interface — leave it None so the game resolves by name
    new_materials.append(sm)
    mesh.set_editor_property('static_materials', new_materials)
    
    # Save
    unreal.EditorAssetLibrary.save_asset(mesh_path, True)
    log("SUCCESS: Material slot named MI_PolygonHeist_01_A")
    log("NOTE: The game should resolve this material at runtime from its own PAKs")

if __name__ == '__main__':
    main()
