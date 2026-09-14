"""Remove only a new Boolean off-edge planar fan, preserving original points.

The caller supplies actual pre-inlet vertices and the real native encoder.
This is a new authored post-cut rear-closure topology, not a tolerance waiver.
No IO, save/export, fixed source payload or report dependency.
"""
from collections import Counter,defaultdict
import math
import bpy

PLANE_Y=2.2300000190734863
OUTLINE=((-0.38,.783),(.38,.783),(.345,.708),(.08,.695),(-.08,.695),(-.345,.708))

def require(value,message):
    if not value:raise ValueError(message)

def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def ny(ps):return cross(sub(ps[1],ps[0]),sub(ps[2],ps[0]))[1]

def identify(points,triangles,materials,material_names,original_points):
    """Finite semantic/geometric selector; no hardcoded mesh or face indices."""
    require(original_points and all(len(p)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in p) for p in original_points),'Missing actual original vertex inventory')
    protected={tuple(p) for p in original_points};incidence=defaultdict(list)
    for fi,tri in enumerate(triangles):
        require(len(tri)==3 and len(set(tri))==3,'Nontriangular original post-cut face')
        for vi in tri:incidence[vi].append(fi)
    candidates=[]
    for fi,tri in enumerate(triangles):
        if material_names[materials[fi]]!='Material_Trim':continue
        ps=[points[i] for i in tri]
        if not all(p[1]==PLANE_Y for p in ps) or ny(ps)<=0:continue
        for vi in tri:
            if tuple(points[vi]) in protected or len(incidence[vi])!=3:continue
            faces=sorted(incidence[vi]);others=[j for j in faces if j!=fi]
            if not all(material_names[materials[j]]=='Material_Paint' and all(points[k][1]==PLANE_Y for k in triangles[j])
                       and ny([points[k] for k in triangles[j]])<0 for j in others):continue
            a,b=[j for j in tri if j!=vi];delta=sub(points[b],points[a]);length2=dot(delta,delta)
            if length2<=0:continue
            fraction=dot(sub(points[vi],points[a]),delta)/length2
            hit=tuple(points[a][k]+fraction*delta[k] for k in range(3));altitude=math.dist(points[vi],hit)
            if not 0<fraction<1 or not 0<altitude<=1e-6:continue
            edge_matches=[]
            for index,(u,v) in enumerate(zip(OUTLINE,OUTLINE[1:]+OUTLINE[:1])):
                dx,dz=v[0]-u[0],v[1]-u[1];length=math.hypot(dx,dz)
                distances=[abs((p[0]-u[0])*dz-(p[2]-u[1])*dx)/length for p in ps]
                parameters=[((p[0]-u[0])*dx+(p[2]-u[1])*dz)/(length*length) for p in ps]
                if max(distances)<=1e-6 and min(parameters)>=-1e-6/length and max(parameters)<=1+1e-6/length:edge_matches.append(index)
            if len(edge_matches)!=1:continue
            directed=Counter((a,b) for j in faces for a,b in zip(triangles[j],triangles[j][1:]+triangles[j][:1]))
            boundary=[edge for edge,n in directed.items() if n-directed[(edge[1],edge[0])]==1]
            require(len(boundary)==3 and all(vi not in e for e in boundary),'Generated candidate does not have a triangular fixed boundary')
            successors=dict(boundary);start=min(successors);replacement=(start,successors[start],successors[successors[start]])
            require(successors[replacement[-1]]==start and len(set(replacement))==3,'Branched generated fan boundary')
            require(ny([points[i] for i in replacement])<0,'Generated fan boundary is not the rear closure')
            require(math.hypot(*cross(sub(points[replacement[1]],points[replacement[0]]),sub(points[replacement[2]],points[replacement[0]])))*.5>1e-12,'Replacement fails unchanged area gate')
            candidates.append({'vertex':vi,'point':points[vi],'old_faces':faces,'sliver_face':fi,
                'boundary_triangle':replacement,'cut_segment_vertices':[a,b],'cut_outline_edge':edge_matches[0],
                'segment_fraction':fraction,'altitude_m':altitude,'original_preinlet_vertex':False,
                'newly_authored_rear_domain':True})
    require(len({r['vertex'] for r in candidates})==len(candidates),'Ambiguous generated fan candidate')
    affected=[fi for r in candidates for fi in r['old_faces']]
    require(len(set(affected))==len(affected),'Intersecting generated fan repair domains')
    return candidates

