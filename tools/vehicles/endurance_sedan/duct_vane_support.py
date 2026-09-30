"""Model-only finite bumper-wall seats for the six original cosmetic vanes.

Apply after the seven-section duct_vanes reduction. Source construction reads
the current scene only. No file I/O, source loading, saves, exports or renders.
The changed end positions are new authored geometry, not retained end caps.
"""
import math
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .corner_encoding import encode

NAMES=tuple('LOD0_BrakeDuctVane_'+side+str(i) for side in ('L','R') for i in range(3))
GUARD=1e-6

def _split(poly,a,b,c):
    inside=[];outside=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        dp=a*p[0]+b*p[1]-c;dq=a*q[0]+b*q[1]-c
        pin=dp>=0.;qin=dq>=0.
        (inside if pin else outside).append(p)
        if pin!=qin:
            t=dp/(dp-dq);r=(p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1]))
            inside.append(r);outside.append(r)
    return inside,outside

def _area(poly):
    return abs(math.fsum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1])))*.5 if len(poly)>2 else 0.

def _cover_rectangle(rectangle,triangles):
    """Subtract actual planar carrier triangles; retain every uncovered piece."""
    remaining=[rectangle];used=[]
    for index,points in triangles:
        area=math.fsum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))
        if area<0:points=list(reversed(points))
        todo=[];touched=False
        for polygon in remaining:
            part=polygon
            for p,q in zip(points,points[1:]+points[:1]):
                a,b=-(q[1]-p[1]),q[0]-p[0]
                part,outside=_split(part,a,b,a*p[0]+b*p[1])
                if outside:todo.append(outside)
                if not part:break
            touched=touched or bool(part)
        if touched:used.append(index)
        remaining=todo
        if not remaining:break
    # Zero-area edge remnants may arise from a native shared triangle edge.
    # They still need complete point membership in an actual supporting facet.
    unresolved=[]
    for polygon in remaining:
        covered=False
        for _,points in triangles:
            orientation=math.fsum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))
            if orientation<0:points=list(reversed(points))
            if all(all((-(q[1]-p[1])*(r[0]-p[0])+(q[0]-p[0])*(r[1]-p[1]))/math.dist(p,q)>=-1e-12
                       for p,q in zip(points,points[1:]+points[:1])) for r in polygon):covered=True;break
        if not covered:unresolved.append(polygon)
    if unresolved:raise ValueError('Actual bumper does not cover complete vane end cap: '+str(unresolved))
    return {'area_m2':_area(rectangle),'carrier_triangle_indices':used,'uncovered':[]}

def _snapshot(mesh):
    return {'vertices':[tuple(v.co) for v in mesh.vertices],
            'polygons':[tuple(p.vertices) for p in mesh.polygons],
            'uvs':{l.name:[tuple(v.uv) for v in l.data] for l in mesh.uv_layers},
            'normals':[tuple(n.vector) for n in mesh.corner_normals],
            'materials':[m.name if m else None for m in mesh.materials],
            'smooth':[p.use_smooth for p in mesh.polygons]}

