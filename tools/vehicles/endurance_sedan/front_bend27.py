"""Original continuous front-form proposal on current native geometry."""
import math
import bpy
from mathutils import Vector

START=2.230
END=2.400
CENTER=.550
OLD_RADIUS=3.457
NEW_RADIUS=.950


def smooth(value):
    t=max(0.,min(1.,value))
    return t*t*t*(10+t*(-15+6*t)),30*t*t*(1-t)*(1-t) if 0<t<1 else 0.


def field(point):
    x,y,z=point
    if y<=START:return Vector(point),(1.,0.,0.,1.,0.)
    weight,derivative=smooth((y-START)/(END-START));derivative/=END-START
    dz=z-CENTER
    old_root=math.sqrt(OLD_RADIUS*OLD_RADIUS-dz*dz)
    new_root=math.sqrt(NEW_RADIUS*NEW_RADIUS-dz*dz)
    delta=(NEW_RADIUS-new_root)-(OLD_RADIUS-old_root)
    delta_z=dz/new_root-dz/old_root
    d=1-delta*derivative;e=-delta_z*weight
    xfade,xder=smooth((abs(x)-.580)/.150);xgate=1-xfade
    xder=-xder/.150*(1 if x>=0 else -1)
    zfade,zder=smooth((z-.340)/.310);upper=1-zfade;upper_derivative=-zder/.310
    lower,lower_derivative=smooth((z-.205)/.095);lower_derivative/=.095
    zgate=upper*lower;zder=upper_derivative*lower+upper*lower_derivative
    amount=.115
    xweight,xweight_derivative=smooth((y-START)/.030);xweight_derivative/=.030
    a=1-amount*(xgate+x*xder)*xweight*zgate
    b=-amount*x*xgate*xweight_derivative*zgate
    c=-amount*x*xgate*xweight*zder
    if min(a,d)<=.2:raise ValueError('Front deformation loses its monotonicity bound')
    return Vector((x-amount*x*xgate*xweight*zgate,y-delta*weight,z)),(a,b,c,d,e)


def apply(obj,row,encode,*,ideal_stream=None):
    original=row(obj)
    graph=bpy.context.evaluated_depsgraph_get()
    evaluated=obj.evaluated_get(graph)
    mesh=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=graph)
    obj.modifiers.clear();obj.data=mesh
    assert row(obj)==original,'Bake changed actual input fields'
    explicit_proof=None
    if obj.name=='LOD0_FrontBumper':
        mesh.calc_loop_triangles()
        triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
        source_loops=[tuple(t.loops) for t in mesh.loop_triangles]
        source_normals=(ideal_stream.input(len(mesh.loops)) if ideal_stream is not None
                        else [tuple(n.vector) for n in mesh.corner_normals])
        old_mesh=mesh
        mesh=bpy.data.meshes.new(obj.name+'ExplicitOriginalTriangles')
        mesh.from_pydata([tuple(v.co) for v in old_mesh.vertices],[],triangles)
        for material in old_mesh.materials:mesh.materials.append(material)
        for polygon,triangle in zip(mesh.polygons,old_mesh.loop_triangles):
            polygon.material_index=triangle.material_index
            polygon.use_smooth=old_mesh.polygons[triangle.polygon_index].use_smooth
        for layer in old_mesh.uv_layers:
            out=mesh.uv_layers.new(name=layer.name)
            out.data.foreach_set('uv',[c for loops in source_loops for i in loops for c in layer.data[i].uv])
        mesh.update();obj.data=mesh
        explicit_targets=[source_normals[i] for loops in source_loops for i in loops]
        explicit_proof=encode(mesh,explicit_targets)
        if ideal_stream is not None:ideal_stream.accept(explicit_targets,len(mesh.loops))
        if not explicit_proof['passed']:raise ValueError('Explicit original bumper field target encoding failed')
        mesh.calc_loop_triangles()
        assert [tuple(t.vertices) for t in mesh.loop_triangles]==triangles
        assert [tuple(v.co) for v in mesh.vertices]==[tuple(v.co) for v in old_mesh.vertices]
        assert all(tuple(out.uv)==tuple(layer.data[i].uv)
                   for layer in old_mesh.uv_layers
                   for out,i in zip(mesh.uv_layers[layer.name].data,[k for ids in source_loops for k in ids]))
        if old_mesh.users==0:bpy.data.meshes.remove(old_mesh)
    old_uvs={layer.name:[tuple(v.uv) for v in layer.data] for layer in mesh.uv_layers}
    normal_matrix=obj.matrix_world.to_3x3().inverted().transposed()
    to_local_normal=obj.matrix_world.to_3x3().transposed()
    inverse=obj.matrix_world.inverted()
    raw_normals=([Vector(n) for n in ideal_stream.input(len(mesh.loops))] if ideal_stream is not None
                 else [Vector(n.vector) for n in mesh.corner_normals])
    world=[obj.matrix_world@v.co for v in mesh.vertices]
    values=[field(p) for p in world]
    targets=[]
    for loop,normal in zip(mesh.loops,raw_normals):
        _,(a,b,c,d,e)=values[loop.vertex_index]
        n=normal_matrix@normal
        nx=n.x/a;ny=(n.y-b*nx)/d
        n=Vector((nx,ny,n.z-c*nx-e*ny))
        targets.append(tuple((to_local_normal@n).normalized()))
    changed=[]
    for vertex,(point,_) in zip(mesh.vertices,values):
        if world[vertex.index].y>START:
            vertex.co=inverse@point;changed.append(vertex.index)
    mesh.update()
    result=encode(mesh,targets)
    if not result['passed']:raise ValueError('Front native target encoding failed')
    if ideal_stream is not None:ideal_stream.accept(targets,len(mesh.loops))
    assert old_uvs=={layer.name:[tuple(v.uv) for v in layer.data] for layer in mesh.uv_layers}
    actual=row(obj)
    assert len(actual['triangles'])==len(original['triangles'])
    return {'object':obj.name,'changed_vertices':changed,'triangles':len(actual['triangles']),
            'minimum_jacobian_diagonal':min(min(v[1][0],v[1][3]) for v in values),
            'maximum_vertex_displacement_m':max((a-b).length for a,(b,_) in zip(world,values)),
            'original_uvs_exact':True,'normal_encoding':result,'original_explicit_triangle_encoding':explicit_proof}
