"""Original triangle-owned fields for reports-only Boolean geometry trials."""
import math
from mathutils import Vector,geometry
from .floor_panels import freeze,clean_new_slivers
from . import triangle_projection as double
from . import corner_encoding as codec

ATTRIBUTE='cb_private_original_triangle'
CAPTURED_VERTICES={}
CLEANUP={}
def clean(obj):
    records=clean_new_slivers(obj,CAPTURED_VERTICES[obj.name]);CLEANUP.setdefault(obj.name,[]).extend(records);return records
def capture(obj):
    # Snapshot plain values before any Blender attribute allocation invalidates RNA.
    import bpy
    bpy.context.view_layer.update();ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh()
    try:
        m.calc_loop_triangles()
        CAPTURED_VERTICES[obj.name]=[tuple(v.co) for v in m.vertices]
        rows=[{'points':[tuple(m.vertices[v].co) for v in t.vertices],
               'normals':[tuple(m.corner_normals[l].vector) for l in t.loops],
               'uv':[tuple(m.uv_layers.active.data[l].uv) for l in t.loops]} for t in m.loop_triangles]
    finally:ev.to_mesh_clear()
    freeze(obj)
    assert len(obj.data.polygons)==len(rows)
    for face,row in zip(obj.data.polygons,rows):
        assert [tuple(obj.data.vertices[v].co) for v in face.vertices]==row['points']
    attr=obj.data.attributes.new(name=ATTRIBUTE,type='INT',domain='FACE')
    for i,value in enumerate(attr.data):value.value=i+1
    return rows

def restore(obj,rows):
    m=obj.data;m.calc_loop_triangles();attr=m.attributes.get(ATTRIBUTE)
    if attr is None:raise ValueError('Missing original-face ownership: '+obj.name)
    exact={tuple(sorted(row['points'])):i for i,row in enumerate(rows)}
    normals=[n.vector.copy() for n in m.corner_normals];uvs=m.uv_layers.active
    owned=0;unowned=0;invalid=[];maxdist=0.
    for face in m.polygons:
        pts=[m.vertices[v].co.copy() for v in face.vertices]
        original=exact.get(tuple(sorted(tuple(p) for p in pts)))
        if original is None:
            tagged=attr.data[face.index].value
            original=tagged-1 if 1<=tagged<=len(rows) else None
        row=rows[original] if original is not None else None
        accepted=False
        if row is not None:
            tri=[Vector(p) for p in row['points']]
            n=(tri[1]-tri[0]).cross(tri[2]-tri[0]).normalized()
            # Convex triangle ownership: every face vertex inside the original
            # closed triangle (1um native encoding guard) bounds its full fan.
            distances=[double.closest(tuple(p),row['points'])[0] for p in pts]
            accepted=(face.normal.dot(n)>.99985 and max(distances)<=1e-6)
        if accepted:
            owned+=1;maxdist=max(maxdist,max(distances))
            for loop in face.loop_indices:
                p=m.vertices[m.loops[loop].vertex_index].co
                direct=next((i for i,q in enumerate(row['points']) if tuple(p)==q),None)
                if direct is None:
                    distance,weights=double.closest(tuple(p),row['points'])
                    normal=Vector(double.interpolate(row['normals'],weights)).normalized()
                    uv=Vector((*double.interpolate(row['uv'],weights),0))
                else:normal=Vector(row['normals'][direct]);uv=Vector((*row['uv'][direct],0))
                if not all(math.isfinite(v) for v in normal) or abs(normal.length-1)>1e-6:raise ValueError('Invalid retained normal')
                normals[loop]=normal;uvs.data[loop].uv=uv.xy
        else:
            unowned+=1
            # Generated cavity faces keep their physical facet normal.
            for loop in face.loop_indices:normals[loop]=face.normal
            if row is not None:invalid.append({'face':face.index,'tagged_reference':original,'max_distance_m':max(distances)})
    encoding=codec.encode(m,normals);m.attributes.remove(m.attributes[ATTRIBUTE])
    return {'native_encoding':encoding,'bounded_new_sliver_cleanup':CLEANUP.get(obj.name,[]),'owned_original_faces':owned,'generated_or_unowned_faces':unowned,'rejected_ownership':invalid,
            'maximum_original_triangle_distance_m':maxdist,'ownership_guard_m':1e-6,
            'scope':'Complete original single-triangle ownership; no interpolated field is assigned to an unowned new face'}
