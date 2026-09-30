"""Unsaved six-pipe bend prototype. Existing ports/receivers are not re-cut."""
import math
import bpy
from mathutils import Vector

SPLITS = {'HotChargePipe': {1: 2, 2: 3, 3: 2},
          'ColdChargePipe': {1: 2, 2: 2, 3: 1, 4: 1},
          'ChargeCoolantHose': {1: 2, 2: 1, 3: 1, 4: 2, 5: 1, 6: 1}}


def hermite(p, q, a, b, length, t):
    point = (2*t**3-3*t**2+1)*p + (t**3-2*t**2+t)*length*a + (-2*t**3+3*t**2)*q + (t**3-t**2)*length*b
    tangent = (6*t*t-6*t)*p + (3*t*t-4*t+1)*length*a + (-6*t*t+6*t)*q + (3*t*t-2*t)*length*b
    return point, tangent.normalized()


def stations(points, radii, sides, overrides, splits):
    ps = [Vector(p) for p in points]; count = len(ps)
    ts = [(ps[min(i+1,count-1)]-ps[max(0,i-1)]).normalized() for i in range(count)]
    for i,d in overrides.items():ts[i]=Vector(d).normalized()
    guide = Vector((0,0,1)) if abs(ts[0].z)<.95 else Vector((0,1,0))
    ns=[ts[0].cross(guide).normalized()]
    for previous,tangent in zip(ts,ts[1:]):
        n=previous.rotation_difference(tangent)@ns[-1]
        ns.append((n-tangent*n.dot(tangent)).normalized())
    rr=list(radii) if isinstance(radii,(list,tuple)) else [radii]*count
    rings=[];info=[]
    for i in range(count):
        b=ts[i].cross(ns[i]).normalized()
        rings.append([ps[i]+rr[i]*(math.cos(j*math.tau/sides)*ns[i]+math.sin(j*math.tau/sides)*b) for j in range(sides)])
        info.append({'original_station':i,'point':list(ps[i]),'tangent':list(ts[i]),'radius':rr[i]})
        if i==count-1:continue
        divisions=splits.get(i,1)
        for step in range(1,divisions):
            t=step/divisions;length=(ps[i+1]-ps[i]).length
            p,d=hermite(ps[i],ps[i+1],ts[i],ts[i+1],length,t)
            n=ts[i].rotation_difference(d)@ns[i]
            n=(n-d*n.dot(d)).normalized()
            end=ts[i].rotation_difference(ts[i+1])@ns[i]
            end=(end-ts[i+1]*end.dot(ts[i+1])).normalized()
            twist=math.atan2(ts[i+1].dot(end.cross(ns[i+1])),end.dot(ns[i+1]))
            # Exact original station rings remain authored anchors. Interior
            # frames rotate continuously into both original endpoint frames.
            n=math.cos(twist*t)*n+math.sin(twist*t)*d.cross(n)
            n=(n-d*n.dot(d)).normalized();b=d.cross(n).normalized()
            r=rr[i]*(1-t)+rr[i+1]*t
            rings.append([p+r*(math.cos(j*math.tau/sides)*n+math.sin(j*math.tau/sides)*b) for j in range(sides)])
            info.append({'segment':i,'fraction':t,'point':list(p),'tangent':list(d),'radius':r,
                         'center_chord_offset_m':(p-(ps[i]*(1-t)+ps[i+1]*t)).length})
    return rings,info


def make_tube(geo, recipe, name, points, radii, material, collection, sides, overrides, splits):
    rings,info=stations(points,radii,sides,overrides,splits)
    vertices=[p for ring in rings for p in ring]
    faces=[(i*sides+j,i*sides+(j+1)%sides,(i+1)*sides+(j+1)%sides,(i+1)*sides+j)
           for i in range(len(rings)-1) for j in range(sides)]
    faces.extend([tuple(reversed(range(sides))),tuple((len(rings)-1)*sides+j for j in range(sides))])
    obj=geo.mesh(name,vertices,faces,material,collection,smooth=True)
    recipe.caps_flat(obj)
    return obj,info


def apply(geo, row, recipe, repair, exact_scan, simplify):
    """Stage/validate all six pipes, then assign. No IO or source-save calls."""
    objects={n:bpy.data.objects[n] for side in (-1,1) for n in
             ('LOD0_HotChargePipe_'+str(side),'LOD0_ColdChargePipe_'+str(side),'LOD0_ChargeCoolantHose_'+str(side))}
    before={n:row(o) for n,o in objects.items()};staged={};made=[];proof={}
    try:
        for side in (-1,1):
            specs=[('HotChargePipe',recipe.HOT,.030,10,{4:(0,1,0),5:(0,1,0)},'LOD0_HotVTurbo_'+str(side)),
                   ('ColdChargePipe',recipe.COLD,recipe.COLD_RADII,10,{0:(side,0,0),1:(side,0,0),5:(0,-1,0),7:(-side,0,0)},'LOD0_IntakePlenum_'+str(side)),
                   ('ChargeCoolantHose',recipe.COOLANT,.012,8,{0:(side,0,0),1:(side,0,0),7:(-side,0,0),8:(-side,0,0)},None)]
            for kind,points,radii,sides,overrides,receiver in specs:
                name='LOD0_'+kind+'_'+str(side);old=objects[name];col=old.users_collection[0];mat=old.data.materials[0]
                obj,info=make_tube(geo,recipe,'Private_Bend_'+kind,recipe.mirror(points,side),radii,mat,col,sides,overrides,SPLITS[kind])
                made.append(obj);uncut=row(obj);metric={}
                if receiver:
                    recipe.explicit_input(obj)
                    reference=row(bpy.data.objects[receiver])
                    cutter=geo.mesh('Private_Bend_EndReceiver',reference['vertices'],reference['triangles'],None,col)
                    made.append(cutter);geo.boolean(obj,cutter);recipe.remove(cutter);made.remove(cutter)
                    recipe.material_only(obj,mat)
                    obj.data.normals_split_custom_set([tuple(n.vector) for n in obj.data.corner_normals])
                    metric['repair']=repair(obj,exact_scan,geo.evaluated_counts)
                    assert row(bpy.data.objects[receiver])==reference,'Receiver changed'
                metric['simplify']=simplify(obj,geo)
                current=row(obj);metric['quality']=geo.evaluated_counts(obj);metric['self']=exact_scan(current)
                assert metric['self']['status']=='passed',name+' exact self failed'
                for key in ('duplicate_faces','nonmanifold_edges','degenerate_faces','degenerate_triangles',
                            'triangulated_duplicate_faces','triangulated_nonmanifold_edges',
                            'nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals'):
                    if key in metric['quality']:assert metric['quality'][key]==0,(name,key)
                metric['old_triangles']=len(before[name]['triangles']);metric['new_triangles']=len(current['triangles'])
                metric['delta']=metric['new_triangles']-metric['old_triangles']
                metric['stations']=info;metric['uncut']=uncut
                staged[name]=obj;proof[name]=metric
        result=[]
        for name,obj in staged.items():
            dst=objects[name];inverse=dst.matrix_world.inverted()
            for vertex in obj.data.vertices:vertex.co=inverse@(obj.matrix_world@vertex.co)
            dst.modifiers.clear();dst.data=obj.data
            bpy.data.objects.remove(obj,do_unlink=True);made.remove(obj);result.append(dst)
        bpy.context.view_layer.update()
        return result,proof,before
    finally:
        for obj in list(made):
            if obj.name in bpy.data.objects:recipe.remove(obj)
