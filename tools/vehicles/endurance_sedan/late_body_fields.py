"""Restore only complete unchanged body triangles from the actual initial field.

No geometry, UV, source I/O or generated-face field change. Ownership requires
an exact oriented original triangle outside the union of actual edit boxes.
"""
import math
import bpy
from . import corner_encoding as codec
def cyclic(points):
    p=[tuple(v)for v in points];i=min(range(3),key=lambda j:p[j:]+p[:j]);return tuple(p[i:]+p[:i]),i
def capture(obj):
    bpy.context.view_layer.update()
    if any(abs(obj.matrix_world[i][j]-(1 if i==j else 0))>1e-12 for i in range(4)for j in range(4)):raise ValueError('Expected established identity body frame')
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh()
    try:
        m.calc_loop_triangles();result={}
        for t in m.loop_triangles:
            points=[tuple(m.vertices[v].co)for v in t.vertices];key,pivot=cyclic(points);loops=list(t.loops);loops=loops[pivot:]+loops[:pivot]
            if key in result:raise ValueError('Ambiguous original geometric triangle')
            result[key]={'normals':[tuple(m.corner_normals[i].vector)for i in loops],'uv':[tuple(m.uv_layers.active.data[i].uv)for i in loops],'triangle_index':int(t.index)}
        return result
    finally:ev.to_mesh_clear()
def restore(obj,original,cutters):
    if obj.modifiers:raise ValueError('Final original-field reset requires applied geometry modifiers')
    m=obj.data;m.calc_loop_triangles();old_vertices=[tuple(v.co)for v in m.vertices];old_polygons=[tuple(p.vertices)for p in m.polygons];old_materials=[p.material_index for p in m.polygons];old_smooth=[p.use_smooth for p in m.polygons]
    uv_layers={layer.name:[tuple(v.uv)for v in layer.data]for layer in m.uv_layers};old_normals=[tuple(n.vector)for n in m.corner_normals];old_codes=[tuple(v.value)for v in m.attributes['custom_normal'].data]
    sharp=m.attributes.get('sharp_edge')
    if sharp is None or not all(v.value for v in sharp.data):raise ValueError('Expected existing independent sharp corner encoding spaces')
    targets=old_normals[:];assigned={};ownership=[]
    for t in m.loop_triangles:
        points=[tuple(m.vertices[v].co)for v in t.vertices];box=[[min(p[i]for p in points)for i in range(3)],[max(p[i]for p in points)for i in range(3)]]
        if not all(any(box[1][i]<cut['bounds'][0][i]-1e-6 or box[0][i]>cut['bounds'][1][i]+1e-6 for i in range(3))for cut in cutters):continue
        key,pivot=cyclic(points)
        if key not in original:raise ValueError('Protected body triangle lacks exact oriented original ownership')
        row=original[key];loops=list(t.loops);loops=loops[pivot:]+loops[:pivot]
        for j,loop in enumerate(loops):
            value=row['normals'][j]
            if tuple(m.uv_layers.active.data[loop].uv)!=row['uv'][j]:raise ValueError('Protected original UV mismatch')
            if loop in assigned and assigned[loop]!=value:raise ValueError('Conflicting original loop ownership')
            assigned[loop]=value;targets[loop]=value
        ownership.append({'final_triangle':int(t.index),'original_triangle':row['triangle_index'],'final_loops':loops})
    if not ownership:raise ValueError('No complete original triangle domain')
    # A loop shared with any unowned triangle would change its field. Require
    # the exact independent triangle representation used by this source.
    selected={r['final_triangle']for r in ownership}
    for t in m.loop_triangles:
        if t.index not in selected and any(i in assigned for i in t.loops):raise ValueError('Protected loop also belongs to an authored domain')
    encoding=codec.encode(m,targets)
    if not encoding['passed']:raise ValueError('Original-source target failed unchanged native encoding guard')
    # Geometry and all corner spaces stayed fixed. Restore old native codes on
    # every unowned loop so no newly authored cavity/profile field changes.
    for i,code in enumerate(old_codes):
        if i not in assigned:m.attributes['custom_normal'].data[i].value=code
    m.update();actual=[tuple(n.vector)for n in m.corner_normals]
    if any(actual[i]!=old_normals[i]for i in range(len(actual))if i not in assigned):raise ValueError('Changed an unowned native corner field')
    if [tuple(v.co)for v in m.vertices]!=old_vertices or [tuple(p.vertices)for p in m.polygons]!=old_polygons:raise ValueError('Unexpected geometry change')
    if {layer.name:[tuple(v.uv)for v in layer.data]for layer in m.uv_layers}!=uv_layers:raise ValueError('Unexpected UV change')
    if [p.material_index for p in m.polygons]!=old_materials or [p.use_smooth for p in m.polygons]!=old_smooth:raise ValueError('Unexpected face attribute change')
    if not all(v.value for v in m.attributes['sharp_edge'].data):raise ValueError('Changed native corner-space topology')
    return {'scope':'One final reset to the untouched actual current source, restricted to exact oriented triangles wholly outside all actual body edit boxes expanded1um. Unowned native loop fields are byte-exact to pre-reset values.','complete_original_triangles':len(ownership),'owned_native_loops':len(assigned),'unowned_native_loops_exact':len(actual)-len(assigned),'ownership':ownership,'native_encoding':encoding,'geometry_UV_material_smooth_exact':True,'unowned_fields_exact':True,'whole_field_certificate':'Separately compare complete affine fields against the original current body; no sum of stage tolerances.'}
