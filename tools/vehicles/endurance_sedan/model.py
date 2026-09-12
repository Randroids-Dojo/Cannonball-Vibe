"""Fresh parameterized sedan surfaces, independent of the Hero GT geometry."""

import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import geometry as geo


CURVED_PROFILES = False
BODY_UPPER_SURFACE = None
BODY_FRONT_FENDER_REFERENCE = None


def front_surface_y(x,z):
    """Original pre-cut body front surface shared by fascia and optical fit."""
    if BODY_UPPER_SURFACE is None:raise ValueError('Front fascia needs the locked pre-cut body')
    hit=BODY_UPPER_SURFACE.ray_cast(Vector((x,3,z)),Vector((0,-1,0)),2)[0]
    if hit is None:raise ValueError(f'Front fascia misses body at {x},{z}')
    return hit.y


def rear_surface_y(x,z):
    """Shared original body contour for the fitted rear optical assembly."""
    if BODY_UPPER_SURFACE is None:raise ValueError('Rear optics need the locked pre-cut body')
    hit=BODY_UPPER_SURFACE.ray_cast(Vector((x,-3,z)),Vector((0,1,0)),2)[0]
    if hit is None:raise ValueError(f'Rear optics miss body at {x},{z}')
    return hit.y


def upper_surface_z(x,y):
    if BODY_UPPER_SURFACE is None:
        return deck(y)+.014*(x/.756)**2
    hit=BODY_UPPER_SURFACE.ray_cast(Vector((x,y,2)),Vector((0,0,-1)),3)[0]
    if hit is None:raise ValueError(f'Closure misses original body upper surface at {x},{y}')
    return hit.z


def closure_z(name,x,y,halfwidth):
    y0,y1=(.803,2.226) if name=='Hood' else (-2.385,-2.020)
    v=(y-y0)/(y1-y0)
    crown=.022*math.sin(math.pi*v)*(1-(x/halfwidth)**2) if name=='Hood' else 0
    return upper_surface_z(x,y)+crown


def interp(value, points):
    if CURVED_PROFILES:
        return monotone_curve(value, points)
    for (a,av),(b,bv) in zip(points,points[1:]):
        if value <= b:
            t=max(0,min(1,(value-a)/(b-a)))
            return av+(bv-av)*t
    return points[-1][1]


def monotone_curve(value, points):
    """C1 Hermite profiles without overshoot at locked width/height maxima."""
    slopes = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(points, points[1:])]
    tangents = [slopes[0]]
    for left, right in zip(slopes, slopes[1:]):
        tangents.append(0 if left * right <= 0 else 2 * left * right / (left + right))
    tangents.append(slopes[-1])
    for i, ((a, av), (b, bv)) in enumerate(zip(points, points[1:])):
        if value <= b:
            t = max(0, min(1, (value - a) / (b - a)))
            return (2*t**3 - 3*t*t + 1)*av + (t**3 - 2*t*t + t)*(b-a)*tangents[i] + (-2*t**3 + 3*t*t)*bv + (t**3 - t*t)*(b-a)*tangents[i+1]
    return points[-1][1]


def width(y):
    return interp(y,[(-2.54,.83),(-2.30,.91),(-1.46,.95),(-.60,.929),(.60,.929),(1.46,.95),(2.08,.919),(2.40,.825)])


def deck(y):
    return interp(y,[(-2.54,.865),(-2.40,.92),(-1.94,.991),(-1.46,.997),(.74,.99),(1.46,.925),(2.17,.848),(2.40,.823 if CURVED_PROFILES else .75)])


def surface(name, function, nu, nv, thickness, material, collection, parent):
    vertices=[function(i/nu,j/nv) for i in range(nu+1) for j in range(nv+1)]
    faces=[]
    for i in range(nu):
        for j in range(nv):
            a=i*(nv+1)+j
            faces.append((a,a+1,a+nv+2,a+nv+1))
    obj=geo.mesh(name,vertices,faces,material,collection,parent,smooth=True)
    if sum(p.normal.z for p in obj.data.polygons)<0:
        bm=bmesh.new();bm.from_mesh(obj.data)
        bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free()
    solid=obj.modifiers.new("Physical sheet thickness","SOLIDIFY")
    solid.thickness=thickness
    solid.offset=-1
    solid.use_even_offset=True
    return obj


def remove(obj):
    bpy.data.objects.remove(obj,do_unlink=True)


