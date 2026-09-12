"""Preserve sensitive paint geometry and its corner field across distance LODs.

The rear deck/bumper is visually sensitive to interpolated normal changes even
where simplification moves positions by only micrometers. Protect the actual
rear region and trunk batch. The hood is also retained because decimation
generated invalid zero corner normals. Other simplification keeps its budget.
"""
import math

# Blender's native custom-normal encoding changed these rebuilt batches by at
# most 0.227282 degrees in the complete source34 probe. This bound applies only
# to native LOD construction, independently of the stricter platform bake gate.
MAXIMUM_NORMAL_REENCODING_DEGREES=1.


def checked_unit_normal(value):
    if not all(math.isfinite(component) for component in value) or value.length_squared<=1e-12:
        raise ValueError('Protected rear paint normal is nonfinite or zero')
    return value.normalized()


def triangle_key(points):
    return tuple(sorted(tuple(point) for point in points))


def prepare(obj):
    if obj.data.materials[0].name!='Material_Paint':return None
    if obj.parent.name not in ('Visual_LOD1','Visual_LOD2','Trunk_Hinge','Hood_Hinge'):return None
    data=obj.data
    data.calc_loop_triangles()
    full=obj.parent.name in ('Trunk_Hinge','Hood_Hinge')
    protected={v.index for v in data.vertices if full or (obj.matrix_world@v.co).y < -2.10}
    if not protected:return None
    triangles=[]
    boundary=0
    for triangle in data.loop_triangles:
        boundary+=any(v in protected for v in triangle.vertices)
        if not all(v in protected for v in triangle.vertices):continue
        points=[data.vertices[i].co.copy() for i in triangle.vertices]
        triangles.append({'points':points,'key':triangle_key(points),
                          'normals':[data.corner_normals[i].vector.copy() for i in triangle.loops],
                          'uv':[data.uv_layers.active.data[i].uv.copy() for i in triangle.loops],
                          'smooth':data.polygons[triangle.polygon_index].use_smooth})
    return {'vertices':protected,'triangles':triangles,'boundary':boundary,
            'initial':len(data.loop_triangles),'full':full,'parent':obj.parent.name}


def configure(obj,modifier,protection,ratio):
    if protection is None:return ratio
    group=obj.vertex_groups.get('Protected rear paint complement') or obj.vertex_groups.new(name='Protected rear paint complement')
    group.add(list(range(len(obj.data.vertices))),1.,'REPLACE')
    group.add(sorted(protection['vertices']),0.,'REPLACE')
    modifier.vertex_group=group.name
    modifier.vertex_group_factor=1.
    boundary=protection['boundary'];initial=protection['initial']
    return (boundary+(initial-boundary)*ratio)/initial


def restore(obj,protection):
    if protection is None:return None
    data=obj.data
    data.calc_loop_triangles()
    remaining={}
    for row in protection['triangles']:remaining.setdefault(row['key'],[]).append(row)
    normals=[n.vector.copy() for n in data.corner_normals]
    uv=data.uv_layers.active
    restored=[]
    for triangle in data.loop_triangles:
        points=[data.vertices[i].co.copy() for i in triangle.vertices]
        matches=remaining.get(triangle_key(points),[])
        if not matches:continue
        row=matches.pop(0)
        order=[next(j for j,p in enumerate(row['points']) if p==point) for point in points]
        if len(set(order))!=3:raise ValueError('Protected rear triangle collapsed: '+obj.name)
        # Cyclic rotations preserve winding; an odd permutation does not.
        if tuple(order) not in ((0,1,2),(1,2,0),(2,0,1)):
            raise ValueError('Protected rear paint winding changed: '+obj.name)
        for loop,j in zip(triangle.loops,order):
            checked_unit_normal(row['normals'][j])
            normals[loop]=row['normals'][j]
            uv.data[loop].uv=row['uv'][j]
        data.polygons[triangle.polygon_index].use_smooth=row['smooth']
        restored.append((tuple(triangle.loops),row,order))
    if any(remaining.values()) or len(restored)!=len(protection['triangles']):
        raise ValueError('Distance LOD lost protected rear triangles: '+obj.name)
    data.normals_split_custom_set(normals)
    data.update()
    maximum_normal=0.
    for loops,row,order in restored:
        for loop,j in zip(loops,order):
            if uv.data[loop].uv!=row['uv'][j]:raise ValueError('Protected rear UV changed')
            a=checked_unit_normal(data.corner_normals[loop].vector)
            b=checked_unit_normal(row['normals'][j])
            angle=math.degrees(math.acos(max(-1.,min(1.,a.dot(b)))))
            if not math.isfinite(angle) or angle>MAXIMUM_NORMAL_REENCODING_DEGREES:
                raise ValueError('Protected rear paint normal exceeds native re-encoding bound: '+obj.name)
            maximum_normal=max(maximum_normal,angle)
    return {'scope':('complete '+protection['parent']+' paint') if protection['full'] else 'fixed paint source Y < -2.10m',
            'protected_vertices':len(protection['vertices']),'complete_restored_triangles':len(restored),
            'position_and_uv_maximum_difference':0.,
            'maximum_native_normal_reencoding_degrees':maximum_normal,
            'maximum_native_normal_reencoding_limit_degrees':MAXIMUM_NORMAL_REENCODING_DEGREES,
            'winding_preserved':True}
