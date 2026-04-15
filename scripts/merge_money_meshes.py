import unreal

LOG_FILE = 'D:/UEProjects/merge_mesh.log'

STACK_H = 8.0  # UE units (cm)
GAP = 0.5

def log(msg):
    with open(LOG_FILE, 'a') as f:
        f.write(msg + '\n')

def main():
    open(LOG_FILE, 'w').close()
    log("=== Merge Money Meshes ===")
    
    orig_path = '/Game/Models/PolygonHeist/Meshes/Props/SM_Prop_Money_Stack_01'
    out_path = '/Game/Models/MyMod/Meshes/SM_MoneyPallet_5'
    
    # Load original mesh via load_package (cooked, not in Asset Registry)
    log("Loading original mesh...")
    pkg = unreal.load_package(orig_path)
    if not pkg:
        log("ERROR: Could not load original package")
        return
    log(f"Package loaded: {pkg.get_name()}")
    
    # Find StaticMesh
    orig_mesh = None
    try:
        objects = unreal.get_package_objects(pkg)
        for obj in objects:
            if isinstance(obj, unreal.StaticMesh):
                orig_mesh = obj
                break
    except:
        pass
    
    if not orig_mesh:
        log("ERROR: No StaticMesh found")
        return
    log(f"Found original mesh: {orig_mesh.get_name()}")
    
    # Get original material
    orig_mats = orig_mesh.get_editor_property('static_materials')
    log(f"Original materials: {len(orig_mats) if orig_mats else 0}")
    
    orig_mat = None
    if orig_mats and len(orig_mats) > 0:
        orig_mat = orig_mats[0].get_editor_property('material_interface')
        log(f"Material: {orig_mat}")
    
    # Create level with 5 money stacks
    level_lib = unreal.EditorLevelLibrary
    level_lib.new_level('/Game/Temp/MergeLevel')
    
    actors = []
    for i in range(5):
        z = i * (STACK_H + GAP)
        actor = level_lib.spawn_actor_from_class(
            unreal.StaticMeshActor,
            unreal.Vector(0, 0, z),
            unreal.Rotator(0, 0, 0)
        )
        smc = actor.get_editor_property('static_mesh_component')
        smc.set_static_mesh(orig_mesh)
        if orig_mat:
            smc.set_material(0, orig_mat)
        actors.append(actor)
        log(f"Placed stack {i+1} at Z={z}")
    
    # Get mesh components
    components = [a.get_editor_property('static_mesh_component') for a in actors]
    
    # Merge settings - combine into single mesh with single collision
    settings = unreal.MeshMergingSettings()
    settings.set_editor_property('b_generate_light_map_uv', True)
    settings.set_editor_property('b_export_vertex_data', True)
    settings.set_editor_property('b_create_package_per_asset', True)
    settings.set_editor_property('b_merge_materials', False)
    settings.set_editor_property('b_merge_physics', True)
    settings.set_editor_property('merged_mesh_package_path', '/Game/Models/MyMod/Meshes')
    settings.set_editor_property('desired_object_name', 'SM_MoneyPallet_5')
    
    log("Merging...")
    try:
        result = unreal.MeshMergeLibrary.merge_static_mesh_components(
            components,
            None,
            settings
        )
        log(f"Merge result: {result}")
        
        if result:
            unreal.EditorAssetLibrary.save_asset(out_path, True)
            log("SUCCESS: Merged mesh saved")
        else:
            log("ERROR: Merge returned null")
    except Exception as e:
        log(f"ERROR: Merge failed: {e}")
    
    # Clean up
    try:
        unreal.EditorAssetLibrary.delete_directory('/Game/Temp')
    except:
        pass
    
    log("Done")

if __name__ == '__main__':
    main()