def inset_polygon(points, distance):
    """Offset convex y/z closure boundaries inward by a physical gap."""
    points=[Vector(p) for p in points]
    center=sum(points,Vector((0,0)))/len(points)
    lines=[]
    for a,b in zip(points,points[1:]+points[:1]):
        direction=(b-a).normalized()
        normal=Vector((-direction.y,direction.x))
        if normal.dot(center-(a+b)/2)<0:
            normal=-normal
        lines.append((a+normal*distance,direction))
    result=[]
    for (a,u),(b,v) in zip(lines[-1:]+lines[:-1],lines):
        cross=u.x*v.y-u.y*v.x
        t=((b-a).x*v.y-(b-a).y*v.x)/cross
        result.append(tuple(a+u*t))
    return result


def fascia_roll(z):
    radius=3.457
    return radius-math.sqrt(radius*radius-(z-.550)**2)


def lower_body(collection, lod, mats):
    ys=sorted(set([-2.54+i*4.94/48 for i in range(49)]+[-2.4,-1.94,-1.46,.74,1.46,1.82,2.17,2.4]))
    # Distinct Python stations can encode as exactly the same Blender float32.
    # Keep the first actual native Y station; avoid a zero-width closing ring.
    unique=[]
    for station in ys:
        if not unique or Vector((0,station,0)).y!=Vector((0,unique[-1],0)).y:
            unique.append(station)
    ys=unique
    vertices=[];rings=[]
    for y in ys:
        w=width(y); top=deck(y)
        half=[(0,.135),(.72*w,.135),(.91*w,.20),(.982*w,.39),(w,.67),(.996*w,top-.075),(.94*w,top+.016),(.80*w,top+.017),(0,top)]
        if CURVED_PROFILES:
            # Sample a monotone C1 cross section through the declared stations.
            # Width and deck extrema stay locked while highlights flow across
            # the shoulder rather than breaking across a faceted extrusion.
            xp=list(enumerate(p[0] for p in half));zp=list(enumerate(p[1] for p in half))
            parameters=[i/3 for i in range(25)]
            # Refine front shoulder sampling; preserve the remaining body tessellation.
            if y>=1.82:parameters=sorted(set(parameters+[5+i/9 for i in range(19)]))
            from .shoulder_profile import profile as shoulder_profile
            half=[tuple(axis[0] for axis in shoulder_profile(t,y,w,top))
                  if y>1.90 and 5.65<t<6.35 else
                  (monotone_curve(t,xp),monotone_curve(t,zp)) for t in parameters]
        else:parameters=list(range(len(half)))
        loop=half+[(-x,z) for x,z in half[-2:0:-1]]
        keys=parameters+[16-t for t in reversed(parameters[1:-1])]
        rings.append((list(range(len(vertices),len(vertices)+len(loop))),keys))
        for x,z in loop:
            adjusted_y=y
            if CURVED_PROFILES and y>2.05:
                adjusted_y-=.15*(abs(x)/w)**3*((y-2.05)/.35)**2
            if CURVED_PROFILES and y<-2.25:
                adjusted_y+=.105*(abs(x)/w)**3*((-2.25-y)/.29)**2
            if CURVED_PROFILES and y>2.230:
                t=max(0.,min(1.,(y-2.230)/.170))
                adjusted_y-=fascia_roll(z)*t*t*t*(10+t*(-15+6*t))
            vertices.append((x,adjusted_y,z))
    faces=[]
    for (left,lk),(right,rk) in zip(rings,rings[1:]):
        i=j=0
        while i<len(left) or j<len(right):
            next_left=lk[i+1] if i+1<len(left) else 16
            next_right=rk[j+1] if j+1<len(right) else 16
            a=left[i%len(left)];b=right[j%len(right)]
            if abs(next_left-next_right)<1e-9:
                faces.append((a,b,right[(j+1)%len(right)],left[(i+1)%len(left)]));i+=1;j+=1
            elif next_left<next_right:
                faces.append((a,b,left[(i+1)%len(left)]));i+=1
            else:
                faces.append((a,b,right[(j+1)%len(right)]));j+=1
    faces.append(tuple(reversed(rings[0][0])))
    boundary=rings[-1][0]
    if CURVED_PROFILES:
        cap_center=(0.,.550)
        previous=None
        center_index=len(vertices)
        vertices.append((0.,2.40-fascia_roll(cap_center[1]),cap_center[1]))
        for fraction in (.25,.5,.75,1.):
            if fraction==1.:
                current=boundary
            else:
                current=[]
                for index in boundary:
                    x,_,z=vertices[index]
                    x*=fraction
                    z=cap_center[1]+(z-cap_center[1])*fraction
                    current.append(len(vertices))
                    vertices.append((x,2.40-.15*(abs(x)/width(2.40))**3-fascia_roll(z),z))
            for j in range(len(current)):
                following=(j+1)%len(current)
                if previous is None:
                    faces.append((center_index,current[j],current[following]))
                else:
                    faces.append((previous[j],current[j],current[following],previous[following]))
            previous=current
    else:
        faces.append(tuple(boundary))
    body=geo.mesh("LOD0_StructuralBody",vertices,faces,mats['paint'],collection,lod,smooth=True)
    if CURVED_PROFILES:
        cap_indices=set(boundary)|{center_index}|set(range(center_index,len(vertices)))
        cap_polygon_ids=[int(p.index) for p in body.data.polygons if set(p.vertices)<=cap_indices]
        cap_loop_vertices=[(int(i),int(body.data.loops[i].vertex_index)) for p in body.data.polygons if p.index in cap_polygon_ids for i in p.loop_indices]
        perimeter={tuple(sorted((a,b))) for a,b in zip(boundary,boundary[1:]+boundary[:1])}
        edge_ids=[int(e.index) for e in body.data.edges if tuple(sorted(e.vertices)) in perimeter]
        if len(edge_ids)!=len(boundary):raise ValueError('Missing original cap perimeter edges')
        marker=body.data.attributes.new(name='cb_fascia_cap',type='INT',domain='FACE')
        for index in cap_polygon_ids:marker.data[index].value=1
        weights=body.data.attributes.new(name='bevel_weight_edge',type='FLOAT',domain='EDGE')
        for index in edge_ids:
            edge=body.data.edges[index]
            z=sum(body.data.vertices[v].co.z for v in edge.vertices)/2
            t=max(0.,min(1.,(z-.670)/.100))
            weights.data[index].value=t*t*t*(10-15*t+6*t*t)
        def field(point):
            x,y,z=point
            return Vector((.45*x*abs(x)/width(2.4)**3,1.,(z-.550)/math.sqrt(3.457**2-(z-.550)**2))).normalized()
        corners=[v.vector.copy() for v in body.data.corner_normals]
        for loop,vertex in cap_loop_vertices:corners[loop]=field(body.data.vertices[vertex].co)
        body.data.normals_split_custom_set(corners)
        radius=body.modifiers.new('Original formed front perimeter18mm','BEVEL')
        radius.width=.018;radius.segments=3;radius.limit_method='WEIGHT';radius.harden_normals=True
        radius.face_strength_mode='FSTR_ALL'
        bpy.context.view_layer.objects.active=body
        bpy.ops.object.modifier_apply(modifier=radius.name)
        marker=body.data.attributes['cb_fascia_cap']
        strength=body.data.attributes['__mod_weightednormals_faceweight']
        for face in body.data.polygons:
            if marker.data[face.index].value==1 and strength.data[face.index].value!=16384:
                marker.data[face.index].value=2
        body['formed_front_perimeter_m']=.018
        geo.project_uv(body)
    # C1 longitudinal profiles produce nonplanar quads at shoulder corners.
    # Give the exact solid boolean solver explicit planar faces first.
    if CURVED_PROFILES:
        triangulate=body.modifiers.new('Planar boolean input','TRIANGULATE')
        bpy.context.view_layer.objects.active=body
        bpy.ops.object.modifier_apply(modifier=triangulate.name)
        geo.repair_triangulation(body)
        global BODY_UPPER_SURFACE, BODY_FRONT_FENDER_REFERENCE
        bpy.context.view_layer.update()
        BODY_UPPER_SURFACE=BVHTree.FromObject(body,bpy.context.evaluated_depsgraph_get())
        from . import fender_field
        BODY_FRONT_FENDER_REFERENCE=fender_field.capture(body)
    # Real holes are needed for a usable cockpit and later opening inspection.
    for name,center,size in [
        ('CabinVoid',(0,-.55,1.12),(1.64,2.62,1.76)),
        ('EngineVoid',(0,1.5145,1.0),(1.52,1.431,1.46)) if CURVED_PROFILES else ('EngineVoid',(0,1.49,1.0),(1.52,1.48,1.46)),
        ('TrunkVoid',(0,-2.2025,1.220),(1.58,.372,.56)),
    ]:
        cutter=geo.box(name,center,size,None,collection,radius=0)
        geo.boolean(body,cutter);remove(cutter)
    # Preserve the lower cargo volume while leaving the upper rear sill
    # behind the closed lid. The old box perforated a 45 mm slot here.
    cavity=geo.prism_x('TrunkInterior',
        [(-2.430,.295),(-1.500,.295),(-1.500,.945),
         (-2.3885,.945),(-2.3885,.880),(-2.430,.880)],
        -.790,.790,None,collection)
    geo.boolean(body,cavity);remove(cavity)
    for side in (-1,1):
        for y in (-1.46,1.46):
            # The tunnel ends inboard of the full steering envelope.
            points=[(side*.90,y,.3433),(side*1.30,y,.3433)]
            points[0]=(side*.46,y,.3433)
            cutter=geo.tube('WheelArchCutter',points,.4483,None,collection,sides=64)
            geo.boolean(body,cutter);remove(cutter)
    return body