def apply():
    if bpy.app.version!=(5,1,2):raise ValueError('Pinned Blender5.1.2 required')
    if any(n not in bpy.data.objects for n in (*NAMES,'LOD0_FrontBumper')):raise ValueError('Missing exact duct-vane/carrier semantics')
    objects=[bpy.data.objects[n] for n in NAMES]
    if any(o.get('duct_vane_fixed_seats') for o in objects):raise ValueError('Vane supports already authored')
    graph=bpy.context.evaluated_depsgraph_get();body=bpy.data.objects['LOD0_FrontBumper'].evaluated_get(graph)
    bm=body.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
    try:
        bm.calc_loop_triangles();bp=[tuple(body.matrix_world@v.co) for v in bm.vertices]
        bt=[tuple(t.vertices) for t in bm.loop_triangles]
    finally:body.to_mesh_clear()
    tree=BVHTree.FromPolygons(bp,bt,all_triangles=True,epsilon=0.)
    staged=[];proof=[]
    try:
        for obj in objects:
            if obj.type!='MESH' or obj.modifiers:raise ValueError('Apply to final seven-section vanilla mesh: '+obj.name)
            if max(abs(obj.matrix_world[i][j]-(1. if i==j else 0.)) for i in range(4) for j in range(4))>1e-12:
                raise ValueError('Expected original source-coordinate identity vane transform')
            old=_snapshot(obj.data);obj.data.calc_loop_triangles()
            if len(old['vertices'])!=28 or len(obj.data.loop_triangles)!=52 or len(old['materials'])!=1:
                raise ValueError('Expected original optimized seven rings, four corners,52 triangles')
            mesh=obj.data.copy();staged.append((obj,mesh));ends=[];changed=set()
            for sign,ids in ((-1,list(range(4))),(1,list(range(24,28)))):
                pp=[old['vertices'][i] for i in ids];x=pp[0][0]
                if any(abs(p[0]-x)>1e-12 for p in pp):raise ValueError('Nonplanar original vane end')
                center=sum((Vector(p) for p in pp),Vector())/4
                hit,normal,index,distance=tree.ray_cast(center,Vector((sign,0,0)),.020)
                if hit is None or not .0064<distance<.0066 or normal.dot(Vector((-sign,0,0)))<.999999:
                    raise ValueError('Actual bumper aperture wall changed')
                face=[bp[i] for i in bt[index]];target=face[0][0]
                if any(abs(p[0]-target)>1e-7 for p in face):raise ValueError('Expected actual planar aperture carrier')
                for p in pp:
                    q,n,_,d=tree.ray_cast(Vector(p),Vector((sign,0,0)),.020)
                    if q is None or abs(q.x-target)>GUARD or n.dot(Vector((-sign,0,0)))<.999999:
                        raise ValueError('Vane corner fails measured carrier plane')
                ymin,ymax=min(p[1] for p in pp),max(p[1] for p in pp)
                zmin,zmax=min(p[2] for p in pp),max(p[2] for p in pp)
                rectangle=[(ymin,zmin),(ymax,zmin),(ymax,zmax),(ymin,zmax)]
                carriers=[]
                for ti,t in enumerate(bt):
                    p=[bp[i] for i in t]
                    if not all(abs(v[0]-target)<=GUARD for v in p):continue
                    normal=(Vector(p[1])-Vector(p[0])).cross(Vector(p[2])-Vector(p[0]))
                    if normal.length<=1e-12 or normal.normalized().dot(Vector((-sign,0,0)))<.999999:continue
                    if max(v[1] for v in p)<ymin or min(v[1] for v in p)>ymax or max(v[2] for v in p)<zmin or min(v[2] for v in p)>zmax:continue
                    carriers.append((ti,[(v[1],v[2]) for v in p]))
                support=_cover_rectangle(rectangle,carriers)
                if support['area_m2']<.000258:raise ValueError('Complete original 37x7mm seat area required')
                for i in ids:mesh.vertices[i].co.x=target;changed.add(i)
                ends.append({'carrier':'LOD0_FrontBumper','x_m':target,'former_x_m':x,'x_change_m':target-x,
                    'yz_bounds_m':[[ymin,zmin],[ymax,zmax]],'vertex_ids':ids,'full_cap_support':support,
                    'type':'Finite fixed end-cap butt seat; no bond load/fastener/airflow simulation'})
            mesh.update();targets=[];changed_polygons=[]
            for polygon in mesh.polygons:
                authored=any(i in changed for i in polygon.vertices)
                if authored:changed_polygons.append(polygon.index)
                for loop in polygon.loop_indices:
                    vi=mesh.loops[loop].vertex_index
                    target=tuple(polygon.normal) if vi in changed else old['normals'][loop]
                    targets.append(target)
            encoding=encode(mesh,targets)
            if not encoding['passed']:raise ValueError('Native normal encoding guard failed')
            mesh.calc_loop_triangles();now=_snapshot(mesh)
            if len(mesh.loop_triangles)!=52 or now['polygons']!=old['polygons'] or now['uvs']!=old['uvs'] or now['materials']!=old['materials'] or now['smooth']!=old['smooth']:
                raise ValueError('Unexpected vane count/topology/material/UV/smooth change')
            if any(now['vertices'][i]!=p for i,p in enumerate(old['vertices']) if i not in changed):raise ValueError('Interior vane ring moved')
            if any(now['vertices'][i][1:]!=old['vertices'][i][1:] for i in changed):raise ValueError('End Y/Z envelope changed')
            proof.append({'name':obj.name,'seats':ends,'triangles_before':52,'triangles_after':52,'triangle_delta':0,
                'moved_vertices':sorted(changed),'authored_polygon_indices':changed_polygons,
                'unchanged_middle_ring_vertices':20,'unchanged_uvs_materials_polygons':True,
                'native_normal_encoding':encoding,'field_scope':'End caps and first/last cells newly authored; all untouched corner targets are the original current values.',
                'before':old,'after':now})
        for obj,mesh in staged:
            obj.data=mesh;obj['duct_vane_fixed_seats']='Both end rings extended to actual bumper aperture side walls; finite37x7mm butt seats. New authored width223mm; no retained-end-position claim.'
        return objects,proof
    except BaseException:
        for _,mesh in staged:
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        raise
