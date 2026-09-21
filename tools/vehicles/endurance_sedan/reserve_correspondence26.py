"""Read native fields and compare them only; never assign fixture data to a mesh."""
from . import reserve_semantic26 as complete

def require(value, reason):
    if not value:
        raise ValueError(reason)

def raw(obj):
    mesh = obj.data
    return {'vertices': [list(v.co) for v in mesh.vertices], 'edges': [(list(e.vertices), e.use_edge_sharp) for e in mesh.edges], 'polygons': [(list(p.vertices), p.material_index, p.use_smooth) for p in mesh.polygons], 'uvs': {u.name: [list(d.uv) for d in u.data] for u in mesh.uv_layers}, 'normals': [list(n.vector) for n in mesh.corner_normals], 'matrix': [list(r) for r in obj.matrix_world], 'materials': [m.name if m else None for m in mesh.materials], 'parent': obj.parent.name if obj.parent else None}

def evaluated(obj):
    import bpy
    graph = bpy.context.evaluated_depsgraph_get()
    ob = obj.evaluated_get(graph)
    mesh = ob.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        mesh.calc_loop_triangles()
        return {'name': obj.name, 'vertices': [list(ob.matrix_world @ v.co) for v in mesh.vertices], 'triangles': [list(t.vertices) for t in mesh.loop_triangles], 'normals': [list(n.vector) for n in mesh.corner_normals], 'triangle_loops': [list(t.loops) for t in mesh.loop_triangles], 'uvs': {u.name: [list(d.uv) for d in u.data] for u in mesh.uv_layers}, 'materials': [m.name if m else None for m in mesh.materials], 'triangle_materials': [t.material_index for t in mesh.loop_triangles]}
    finally:
        ob.to_mesh_clear()


def compare_raw(expected, actual):
    require(set(expected) == set(actual), 'Changed raw contract fields')
    return complete.compare_raw(expected, actual)


def compare_evaluated(expected, actual):
    require(set(expected) == set(actual), 'Changed evaluated contract fields')
    require(expected['name'] == actual['name'], 'Changed evaluated semantic identity')
    return complete.compare_evaluated(expected, actual)