def split_door_outlines():
    return {
        'F':[(.605,1.035),(-.543,1.035),(-.526,.280),(.675,.280)],
        'R':[(-.645,1.035),(-1.708,1.035),(-1.185,.637),(-1.015,.280),(-.630,.280)],
    }


def split_doors(body, collection, mats, pivots):
    outlines=split_door_outlines()
    for side,symbol in [(-1,'L'),(1,'R')]:
        lo,hi=sorted((side*.78,side*1.08))
        for axle,outline in outlines.items():
            suffix=axle+symbol
            cut=geo.prism_x('DoorCut',outline,lo,hi,None,collection)
            panel=body.copy();panel.data=body.data.copy();panel.name='LOD0_Door_'+suffix
            collection.objects.link(panel)
            panel.modifiers.clear()
            panel.parent=body.parent
            inner=geo.prism_x('DoorInset',inset_polygon(outline,.0035),lo,hi,None,collection)
            geo.boolean(panel,inner,'INTERSECT')
            geo.boolean(body,cut)
            remove(inner);remove(cut)
            if axle=='F' and CURVED_PROFILES:
                # Taper the inner trailing return away from the fixed pillar.
                # The exterior edge at X>=.875 keeps its authored shut line.
                vertices=[]
                for z in (.275,1.045):
                    for x in (.760,.875):
                        rear=-.526-.017*(z-.280)/.755
                        limit=rear+.0035+.010*(.875-x)/.115
                        vertices.extend([(side*x,-.70,z),(side*x,limit,z)])
                faces=[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
                relief=geo.mesh('FrontDoorInnerReturnRelief',vertices,faces,None,collection)
                geo.boolean(panel,relief);remove(relief)
            if axle=='R':
                # The inner stamped return steps away from the fixed liner;
                # the outboard arch and exterior shut line remain intact.
                wheel_relief=geo.tube('RearDoorInnerArchRelief',[(side*.76,-1.46,.3433),(side*.931,-1.46,.3433)],[.525,.495],None,collection,sides=48)
                geo.boolean(panel,wheel_relief);remove(wheel_relief)
                low,high=sorted((side*.760,side*.880))
                aft_relief=geo.prism_x('RearDoorAftReturnRelief',[(-1.80,.850),(-1.426,.850),(-1.670,1.045),(-1.80,1.045)],low,high,None,collection)
                geo.boolean(panel,aft_relief);remove(aft_relief)
            geo.bevel(panel,.0012,2)
            geo.parent_at_pivot(panel,pivots['Door_'+suffix])
            panel['closure_gap_m']=.0035
            # A simple door card already provides a readable cabin envelope.
            card_outline=[(y,min(z,.94)) for y,z in inset_polygon(outline,.055 if axle=='R' else .026)]
            card_low,card_high=sorted((side*.790,side*.821))
            card=geo.prism_x('LOD0_DoorCard_'+suffix,card_outline,card_low,card_high,mats['leather'],collection,body.parent)
            if axle=='R':
                clearance=geo.tube('RearDoorTrimWheelRelief',[(side*.70,-1.46,.3433),(side*.90,-1.46,.3433)],.505,None,collection,sides=64)
                geo.boolean(card,clearance);remove(clearance)
            geo.bevel(card,.005,3)
            geo.parent_at_pivot(card,pivots['Door_'+suffix])


def closures(collection,lod,mats,pivots):
    for name,y0,y1,halfwidth in [('Hood',.803 if CURVED_PROFILES else .744,2.226,.756),('Trunk',-2.385,-2.020 if CURVED_PROFILES else -1.935,.786)]:
        def f(u,v,y0=y0,y1=y1,halfwidth=halfwidth):
            y=y0+(y1-y0)*v;x=(2*u-1)*halfwidth
            return (x,y,closure_z(name,x,y,halfwidth) if CURVED_PROFILES else deck(y)+.014*(x/halfwidth)**2)
        obj=surface('LOD0_'+name,f,12 if name=='Hood' else 10,18 if name=='Hood' else 10,.0012,mats['paint'],collection,lod)
        geo.bevel(obj,.0012,2)
        geo.parent_at_pivot(obj,pivots['Hood_Hinge' if name=='Hood' else 'Trunk_Hinge'])


def roof_shape(y):
    return (interp(y,[(-1.27,.689),(-.45,.742),(.14,.691)]),
            interp(y,[(-1.27,1.37),(-.45,1.45),(.14,1.395)]))


def formed_a_pillar(roof_obj, side, symbol, collection, lod, material):
    """A closed original ribbon, fitted to the actual evaluated roof underside."""
    from mathutils.bvhtree import BVHTree

    bpy.context.view_layer.update()
    evaluated=roof_obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=evaluated.to_mesh();mesh.calc_loop_triangles()
    roof_vertices=[evaluated.matrix_world@v.co for v in mesh.vertices]
    roof_triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
    roof_bvh=BVHTree.FromPolygons(roof_vertices,roof_triangles,all_triangles=True)
    evaluated.to_mesh_clear()

    def upper_point(y):
        points=[]
        for triangle in roof_triangles:
            for j in range(3):
                a=roof_vertices[triangle[j]];b=roof_vertices[triangle[(j+1)%3]]
                if abs(a.y-y)<1e-6:points.append(a)
                if (a.y-y)*(b.y-y)<0:points.append(a+(b-a)*((y-a.y)/(b.y-a.y)))
        if not points:raise RuntimeError('A-pillar roof section is absent')
        extent=max(side*p.x for p in points)
        edge=max((p for p in points if extent-side*p.x<1e-6),key=lambda p:p.z)
        hit=roof_bvh.ray_cast(Vector((edge.x-side*.0001,y,1.2)),Vector((0,0,1)),.5)[0]
        if hit is None:raise RuntimeError('A-pillar cannot reach the roof underside')
        return hit

    w0=Vector((side*.828,.740,.970));w1=upper_point(.128)
    d0=Vector((side*.87156,.622,1.028));d1=upper_point(.107)
    spans=12;cross_spans=3;vertices=[]
    for i in range(spans+1):
        t=i/spans;w=w0.lerp(w1,t);d=d0.lerp(d1,t)
        for j in range(cross_spans+1):
            s=j/cross_spans;tangent=(w1-w0).lerp(d1-d0,s)
            normal=(tangent.cross(d-w)*side).normalized()
            vertices.append(w.lerp(d,s)+normal*(.004*math.sin(math.pi*s)*math.sin(math.pi*t)))
    windshield_normal=Vector((0,.425,.600)).normalized()
    for index,p in enumerate(list(vertices)):
        s=(index%(cross_spans+1))/cross_spans
        inward=windshield_normal.lerp(Vector((side,0,.48)).normalized(),s).normalized()
        fraction=max(0.,min(1.,(p.z-1.10)/.14))
        weight=fraction*fraction*(3-2*fraction)
        common=Vector((side*.5,.289,.624)).normalized()
        inward=inward.lerp(common,weight).normalized()
        vertices.append(p-inward*.018)
    stride=cross_spans+1;layer=(spans+1)*stride;faces=[]
    for i in range(spans):
        for j in range(cross_spans):
            a=i*stride+j;b=(i+1)*stride+j
            faces.extend([(a,b,b+1,a+1),(a+layer,a+1+layer,b+1+layer,b+layer)])
    boundary=[i*stride for i in range(spans+1)]
    boundary += [spans*stride+j for j in range(1,cross_spans+1)]
    boundary += [i*stride+cross_spans for i in reversed(range(spans))]
    boundary += list(reversed(range(1,cross_spans)))
    for a,b in zip(boundary,boundary[1:]+boundary[:1]):faces.append((a,a+layer,b+layer,b))
    pillar=geo.mesh('LOD0_PillarA_'+symbol,vertices,faces,material,collection,lod,smooth=True)
    pillar['assembly_boundary']='Original formed ribbon; upper boundary butts against evaluated roof underside'
    pillar['formed_return_m']=.018
    pillar['inner_return_sections']='Coherent common inward direction above Z1.24; smooth transition from original lower section over Z1.10..1.24m; depth18mm'
    return pillar


def greenhouse(collection,lod,mats,pivots,spec=None):
    def roof(u,v):
        y=-1.27+1.41*v
        half,center=roof_shape(y)
        x=(u*2-1)*half
        return (x,y,center-.026*math.sin(math.pi*v)*(abs(x)/half)**2)
    roof_panel=surface('LOD0_Roof',roof,14,16,.0012,mats['paint'],collection,lod)
    if CURVED_PROFILES:
        # An enclosed formed rail supplies the missing roof-side depth. Its
        # lower face stays above the actual glass/frame envelope; the upper
        # face follows the same roof curve, rather than a detached straight bar.
        for side,symbol in ((-1,'L'),(1,'R')):
            vertices=[];steps=24
            lower_heights=spec['original_packaging']['finish_revision15']['formed_header_wall']['lower_z_by_side_m'][symbol]
            if len(lower_heights)!=steps+1:raise ValueError('Header wall requires the locked25-station table')
            for i in range(steps+1):
                y=-1.230+1.330*i/steps;v=(y+1.27)/1.41
                half,center=roof_shape(y)
                height=lambda x:center-.026*math.sin(math.pi*v)*(x/half)**2
                outer=half-.001
                # A stamped2 mm flange follows the real roof cross crown;
                # the35 mm-deep closed section stays farther inboard.
                underside=lambda x:(height(outer)-.0032)+(height(.620)-height(outer))*(outer-x)/(outer-.620)
                vertices.extend([(side*outer,y,height(outer)-.0012),
                                 (side*outer,y,height(outer)-.0032),
                                 (side*.668,y,underside(.668)),
                                 (side*.668,y,lower_heights[i]),
                                 (side*.662,y,lower_heights[i]),
                                 (side*.662,y,underside(.662)),
                                 (side*.620,y,height(.620)-.0032),
                                 (side*.620,y,height(.620)-.035),
                                 (side*.592,y,height(.592)-.035),
                                 (side*.592,y,height(.592)-.0012)])
            faces=[]
            for i in range(steps):
                for j in range(10):faces.append((10*i+j,10*i+(j+1)%10,10*(i+1)+(j+1)%10,10*(i+1)+j))
            faces.extend([tuple(reversed(range(10))),tuple(10*steps+i for i in range(10))])
            rail=geo.mesh('LOD0_RoofSideRail_'+symbol,vertices,faces,mats['paint'],collection,lod,smooth=True)
            rail['assembly_boundary']='Finite welded reinforcement flange within evaluated roof skin; |X| .592.. .741, Y-1.230.. .100; penetration <=.65mm and remaining outer skin >=.55mm; no outer protrusion or body-wide contact exception'
    for name,yl,zl,wl,yh,zh,wh in [('Windshield',.74,.97,.820,.14,1.395,.687),('Backlight',-1.94,.99,.810,-1.27,1.37,.685)]:
        def glass(u,v,yl=yl,zl=zl,wl=wl,yh=yh,zh=zh,wh=wh):
            return ((2*u-1)*(wl+(wh-wl)*v),yl+(yh-yl)*v,zl+(zh-zl)*v)
        surface('LOD0_'+name,glass,8,6,.0045,mats['glass_rear'] if name=='Backlight' and CURVED_PROFILES else mats['glass'],collection,lod)
        corners=[glass(0,0),glass(1,0),glass(1,1),glass(0,1)]
        geo.tube('LOD0_'+name+'Seal',corners,.010,mats['rubber'],collection,lod,sides=8,closed=True)
    for side,symbol in [(-1,'L'),(1,'R')]:
        outlines=[('F',[(.597,1.028),(-.534,1.028),(-.532,1.397),(.094,1.365)]),
                  ('R',[(-.655,1.028),(-1.667,1.028),(-1.263,1.330),(-.655,1.395)])]
        for axle,points in outlines:
            def position(y,z):
                x=.885-(z-1.0)*.48
                return (side*x,y,z)
            verts=[position(y,z) for y,z in points]
            glass=geo.mesh('LOD0_DoorGlass_'+axle+symbol,verts,[(0,1,2,3)],mats['glass_rear'] if axle=='R' and CURVED_PROFILES else mats['glass'],collection,lod)
            if glass.data.polygons[0].normal.x*side<0:
                bm=bmesh.new();bm.from_mesh(glass.data)
                bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(glass.data);bm.free()
            solid=glass.modifiers.new('Laminated glass thickness','SOLIDIFY');solid.thickness=.0045
            seal=geo.tube('LOD0_DoorGlassSeal_'+axle+symbol,verts,.013,mats['rubber'],collection,lod,sides=8,closed=True)
            frame=geo.tube('LOD0_DoorFrame_'+axle+symbol,verts,.012 if CURVED_PROFILES else .020,mats['paint'],collection,lod,sides=8,closed=True)
            for obj in (glass,seal,frame):geo.parent_at_pivot(obj,pivots['Door_'+axle+symbol])
        for name,points,radius in [('A',[(side*.86,.735,.964),(side*.704,.14,1.385)],.025),
                                  ('B',[(side*.746,-.595,.281),(side*.659,-.595,1.405)],.024),
                                  ('C',[(side*.812,-1.895,.996),(side*.658,-1.267,1.35)],.030)]:
            if name=='A' and CURVED_PROFILES:
                formed_a_pillar(roof_panel,side,symbol,collection,lod,mats['paint'])
            else:
                geo.tube('LOD0_Pillar'+name+'_'+symbol,points,radius,mats['paint'],collection,lod,sides=10)
        if CURVED_PROFILES:
            boundary=[(-.551,1.016),(-.637,1.016),(-.637,1.407),(-.551,1.415)]
            verts=[(side*(.885-(z-1)*.48),y,z) for y,z in boundary]
            pillar=geo.mesh('LOD0_StampedPillar_B'+symbol,verts,[(0,1,2,3)],mats['trim'],collection,lod,smooth=True)
            if pillar.data.polygons[0].normal.x*side<0:
                bm=bmesh.new();bm.from_mesh(pillar.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(pillar.data);bm.free()
            solid=pillar.modifiers.new('B-pillar formed depth','SOLIDIFY');solid.thickness=.024;solid.offset=-1
            geo.bevel(pillar,.002,2)
            for name,points in [
                ('C',[(side*.875,-1.743,1.022),(side*.812,-1.941,.992),(side*.687,-1.271,1.370),(side*.717,-1.298,1.330)])]:
                panel=geo.mesh('LOD0_StampedPillar_'+name+symbol,points,[(0,1,2,3)],mats['paint'],collection,lod,smooth=True)
                solid=panel.modifiers.new('Pillar outer skin','SOLIDIFY');solid.thickness=.012
                geo.bevel(panel,.003,3)


def blockout_cabin(collection,lod,mats):
    floor=geo.box('LOD0_CabinFloor',(0,-.54,.252),(1.57,2.51,.028),mats['carpet'],collection,lod,radius=0)
    # The floor wraps the rear wheel tubs; a rectangle crosses the tires.
    # This 448.3 mm tunnel includes static radius, full bump and clearance.
    for side in (-1,1):
        cutter=geo.tube('FloorWheelTubCut',[(side*.59,-1.46,.3433),(side*1.12,-1.46,.3433)],.4483,None,collection,sides=64)
        geo.boolean(floor,cutter);remove(cutter)
    geo.bevel(floor,.003,2)
    geo.box('LOD0_Dashboard',(0,.62,.827),(1.57,.34,.22),mats['trim'],collection,lod,radius=.055)
    geo.box('LOD0_Console',(0,-.05,.455),(.27,1.15,.26),mats['trim'],collection,lod,radius=.026)
    for row,cy in [('Front',-.18),('Rear',-1.11)]:
        for side,cx in [('L',-.43),('R',.43)]:
            geo.box('LOD0_'+row+'SeatBase_'+side,(cx,cy,.435),(.49,.53,.16),mats['leather'],collection,lod,radius=.055)
            geo.box('LOD0_'+row+'SeatBack_'+side,(cx,cy-.245,.78),(.49,.14,.64),mats['leather'],collection,lod,radius=.05)
            geo.box('LOD0_'+row+'Headrest_'+side,(cx,cy-.25,1.16),(.255,.13,.18),mats['leather'],collection,lod,radius=.04)
    geo.box('LOD0_AuxiliaryTank',(0,-1.80,.46),(.90,.48,.28),mats['alloy'],collection,lod,radius=.018)
    geo.box('LOD0_EngineEnvelope',(0,1.46,.57),(.72,.88,.53),mats['trim'],collection,lod,radius=.055)


def blockout_wheels(collection,mats,pivots,spec):
    radius=spec['geometry']['wheel_radius_m'];half=.1275
    profile=[(-half+.017,.2413),(-half,.282),(-half+.009,.322),(-half+.028,radius),
             (half-.028,radius),(half-.009,.322),(half,.282),(half-.017,.2413)]
    for suffix in ('FL','FR','RL','RR'):
        parent=pivots['Wheel_'+suffix]
        geo.ring_x('LOD0_Tire_'+suffix,profile,(0,0,0),mats['rubber'],collection,parent,64)
        geo.ring_x('LOD0_Rim_'+suffix,[(-.108,.227),(-.108,.244),(.108,.244),(.108,.227)],(0,0,0),mats['wheel'],collection,parent,48)
        side=-1 if suffix.endswith('L') else 1
        for j in range(10):
            a=2*math.pi*j/10
            geo.tube('LOD0_Spoke_'+suffix+'_'+str(j),[(side*.108,.052*math.sin(a),.052*math.cos(a)),(side*.098,.226*math.sin(a+.09),.226*math.cos(a+.09))],.013,mats['wheel'],collection,parent,sides=6)
        r=.1995 if suffix.startswith('F') else .178
        geo.ring_x('LOD0_BrakeDisc_'+suffix,[(-.030,.067),(-.030,r),(-.010,r),(-.010,.067)],(side*.04,0,0),mats['metal'],collection,parent,48)
        geo.box('LOD0_Caliper_'+suffix,(side*.035,-.14,.035),(.075,.11,.18),mats['caliper'],collection,pivots['Suspension_'+suffix],radius=.025)


def build_blockout(collection,lod,mats,pivots,spec):
    body=lower_body(collection,lod,mats)
    split_doors(body,collection,mats,pivots)
    geo.bevel(body,.0012,2)
    closures(collection,lod,mats,pivots)
    greenhouse(collection,lod,mats,pivots)
    blockout_cabin(collection,lod,mats)
    blockout_wheels(collection,mats,pivots,spec)
    for name in ('Mirror_Left','Mirror_Right','Mirror_Rear'):
        location=spec['hardpoints_source_m'][name]
        size=(.146,.095,.085) if name!='Mirror_Rear' else (.235,.024,.066)
        geo.box('LOD0_'+name+'Housing',location,size,mats['trim'],collection,lod,radius=.014)
        mirror=geo.box('LOD0_'+name+'Surface',(location[0],location[1]-size[1]/2-.002,location[2]),(size[0]*.87,.003,size[2]*.87),mats['mirror'],collection,lod,radius=.001)
        geo.parent_at_pivot(mirror,pivots[name])
    for name in [n for n in pivots if n.startswith('Light_')]:
        key='headlight' if 'Head_' in name else 'taillight'
        if 'Brake' in name:key='brake'
        if 'Reverse' in name:key='reverse'
        if 'Indicator' in name:key='indicator_left' if name.endswith(('FL','RL')) else 'indicator_right'
        geo.box('LOD0_'+name+'Lens',(0,0,0),(.21,.015,.024),mats[key],collection,pivots[name],radius=.005)


def build_production(collection, lod, mats, pivots, controls, spec):
    from . import cabin, cabin_floor_panels, construction, exterior, floor_panels, mechanisms, pillar_joints, powertrain, source_dashboard, wheels

    global CURVED_PROFILES
    CURVED_PROFILES = True
    from . import fascia_surface
    fascia_surface.validate(spec['original_packaging']['fascia_revision21'])
    body = lower_body(collection, lod, mats)
    split_doors(body, collection, mats, pivots)
    closures(collection, lod, mats, pivots)
    greenhouse(collection, lod, mats, pivots, spec)
    exterior.fascia(body, collection, lod, mats, pivots, spec)
    exterior.closures_and_trim(collection, lod, mats, pivots)
    exterior.mirrors(collection, lod, mats, pivots, spec)
    cabin.build(collection, lod, mats, pivots, spec)
    wheels.build(collection, mats, pivots, spec)
    before_powertrain=set(collection.objects)
    powertrain.build(body, collection, lod, mats, pivots)
    # Inspection forces LOD0; hidden engine/trunk/underbody internals need not
    # survive the medium/far driving silhouettes. Exterior exhaust lips remain.
    for obj in set(collection.objects)-before_powertrain:
        if obj.type=='MESH':obj['maximum_lod']=0
    mechanisms.wipers(collection, lod, mats, pivots, spec)
    mechanisms.source_controls(pivots, controls, mats, spec)
    source_dashboard.build(collection,lod,mats,pivots,controls,spec)
    construction.build(body,collection,lod,mats,pivots,spec)
    split_bumpers(body,collection,lod,mats)
    geo.bevel(body, .0012, 2)
    floor_panels.build(body, collection, lod, mats)
    pillar_joints.build(body, collection)
    cabin_floor_panels.build(body, collection, lod, mats)


def split_bumpers(body,collection,lod,mats):
    """Separate molded bumper covers with a measured 3.5 mm closure gap."""
    for name,center,size,inner_center,inner_size in [
        ('FrontBumper',(0,2.225,.60),(2.4,.710,1.0),(0,2.22675,.60),(2.4,.7065,1.0)),
        ('RearBumper',(0,-2.33,.436),(2.4,.606,.609),(0,-2.33175,.43425),(2.4,.6025,.6055))]:
        cutter=geo.box('BumperBoundary',center,size,None,collection,radius=0)
        inset=geo.box('BumperGap',inner_center,inner_size,None,collection,radius=0)
        panel=body.copy();panel.data=body.data.copy();panel.name='LOD0_'+name
        collection.objects.link(panel);panel.parent=lod;panel.modifiers.clear()
        geo.boolean(panel,inset,'INTERSECT');geo.boolean(body,cutter)
        remove(cutter);remove(inset)
        panel['closure_gap_m']=.0035
        geo.bevel(panel,.0012,2)
        if name=='FrontBumper':
            panel.modifiers[-1].angle_limit=1.0
            panel.modifiers[-1].face_strength_mode='FSTR_ALL'
