import bpy
import os

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Money stack dimensions (approximate)
STACK_W = 0.40   # Width (X) in meters (= 40 UE units)
STACK_D = 0.25   # Depth (Y) in meters (= 25 UE units)
STACK_H = 0.08   # Height (Z) in meters (= 8 UE units)
GAP = 0.005      # Small gap between stacks

# 5 stacks stacked vertically
for i in range(5):
    bpy.ops.mesh.primitive_cube_add(size=1)
    stack = bpy.context.active_object
    stack.name = f'MoneyStack_{i+1}'
    stack.scale = (STACK_W / 2, STACK_D / 2, STACK_H / 2)
    z_pos = i * (STACK_H + GAP) + STACK_H / 2
    stack.location = (0, 0, z_pos)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# Select all and join into one mesh
bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects['MoneyStack_1']
bpy.ops.object.join()
joined = bpy.context.active_object
joined.name = 'SM_MoneyPallet_5'

# Add simple UV unwrap
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=66, island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')

# Export as FBX
output_path = os.environ.get('OUTPUT_PATH', r'D:\UEProjects\MotorTown\Content\Models\MyMod\Meshes\SM_MoneyPallet_5.fbx')
bpy.ops.export_scene.fbx(
    filepath=output_path,
    use_selection=True,
    apply_scale_options='FBX_SCALE_ALL',
    axis_forward='-Z',
    axis_up='Y',
    mesh_smooth_type='FACE',
    add_leaf_bones=False,
)

print(f'Exported: {output_path}')