def apply(obj,original_preinlet_vertices,encode,*,ideal_normals=None):
    require(obj.name=='LOD0_FrontBumper' and not obj.modifiers,'Expected current native front bumper')
    old=obj.data;old.calc_loop_triangles()
    require(len(old.polygons)==len(old.loop_triangles) and all(len(p.vertices)==3 for p in old.polygons),'Expected explicit post-inlet triangles')
    points=[tuple(v.co) for v in old.vertices];triangles=[tuple(p.vertices) for p in old.polygons]
    materials=[p.material_index for p in old.polygons];names=[m.name for m in old.materials]
    candidates=identify(points,triangles,materials,names,original_preinlet_vertices)
    if not candidates:return {'status':'no-generated-offedge-fan','repairs':[],'triangle_delta':0,'vertex_delta':0}
    require(set(u.name for u in old.uv_layers)=={'SurfaceMeters'},'Unsupported current chart domain')
    normals=[tuple(n.vector) for n in old.corner_normals] if ideal_normals is None else [tuple(n) for n in ideal_normals]
    require(len(normals)==len(old.loops) and all(len(n)==3 and abs(math.hypot(*n)-1)<=1e-6 and all(math.isfinite(x) for x in n) for n in normals),'Invalid complete ideal target inventory')
    removed_faces={fi for r in candidates for fi in r['old_faces']};removed_vertices={r['vertex'] for r in candidates}
    indices=[i for i in range(len(points)) if i not in removed_vertices];remap={old_i:new_i for new_i,old_i in enumerate(indices)}
    new_points=[points[i] for i in indices];faces=[];slots=[];smooth=[];targets=[];uvs=[];outside=[]
    for fi,p in enumerate(old.polygons):
        if fi in removed_faces:continue
        require(not removed_vertices.intersection(p.vertices),'Removed point escapes selected fan')
        faces.append(tuple(remap[i] for i in p.vertices));slots.append(p.material_index);smooth.append(p.use_smooth)
        targets.extend(normals[i] for i in p.loop_indices);uvs.extend(tuple(old.uv_layers['SurfaceMeters'].data[i].uv) for i in p.loop_indices)
        outside.append({'new_face':len(faces)-1,'old_face':fi})
    paint=names.index('Material_Paint')
    for r in candidates:
        ids=r['boundary_triangle'];faces.append(tuple(remap[i] for i in ids));slots.append(paint);smooth.append(True)
        targets.extend([(0.,-1.,0.)]*3);uvs.extend((points[i][0]/.25,points[i][2]/.25) for i in ids)
        r['new_face']=len(faces)-1
    mesh=bpy.data.meshes.new(obj.name+'PostcutRearFan')
    try:
        mesh.from_pydata(new_points,[],faces)
        for m in old.materials:mesh.materials.append(m)
        for p,mat,flag in zip(mesh.polygons,slots,smooth):p.material_index=mat;p.use_smooth=flag
        mesh.uv_layers.new(name='SurfaceMeters').data.foreach_set('uv',[x for uv in uvs for x in uv]);mesh.update()
        obj.data=mesh
        result=encode(mesh,targets)
        require(result['passed'],'Post-cut authored target encoding failed')
        require([tuple(v.co) for v in mesh.vertices]==new_points,'Post-cut native point changed')
    except BaseException:
        obj.data=old
        if mesh.users==0:bpy.data.meshes.remove(mesh)
        raise
    return {'status':'authored-generated-offedge-fan-repair','repairs':candidates,'outside_faces':outside,
        'retained_vertex_indices':indices,'triangle_delta':len(faces)-len(triangles),'vertex_delta':len(new_points)-len(points),
        'removed_only_new_Boolean_points':True,'outside_original_corner_targets_preserved':True,
        'normal_encoding':result,'source_saved':False,'mechanical_or_visual_acceptance':False}
