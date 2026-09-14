"""Original swept optical opening field, preserving circular projector geometry."""
import math
import bpy
from mathutils import Vector,Matrix

def smooth(v):
    t=max(0.,min(1.,v))
    return t*t*t*(10+t*(-15+6*t)),30*t*t*(1-t)*(1-t) if 0<t<1 else 0.

def rising(value,start,end):
    f,d=smooth((value-start)/(end-start))
    return f,d/(end-start)

def weight(p):
    x,y,z=p;s=1 if x>=0 else -1
    lx,ld=rising(abs(x),.34,.40);ux,ud=rising(abs(x),.870,.950)
    gx=lx*(1-ux);dx=s*(ld*(1-ux)-lx*ud)
    gy,dy=rising(y,2.015,2.055)
    lz,ld=rising(z,.615,.671);uz,ud=rising(z,.817,.835)
    gz=lz*(1-uz);dz=ld*(1-uz)-lz*ud
    return gx*gy*gz,Vector((dx*gy*gz,gx*dy*gz,gx*gy*dz))

def field(point,kind,center_x):
    x,y,z=point
    if kind=='projector':return Vector((x,y,z+.08*(abs(center_x)-.635)-.22*(.746-.744))),Matrix.Identity(3)
    w,gradient=(1.,Vector((0,0,0))) if kind=='housing' else weight(point)
    amount=-.22*(z-.744)+.08*(abs(x)-.635)
    da=Vector((.08*(1 if x>=0 else -1),0,-.22))
    dz=gradient*amount+da*w
    jacobian=Matrix(((1,0,0),(0,1,0),(dz.x,dz.y,1+dz.z)))
    if jacobian.determinant()<.2:raise ValueError('Optical field loses its monotonicity bound')
    return Vector((x,y,z+w*amount)),jacobian

def kind(name):
    if name in ('LOD0_FrontBumper','LOD0_StructuralBody'):return 'body'
    if name.startswith('LOD0_Projector'):return 'projector'
    if name.startswith(('LOD0_Headlight','LOD0_FrontIndicator_')):return 'housing'
    return None

def apply(obj,row,encode,*,ideal_stream=None):
    original=row(obj);role=kind(obj.name);assert role
    graph=bpy.context.evaluated_depsgraph_get();ev=obj.evaluated_get(graph)
    mesh=bpy.data.meshes.new_from_object(ev,preserve_all_data_layers=True,depsgraph=graph)
    obj.modifiers.clear();obj.data=mesh;assert row(obj)==original
    world=[obj.matrix_world@p.co for p in mesh.vertices]
    cx=(min(p.x for p in world)+max(p.x for p in world))/2
    values=[field(p,role,cx) for p in world]
    matrix=obj.matrix_world.to_3x3();normal_world=matrix.inverted().transposed();normal_local=matrix.transposed()
    original_targets=(ideal_stream.input(len(mesh.loops)) if ideal_stream is not None
                      else [tuple(n.vector) for n in mesh.corner_normals])
    normals=[(normal_local@values[loop.vertex_index][1].inverted().transposed()@normal_world@Vector(n)).normalized()
             for loop,n in zip(mesh.loops,original_targets)]
    inverse=obj.matrix_world.inverted()
    changed=[]
    for v,(p,jacobian) in zip(mesh.vertices,values):
        if tuple(p)!=tuple(world[v.index]):v.co=inverse@p;changed.append(v.index)
    mesh.update();proof=encode(mesh,normals)
    if not proof['passed']:raise ValueError('Optical field native encoding failed')
    if ideal_stream is not None:ideal_stream.accept(normals,len(mesh.loops))
    actual=row(obj);assert actual['uvs']==original['uvs'];assert len(actual['triangles'])==len(original['triangles'])
    return {'object':obj.name,'role':role,'changed_vertices':changed,'maximum_displacement_m':max((a-b).length for a,(b,_) in zip(world,values)),
            'minimum_jacobian_determinant':min(j.determinant() for _,j in values),'normal_encoding':proof,'original_uvs_exact':True,'triangle_delta':0,
            'rigid_projector_translation':role=='projector'}
