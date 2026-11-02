"""Give the cell meshes real collision.

The cloned level's cells shipped with AggGeom -> ConvexElems (Array[1]): one 32-vertex convex
blob per 500 m cell. That is why the map is undriveable - the "road" is a single faceted
hull, not a surface.

The cells are already referenced by the level, so the cheapest correct fix is to change the
collision mode on the meshes rather than add collision actors (which would require level
patching on a cooked map): UseComplexAsSimple makes the engine build a triangle BVH straight
from the render geometry. Every cell is ~20k tris, so this is comparable to landscape
collision, and it makes road, barriers and walls all solid in one move.

Simple collision is explicitly cleared so no convex hull participates.
"""
import unreal

MESH_PATH = '/Game/Mods/C1/Meshes'


def main():
    assets = [a for a in unreal.EditorAssetLibrary.list_assets(MESH_PATH, recursive=False)
              if unreal.load_asset(a) and isinstance(unreal.load_asset(a), unreal.StaticMesh)]
    unreal.log('C1COL start meshes=%d' % len(assets))

    changed = 0
    tri_total = 0
    failed = []

    for path in assets:
        mesh = unreal.load_asset(path)
        try:
            body = mesh.get_editor_property('body_setup')
            if not body:
                raise RuntimeError('no BodySetup')
            # CollisionTraceFlag lives on UBodySetup, not on UStaticMesh.
            body.set_editor_property('collision_trace_flag',
                                     unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            agg = body.get_editor_property('agg_geom')
            agg.set_editor_property('convex_elems', [])
            body.set_editor_property('agg_geom', agg)
            unreal.EditorAssetLibrary.save_loaded_asset(body, False)
            unreal.EditorAssetLibrary.save_loaded_asset(mesh, False)
            changed += 1
            tri_total += mesh.get_num_triangles(0)
        except Exception as exc:  # noqa: BLE001
            failed.append('%s: %s' % (path, exc))

    unreal.log('C1COL_DONE meshes=%d changed=%d tris=%d failed=%d'
               % (len(assets), changed, tri_total, len(failed)))
    if failed:
        unreal.log('C1COL_FAILED %s' % ' | '.join(failed[:8]))


main()
