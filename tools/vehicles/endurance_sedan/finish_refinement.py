"""Bounded original automotive finish refinement, separate from engineering hardpoints.

Candidate work is deliberately piloted against a preserved source checkpoint.
No imported meshes, donor identity or new material inputs are used.
"""
import math
import json

import bmesh
import bpy
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree

from . import geometry as geo


def replace_world_mesh(obj, vertices, faces, material=None, smooth=True):
    """Keep the actual semantic parent/transform while replacing an owned surface."""
    inverse = obj.matrix_world.inverted()
    temporary = geo.mesh(obj.name + '_Refined', [inverse @ Vector(v) for v in vertices], faces,
                         material or obj.data.materials[0], obj.users_collection[0], smooth=smooth)
    old = obj.data
    obj.modifiers.clear()
    obj.data = temporary.data
    obj.data.name = obj.name + 'Mesh'
    bpy.data.objects.remove(temporary, do_unlink=True)
    if old.users == 0:
        bpy.data.meshes.remove(old)
    geo.project_uv(obj)
    obj['finish_refinement'] = 'Original formed surface, revision18 candidate; engineering anchors unchanged'


def rounded_loop(width, height, radius, samples=5):
    points = []
    for cx, cy, start in ((width/2-radius, height/2-radius, 0),
                          (-width/2+radius, height/2-radius, 90),
                          (-width/2+radius, -height/2+radius, 180),
                          (width/2-radius, -height/2+radius, 270)):
        for step in range(samples):
            angle = math.radians(start + 90*step/(samples-1))
            points.append((cx+radius*math.cos(angle), cy+radius*math.sin(angle)))
    return points


def loft_faces(count, layers):
    faces = [(j*count+i, j*count+(i+1)%count, (j+1)*count+(i+1)%count, (j+1)*count+i)
             for j in range(layers-1) for i in range(count)]
    faces.extend([tuple(reversed(range(count))), tuple((layers-1)*count+i for i in range(count))])
    return faces


def mirrors():
    """Taper the forward cap and shoulder; preserve the rear optic and stalk seat."""
    for symbol in ('Left', 'Right'):
        name = 'LOD0_Mirror_' + symbol + 'Housing'
        obj = bpy.data.objects[name]
        center = bpy.data.objects['Mirror_' + symbol].matrix_world.translation.copy()
        vertices = []
        # Rear ring encloses the existing127 by74mm optic. The forebody
        # retreats progressively into an aerodynamic cap within the old box.
        rings = [(-.0475, .146, .085, .005, 0.),
                 (-.027, .146, .085, .016, 0.),
                 (.015, .126, .071, .022, -.003),
                 (.040, .082, .041, .016, -.006),
                 (.0475, .036, .024, .010, -.006)]
        for y, width, height, radius, zshift in rings:
            vertices.extend(center + Vector((x, y, z+zshift)) for x, z in rounded_loop(width, height, radius))
        replace_world_mesh(obj, vertices, loft_faces(20, len(rings)))
        obj['manufacturing_form'] = 'Painted injection-molded aerodynamic cap over retained separate mirror optic; original envelope'


def cushion(obj, center, dimensions, front_axis='z', rotation=None):
    """A molded foam pad with broad radiused shoulders and a shallow face dish."""
    width, height, depth = dimensions
    transform = rotation.to_matrix() if rotation else None
    vertices = []
    rings = [(-.5, .88), (-.32, 1.), (.27, 1.), (.48, .92)]
    for offset, scale in rings:
        for x, y in rounded_loop(width*scale, height*scale, min(width,height)*.13):
            point = Vector((x, y, depth*offset)) if front_axis == 'z' else Vector((x, depth*offset, y))
            vertices.append(Vector(center)+(transform @ point if transform else point))
    faces = loft_faces(20, len(rings))[:-2]
    back = len(vertices)
    front = back+1
    for offset in (-.5, .40):
        point = Vector((0,0,depth*offset)) if front_axis == 'z' else Vector((0,depth*offset,0))
        vertices.append(Vector(center)+(transform @ point if transform else point))
    faces.extend((back, (i+1)%20, i) for i in range(20))
    faces.extend((front, 60+i, 60+(i+1)%20) for i in range(20))
    replace_world_mesh(obj, vertices, faces)
    obj['manufacturing_form'] = 'Contoured upholstered foam with formed shoulder, inset face and physical sewn panel boundary'


def cabin():
    for row, cy in (('Front', -.18), ('Rear', -1.10)):
        rear = row == 'Rear'
        width = .475 if rear else .49
        for side, cx in (('L', -.43), ('R', .43)):
            name = row+side
            cushion(bpy.data.objects['LOD0_'+name+'CushionInsert'], (cx,cy+.018,.476), (width-.137,.436,.054))
            cushion(bpy.data.objects['LOD0_'+name+'BackInsert'], (cx,cy-.151,.794),
                    (width-.145,.545,.064), 'y', Euler((math.radians(9 if rear else 18),0,0)))
            bpy.context.view_layer.update()
            for label in ('CushionInsert', 'BackInsert'):
                pad = bpy.data.objects['LOD0_'+name+label]
                pad.data.calc_loop_triangles()
                tree = BVHTree.FromPolygons([pad.matrix_world@v.co for v in pad.data.vertices],
                    [tuple(t.vertices) for t in pad.data.loop_triangles], all_triangles=True)
                patterns = []
                if label == 'CushionInsert':
                    for j in range(5):
                        patterns.append(('LOD0_'+name+'CushionSeam'+str(j),
                            [Vector((cx-.14+.28*k/6,cy-.12+j*.065,1.0)) for k in range(7)], Vector((0,0,-1)), .0006))
                else:
                    rotation=Euler((math.radians(9 if rear else 18),0,0)).to_matrix()
                    for side in (-1,1):
                        patterns.append(('LOD0_'+name+'BackPiping'+str(side),
                            [Vector((cx,cy-.151,.794))+rotation@Vector((side*(width-.145)*.40,.15,-.205+.410*k/8)) for k in range(9)],
                            rotation@Vector((0,-1,0)), .0008))
                for seam_name, rays, direction, radius in patterns:
                    old=bpy.data.objects[seam_name]
                    if label=='CushionInsert':
                        from .upholstery_seams import section
                        vertices,proof=section(pad,rays[0],rays[-1],radius)
                        replace_world_mesh(old,vertices,loft_faces(4,len(vertices)//4))
                        old['contact_policy']='Ray-fitted sewn piping against actual pad facets; thread is seated15percent of its radius'
                        old['complete_facet_route']=json.dumps(proof,sort_keys=True)
                        continue
                    points=[]
                    for ray in rays:
                        hit,normal,_,_=tree.ray_cast(ray,direction,1.)
                        if hit is None:raise ValueError('Refined seam has no actual pad support: '+seam_name)
                        points.append(hit+normal*(radius*.85))
                    new=geo.tube(seam_name+'_pilot',points,radius,old.data.materials[0],old.users_collection[0],sides=4)
                    replace_world_mesh(old,[v.co for v in new.data.vertices],[tuple(f.vertices) for f in new.data.polygons])
                    bpy.data.objects.remove(new,do_unlink=True)
                    old['contact_policy']='Ray-fitted sewn piping against the actual contoured pad; thread is seated15percent of its radius'
    cushion(bpy.data.objects['LOD0_ConsoleArmrest'], (0,-.468,.589), (.267,.336,.060))
    for suffix in ('FL','FR','RL','RR'):
        side = -1 if suffix.endswith('L') else 1
        y = -.04 if suffix.startswith('F') else -.89
        cushion(bpy.data.objects['LOD0_Armrest_'+suffix], (side*.771,y,.675), (.088,.366,.062))


def grille():
    """Shape each cooling blade as a tapered section with a recessed rear edge."""
    for i in range(20):
        obj = bpy.data.objects['LOD0_MainGrilleUpright_'+str(i)]
        x = -.516+i*.0543
        y = 2.332 - .020*(abs(x)/.55)**2
        vertices = [(x+dx, y+dy, z) for z in (.366,.594)
                    for dx,dy in ((-.0025,-.028),(.0025,-.028),(.003,.010),(0,.024),(-.003,.010))]
        replace_world_mesh(obj,vertices,[(4,3,2,1,0),(5,6,7,8,9)]+[(i,(i+1)%5,(i+1)%5+5,i+5) for i in range(5)],smooth=False)
        geo.bevel(obj,.0006,1)


def window_path(points, radius=.022, crown=.003):
    """Circular bends with optional shallow upper-glazing crown."""
    points=[Vector(p) for p in points]
    path=[]
    for index,corner in enumerate(points):
        previous=points[(index-1)%len(points)]
        following=points[(index+1)%len(points)]
        before=(previous-corner).normalized()
        after=(following-corner).normalized()
        theta=math.acos(max(-1.,min(1.,before.dot(after))))
        tangent_distance=radius/math.tan(theta/2)
        if tangent_distance>=min((previous-corner).length,(following-corner).length)*.45:
            raise ValueError('Window circular fillet exceeds its supporting straight edges')
        center=corner+(before+after).normalized()*(radius/math.sin(theta/2))
        a=corner+before*tangent_distance-center
        b=corner+after*tangent_distance-center
        angle=math.atan2(a.x*b.y-a.y*b.x,a.dot(b))
        for j in range(5):
            rotation=angle*j/4
            path.append(center+Vector((a.x*math.cos(rotation)-a.y*math.sin(rotation),
                                       a.x*math.sin(rotation)+a.y*math.cos(rotation))))
        next_before=(corner-following).normalized()
        next_after=(points[(index+2)%len(points)]-following).normalized()
        next_angle=math.acos(max(-1.,min(1.,next_before.dot(next_after))))
        end=following+next_before*(radius/math.tan(next_angle/2))
        start=path[-1]
        if crown and corner.y>1.2 and following.y>1.2:
            for j in range(1,6):
                t=j/6
                p=start.lerp(end,t)
                p.y+=crown*math.sin(math.pi*t)**2
                path.append(p)
    return path


def windows_and_pillars():
    for side,symbol in ((-1,'L'),(1,'R')):
        for axle, outline in [('F',[(.597,1.028),(-.534,1.028),(-.532,1.397),(.094,1.365)]),
                              ('R',[(-.655,1.028),(-1.667,1.028),(-1.263,1.330),(-.655,1.395)])]:
            suffix=axle+symbol
            if axle=='R':outline=[(y,z-.009 if z>1.2 else z) for y,z in outline]
            yz=window_path(outline)
            path=[Vector((side*(.885-(z-1)*.48),y,z)) for y,z in yz]
            normal=Vector((side,0,.48)).normalized()
            vertices=path+[p-normal*.0045 for p in path]
            count=len(path)
            glass=bpy.data.objects['LOD0_DoorGlass_'+suffix]
            replace_world_mesh(glass,vertices,[tuple(range(count)),tuple(reversed(range(count,2*count)))]+
                [(i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count)],smooth=False)
            seal=bpy.data.objects['LOD0_DoorGlassSeal_'+suffix]
            temporary=geo.tube('RefinedGlassSeal',path,.013,seal.data.materials[0],seal.users_collection[0],sides=8,closed=True)
            replace_world_mesh(seal,[v.co for v in temporary.data.vertices],[tuple(p.vertices) for p in temporary.data.polygons])
            bpy.data.objects.remove(temporary,do_unlink=True)
            center=sum(path,Vector())/count
            frame_vertices=[]
            # Rolled exterior metal section sits on the compressible weatherstrip.
            # It replaces the former painted tube hidden entirely inside rubber.
            section=[(-.009,.011),(-.012,.013),(-.009,.016),(.009,.016),(.012,.013),(.009,.011)]
            for i,p in enumerate(path):
                tangent=(path[(i+1)%count]-path[(i-1)%count]).normalized()
                outward=tangent.cross(normal).normalized()
                if outward.dot(p-center)<0:outward=-outward
                frame_vertices.extend(p+outward*u+normal*v for u,v in section)
            faces=[(i*6+j,i*6+(j+1)%6,((i+1)%count)*6+(j+1)%6,((i+1)%count)*6+j)
                   for i in range(count) for j in range(6)]
            frame=bpy.data.objects['LOD0_DoorFrame_'+suffix]
            replace_world_mesh(frame,frame_vertices,faces)
            frame['manufacturing_form']='Closed rolled metal cap seated over the compressible glass weatherstrip; rounded corners and original shallow top crown'
        # Keep the previously validated full-thickness A ribbon. A return wall
        # closes toward the refined sash without deforming the two skins with
        # unrelated position-dependent offsets.


def coherent_a_pillars():
    """Upgrade preserved pilot sources to the current original inner section."""
    from . import model
    from .floor_panels import freeze
    from .pillar_joints import normal_reference, preserve_surface_normals
    for side,symbol in ((-1,'L'),(1,'R')):
        obj=bpy.data.objects['LOD0_PillarA_'+symbol]
        if obj.get('inner_return_sections'):
            continue
        freeze(obj)
        reference=normal_reference(obj)
        fresh=model.formed_a_pillar(bpy.data.objects['LOD0_Roof'],side,symbol,
                                  obj.users_collection[0],obj.parent,obj.data.materials[0])
        freeze(fresh)
        cutter=geo.box('RetainedAUpstandPlane',(0,0,-.475),(4,6,3.05),None,obj.users_collection[0],radius=0)
        geo.boolean(fresh,cutter)
        bpy.data.objects.remove(cutter,do_unlink=True)
        geo.repair_triangulation(fresh)
        # A preserved pilot already owns the matching structural-body cap.
        # Native complement clipping can move a redundant cap subdivision by
        # a few micrometers; retain that existing complete vertex footprint.
        old_cap=[obj.matrix_world@v.co for v in obj.data.vertices
                 if abs((obj.matrix_world@v.co).z-1.05)<1e-7]
        points=[fresh.matrix_world@v.co for v in fresh.data.vertices]
        matched=set();maximum=0.
        for index,point in enumerate(points):
            if abs(point.z-1.05)>=1e-7:
                continue
            nearest=min(range(len(old_cap)),key=lambda j:(point-old_cap[j]).length)
            distance=(point-old_cap[nearest]).length
            if distance>1e-5 or nearest in matched:
                raise ValueError('A lower cap no longer matches the preserved body footprint')
            matched.add(nearest);maximum=max(maximum,distance)
            points[index]=old_cap[nearest]
        if len(matched)!=len(old_cap):
            raise ValueError('A lower cap footprint has unmatched vertices')
        replace_world_mesh(obj,points,
                           [tuple(p.vertices) for p in fresh.data.polygons])
        obj['inner_return_sections']=fresh['inner_return_sections']
        obj['retained_lower_cap']=json.dumps({'matched_vertices':len(matched),
            'maximum_native_subdivision_correction_m':maximum,'plane_z_m':1.05},sort_keys=True)
        bpy.data.objects.remove(fresh,do_unlink=True)
        preserve_surface_normals(obj,[reference])


def roof_closing_faces():
    """Extend the existing closed roof rail towards the separate moving sash."""
    from .surface_normals import mark_fold_edges
    for side,symbol in ((-1,'L'),(1,'R')):
        obj=bpy.data.objects['LOD0_RoofSideRail_'+symbol]
        vertices=[obj.matrix_world@v.co for v in obj.data.vertices]
        if len(vertices)!=250:raise ValueError('Roof rail topology changed')
        frames=[]
        for axle in ('F','R'):
            frame=bpy.data.objects['LOD0_DoorFrame_'+axle+symbol]
            frames.append(([frame.matrix_world@v.co for v in frame.data.vertices],
                           [tuple(e.vertices) for e in frame.data.edges]))
        for section in range(25):
            first=section*10
            y=vertices[first].y
            intersections=[]
            for points,edges in frames:
                for a,b in edges:
                    p,q=points[a],points[b]
                    if abs(p.y-y)<1e-7:intersections.append(p)
                    if (p.y-y)*(q.y-y)<0:
                        intersections.append(p.lerp(q,(y-p.y)/(q.y-p.y)))
            upper=[p for p in intersections if p.z>1.25]
            if not upper:
                # The fixed B-pillar occupies the short inter-door station.
                continue
            top=max(upper,key=lambda p:p.z)
            bottom=top+Vector((0,0,.007 if y<-.60 else .004))
            # Replace the thin outer flange with a folded closing face. Its
            # original roof weld and inner reinforcement remain unchanged.
            vertices[first+1]=Vector((side*min(abs(vertices[first].x),abs(bottom.x)),y,bottom.z))
            vertices[first+2]=Vector((vertices[first+1].x-side*.002,y,bottom.z+.0015))
            vertices[first+3]=Vector((side*.668,y,max(bottom.z+.0015,vertices[first+3].z)))
            vertices[first+4]=Vector((side*.662,y,vertices[first+3].z))
        replace_world_mesh(obj,vertices,[tuple(p.vertices) for p in obj.data.polygons])
        mark_fold_edges(obj)
        obj['manufacturing_form']='Continuous fixed roof closing face folded towards the separately moving door sash; candidate4mm vertical seam'


def roof_inner_returns():
    """Integral inboard lips close the gasket/header sightline below the shelf."""
    from .floor_panels import freeze
    from .pillar_joints import normal_reference, preserve_surface_normals
    from .surface_normals import restore_owned
    for side,symbol in ((-1,'L'),(1,'R')):
        obj=bpy.data.objects['LOD0_RoofSideRail_'+symbol]
        original=[obj.matrix_world@v.co for v in obj.data.vertices]
        stations=[original[i*10].y for i in range(25)]
        def height(y):
            index=max(0,min(23,next((j-1 for j,q in enumerate(stations) if q>=y),23)))
            fraction=(y-stations[index])/(stations[index+1]-stations[index])
            a,b=original[index*10+2].z,original[(index+1)*10+2].z
            return a+(b-a)*fraction
        freeze(obj)
        normals=normal_reference(obj)
        lip_references=[]
        for label,lo,hi in (('Rear',-1.230,-.650),('Front',-.540,.104)):
            ys=sorted(set([lo,hi]+[y for y in stations if lo<y<hi]))
            vertices=[]
            for y in ys:
                vertices.extend([(side*.678,y,height(y)+.0003),
                                 (side*.678,y,height(y)-.022),
                                 (side*.675,y,height(y)-.022),
                                 (side*.675,y,height(y)+.0003)])
            lip=geo.mesh('IntegralRoof'+label+'Return',vertices,loft_faces(4,len(ys)),None,obj.users_collection[0])
            lip_references.append(normal_reference(lip))
            geo.boolean(obj,lip,'UNION')
            bpy.data.objects.remove(lip,do_unlink=True)
        preserve_surface_normals(obj,[normals])
        obj['formed_lip_normal_ownership']=json.dumps(restore_owned(obj,lip_references),sort_keys=True)
        geo.project_uv(obj)
        obj['inner_return_section_m']='|X|.675..678,22mm below interpolated shelf vertex2; separate front/rear spans clear fixed B-pillar; integral union with300um regular attachment overlap and finite overlap at B transitions'


def door_returns():
    """Rebuild rear return cuts as a connected taper, preserving the outer hem."""
    from . import model
    original_profile=model.CURVED_PROFILES
    original_reference=model.BODY_UPPER_SURFACE
    temporary=bpy.data.collections.new('RefinementTemporary')
    bpy.context.scene.collection.children.link(temporary)
    try:
        model.CURVED_PROFILES=True
        material=bpy.data.objects['LOD0_Door_RL'].data.materials[0]
        body=model.lower_body(temporary,None,{'paint':material})
        outline=model.inset_polygon(model.split_door_outlines()['R'],.0035)
        for side,symbol in ((-1,'L'),(1,'R')):
            obj=bpy.data.objects['LOD0_Door_R'+symbol]
            panel=body.copy();panel.data=body.data.copy();temporary.objects.link(panel)
            limits=sorted((side*.780,side*1.080))
            cutter=geo.prism_x('DoorReturnOutline',outline,*limits,None,temporary)
            geo.boolean(panel,cutter,'INTERSECT');bpy.data.objects.remove(cutter,do_unlink=True)
            cutter=geo.tube('DoorReturnArch',[(side*.76,-1.46,.3433),(side*.931,-1.46,.3433)],
                            [.525,.495],None,temporary,sides=48)
            geo.boolean(panel,cutter);bpy.data.objects.remove(cutter,do_unlink=True)
            rings=[]
            for x in (.760,.810,.850,.880,.905,.931):
                t=max(0,min(1,(x-.880)/.051))
                retreat=.180*(t*t*(3-2*t))
                low_y=-1.426+(.850-.795)*1.2513-retreat
                high_y=-1.670-retreat
                rings.extend([(side*x,-1.98,.795),(side*x,low_y,.795),
                              (side*x,high_y,1.045),(side*x,-1.98,1.045)])
            cutter=geo.mesh('DoorReturnTaper',rings,loft_faces(4,6),None,temporary)
            geo.boolean(panel,cutter);bpy.data.objects.remove(cutter,do_unlink=True)
            replace_world_mesh(obj,[v.co for v in panel.data.vertices],
                               [tuple(p.vertices) for p in panel.data.polygons])
            geo.bevel(obj,.0012,2)
            obj['inner_return_finish']='Original rear outer hem retained; connected smoothstep depth taper replaces the abrupt aft inner return step'
            bpy.data.objects.remove(panel,do_unlink=True)
    finally:
        for obj in list(temporary.objects):bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.collections.remove(temporary)
        model.CURVED_PROFILES=original_profile
        model.BODY_UPPER_SURFACE=original_reference


def connected_header_returns():
    """Form a coherent assembly, then split its complete finite butt section."""
    from . import header_return
    from .floor_panels import freeze
    from .pillar_joints import normal_reference, preserve_surface_normals
    from .surface_normals import restore_owned
    for side, data in header_return.PARTS.items():
        pillar=bpy.data.objects['LOD0_PillarA_'+side]
        rail=bpy.data.objects['LOD0_RoofSideRail_'+side]
        for obj in (pillar,rail):freeze(obj)
        if pillar.matrix_world != rail.matrix_world:
            raise ValueError('A/header carriers must share their original fixed source frame')
        collection=pillar.users_collection[0]
        coating=pillar.data.materials[0]
        originals=[normal_reference(obj) for obj in (pillar,rail)]
        whole=pillar.copy();whole.data=pillar.data.copy();collection.objects.link(whole)
        whole.name='IntegralAHeaderAssembly_'+side
        wall = geo.mesh('IntegralAHeaderReturn_' + side, data['vertices'], data['triangles'],
                        coating, collection, smooth=True)
        edit = bmesh.new()
        edit.from_mesh(wall.data)
        for edge in edit.edges:
            if len(edge.link_faces) == 2 and edge.calc_face_angle() > math.radians(35):
                edge.smooth = False
        edit.to_mesh(wall.data)
        edit.free()
        wall.data.update()
        wall_reference=normal_reference(wall)
        geo.boolean(whole, wall, 'UNION')
        bpy.data.objects.remove(wall, do_unlink=True)
        geo.boolean(whole, rail, 'UNION')
        repair_stamp_slivers(whole)
        freeze(whole)
        rear=whole.copy();rear.data=whole.data.copy();collection.objects.link(rear)
        rear.name='IntegralAHeaderRearHalf_'+side
        split=geo.prism_x('AHeaderCompleteSection',
            [(header_return.PLANE_Y,-1),(4,-1),(4,3),(header_return.PLANE_Y,3)],
            -2,2,None,collection)
        geo.boolean(whole,split,'INTERSECT')
        geo.boolean(rear,split,'DIFFERENCE')
        bpy.data.objects.remove(split,do_unlink=True)
        for obj,result in ((pillar,whole),(rail,rear)):
            repair_stamp_slivers(result)
            obj.data=result.data
            obj.data.name=obj.name+'ConnectedHeaderMesh'
            # Both structural carriers and the new return use the same paint.
            for polygon in obj.data.polygons:
                actual=obj.data.materials[polygon.material_index]
                if actual is not None and actual != coating:
                    raise ValueError('Unexpected A/header material assignment')
            obj.data.materials.clear();obj.data.materials.append(coating)
            for polygon in obj.data.polygons:polygon.material_index=0
            preserve_surface_normals(obj,originals)
            obj['formed_header_normal_ownership']=json.dumps(restore_owned(obj,[wall_reference]),sort_keys=True)
            geo.project_uv(obj)
            obj['a_header_finite_butt_y_m']=header_return.PLANE_Y
            obj['a_header_construction']='Coherent18mm A inner sheet plus integral3mm formed return and fixed roof rail, unioned then split on complete finite Y.1051m butt. Original exterior, roof-skin and lower-body joints retained.'
            bpy.data.objects.remove(result,do_unlink=True)


def door_cards():
    """Form padded trim shoulders inside each original door-card perimeter."""
    from collections import Counter
    for suffix in ('FL','FR','RL','RR'):
        obj=bpy.data.objects['LOD0_DoorCard_'+suffix]
        side=-1 if suffix.endswith('L') else 1
        points=[obj.matrix_world@v.co for v in obj.data.vertices]
        faces=[tuple(p.vertices) for p in obj.data.polygons
               if all(abs(abs(points[i].x)-.790)<1e-6 for i in p.vertices)]
        edges=Counter(tuple(sorted((face[i],face[(i+1)%len(face)])))
                      for face in faces for i in range(len(face)))
        boundary=[edge for edge,count in edges.items() if count==1]
        neighbors={}
        for a,b in boundary:
            neighbors.setdefault(a,[]).append(b);neighbors.setdefault(b,[]).append(a)
        if not neighbors or any(len(v)!=2 for v in neighbors.values()):raise ValueError('Door card boundary is not a loop: '+suffix)
        order=[min(neighbors)];previous=None
        while True:
            current=order[-1]
            following=next(n for n in sorted(neighbors[current]) if n!=previous)
            if following==order[0]:break
            order.append(following);previous=current
            if len(order)>len(neighbors):raise ValueError('Door-card boundary loop did not close')
        path=[points[i] for i in order]
        center=sum(path,Vector())/len(path)
        vertices=[]
        for x,scale in ((.821,1.),(.804,1.),(.793,.984),(.790,.970)):
            for p in path:
                q=center+(p-center)*scale;q.x=side*x;vertices.append(q)
        replace_world_mesh(obj,vertices,loft_faces(len(path),4))
        for polygon in obj.data.polygons[-2:]:polygon.use_smooth=False
        obj['manufacturing_form']='Molded padded door card with a broad retained mounting perimeter and tapered upholstered shoulder'


def rear_inner_hems():
    """Use supported14mm bends instead of folded six-millimeter hem sections."""
    outline=[(-.668,.981),(-.655,.316)]+[
        (-1.46+.514*math.cos(math.radians(a)),.3433+.514*math.sin(math.radians(a)))
        for a in (-3,15,35,55,75)]+[(-1.606,.981)]
    outline=window_path(outline,radius=.014,crown=0)
    for side,symbol in ((-1,'L'),(1,'R')):
        obj=bpy.data.objects['LOD0_DoorInnerHem_R'+symbol]
        fresh=geo.tube('RefinedRearInnerHem',[(side*.812,y,z) for y,z in outline],.006,
                       obj.data.materials[0],obj.users_collection[0],sides=6,closed=True)
        replace_world_mesh(obj,[v.co for v in fresh.data.vertices],
                           [tuple(p.vertices) for p in fresh.data.polygons])
        bpy.data.objects.remove(fresh,do_unlink=True)
        obj['manufacturing_form']='Continuous6mm rolled return around the514mm arch,14mm corner bends; redundant subdiameter backtrack removed'


def headliner_mounts():
    """Upgrade the preserved-source pad with the current exact clipping rule."""
    from collections import Counter
    from . import surface_clip
    obj=bpy.data.objects['LOD0_HandleMount_-1_1']
    if obj.get('support_clipping'):return
    points=[obj.matrix_world@v.co for v in obj.data.vertices]
    rect=(min(p.x for p in points),max(p.x for p in points),
          min(p.y for p in points),max(p.y for p in points))
    bottom=min(p.z for p in points)
    headliner=bpy.data.objects['LOD0_Headliner']
    evaluated=headliner.evaluated_get(bpy.context.evaluated_depsgraph_get())
    support=evaluated.to_mesh();support.calc_loop_triangles()
    underside=[]
    try:
        for triangle in support.loop_triangles:
            vertices=[evaluated.matrix_world@support.vertices[i].co for i in triangle.vertices]
            if (vertices[1]-vertices[0]).cross(vertices[2]-vertices[0]).z < -1e-10:
                underside.append(list(reversed(vertices)))
    finally:evaluated.to_mesh_clear()
    vertices=[];lookup={};faces=[]
    for triangle in surface_clip.patch(underside,rect):
        face=[]
        for point in triangle:
            key=tuple(point)
            if key not in lookup:lookup[key]=len(vertices);vertices.append(key)
            face.append(lookup[key])
        faces.append(tuple(face))
    counts=Counter(tuple(sorted((face[i],face[(i+1)%3]))) for face in faces for i in range(3))
    if max(counts.values())>2:raise ValueError('Mount top contains a nonmanifold shared edge')
    boundary=[(face[i],face[(i+1)%3]) for face in faces for i in range(3)
              if counts[tuple(sorted((face[i],face[(i+1)%3]))) ]==1]
    count=len(vertices)
    vertices += [(v[0],v[1],bottom) for v in vertices[:count]]
    faces += [tuple(i+count for i in reversed(face)) for face in list(faces)]
    faces += [(a,b,b+count,a+count) for a,b in boundary]
    replace_world_mesh(obj,vertices,faces,smooth=False)
    obj['support_clipping']='Exact shared-edge clipping, one float32 encoding; no rounded welding keys'


def repair_stamp_slivers(obj):
    """Flip a sliver diagonal; preserve every vertex and the closed surface."""
    try:
        geo.repair_triangulation(obj)
        counts=geo.evaluated_counts(obj)
        if any(counts[key] for key in ('nonmanifold_edges','duplicate_faces',
                'triangulated_nonmanifold_edges','triangulated_duplicate_faces')):
            raise ValueError('Invalid stamp or header input: '+obj.name+' '+str(counts))
        return
    except ValueError:
        counts=geo.evaluated_counts(obj)
        if counts['nonmanifold_edges'] or counts['duplicate_faces']:raise
    edit=bmesh.new();edit.from_mesh(obj.data)
    repairs=[]
    def area(face):
        a,b,c=([float(q) for q in v.co] for v in face.verts)
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        return .5*math.sqrt(sum(q*q for q in (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])))
    try:
        for _ in range(12):
            bad=[f for f in edit.faces if len(f.verts)==3 and area(f)<=1e-12]
            if not bad:break
            face=bad[0];changed=False
            for edge in sorted(face.edges,key=lambda e:e.calc_length(),reverse=True):
                if len(edge.link_faces)!=2 or any(len(f.verts)!=3 for f in edge.link_faces):continue
                other=next(f for f in edge.link_faces if f!=face)
                if area(other)<=1e-12 or other.material_index!=face.material_index:continue
                a,b=[v.co.copy() for v in edge.verts]
                c=next(v.co for v in face.verts if v not in edge.verts)
                direction=b-a;fraction=(c-a).dot(direction)/direction.length_squared
                deviation=(c-(a+direction*fraction)).length
                if not 0<fraction<1 or deviation>1e-6:continue
                old_vertices=sorted(tuple(v.co) for v in edit.verts)
                result=bmesh.ops.rotate_edges(edit,edges=[edge],use_ccw=False)
                if not result.get('edges'):continue
                if sorted(tuple(v.co) for v in edit.verts)!=old_vertices:
                    raise ValueError('Stamp diagonal repair moved a vertex')
                repairs.append({'sliver_altitude_m':deviation,'vertex_positions_unchanged':True})
                changed=True;break
            if not changed:raise ValueError('No bounded stamp sliver diagonal repair: '+obj.name)
        else:raise ValueError('Stamp sliver repair did not converge: '+obj.name)
        bmesh.ops.recalc_face_normals(edit,faces=list(edit.faces))
        edit.to_mesh(obj.data);obj.data.update()
    finally:edit.free()
    counts=geo.evaluated_counts(obj)
    if counts['nonmanifold_edges'] or counts['degenerate_triangles'] or counts['duplicate_faces']:
        raise ValueError('Stamp diagonal repair failed closed-mesh quality: '+obj.name)
    obj['stamp_sliver_diagonal_repairs']=json.dumps(repairs,sort_keys=True)


def pressed_door_returns():
    """Shallow formed recesses in the real return, clear of latch and hem seats."""
    from .floor_panels import freeze
    from .pillar_joints import normal_reference, preserve_surface_normals
    for suffix in ('FL','FR','RL','RR'):
        obj=bpy.data.objects['LOD0_Door_'+suffix]
        side=-1 if suffix.endswith('L') else 1
        freeze(obj)
        old_normals=normal_reference(obj)
        world=[obj.matrix_world@v.co for v in obj.data.vertices]
        obj.data.calc_loop_triangles()
        tree=BVHTree.FromPolygons(world,[tuple(t.vertices) for t in obj.data.loop_triangles],all_triangles=True)
        forms=[(.858,.520,.048,.440),(.858,.934,.048,.120)] if suffix.startswith('F') else [(.892,.927,.050,.130)]
        for cx,cz,width,height in forms:
            vertices=[]
            # Draft the outside tool beyond the finished perimeter. A parallel
            # entry face exactly sharing the planar return's border generated
            # a collinear T-junction in the exact Boolean result.
            rings=((-.024,1.05),(.0004,1.),(.002,.97),(.0055,.83),(.006,.78))
            for depth,scale in rings:
                for dx,dz in rounded_loop(width*scale,height*scale,min(.012,width*.23)*scale,samples=3):
                    x=side*(cx+dx);z=cz+dz
                    hit=tree.ray_cast(Vector((x,-3,z)),Vector((0,1,0)),6.)[0]
                    if hit is None:raise ValueError('Pressed door return has no supporting surface: '+suffix+' at '+str((x,z)))
                    vertices.append((x,hit.y+depth,z))
            cutter=geo.mesh('DoorReturnStamp',vertices,loft_faces(12,len(rings)),None,obj.users_collection[0],smooth=True)
            planar=cutter.modifiers.new('Planar stamped-surface tool','TRIANGULATE')
            bpy.context.view_layer.objects.active=cutter
            bpy.ops.object.modifier_apply(modifier=planar.name)
            geo.boolean(obj,cutter)
            bpy.data.objects.remove(cutter,do_unlink=True)
        repair_stamp_slivers(obj)
        preserve_surface_normals(obj,[old_normals])
        geo.project_uv(obj)
        obj['pressed_return_depth_m']=.006
        obj['pressed_return_scope']='Integral shallow formed return recess; latch, inner hem and exterior boundary are retained'


def door_latches():
    """Fit visible flanged latch housings to the actual stamped return surfaces."""
    from .floor_panels import freeze
    from .pillar_joints import normal_reference, preserve_surface_normals
    for suffix in ('FL','FR','RL','RR'):
        panel=bpy.data.objects['LOD0_Door_'+suffix]
        housing=bpy.data.objects['LOD0_DoorLatch_'+suffix]
        side=-1 if suffix.endswith('L') else 1
        freeze(panel)
        normals=normal_reference(panel)
        panel.data.calc_loop_triangles()
        tree=BVHTree.FromPolygons([panel.matrix_world@v.co for v in panel.data.vertices],
                                 [tuple(t.vertices) for t in panel.data.loop_triangles],all_triangles=True)
        height=.795 if suffix.startswith('F') else .935
        hit,out,_,_=tree.ray_cast(Vector((side*.844,-3,height)),Vector((0,1,0)),6.)
        if hit is None or out.y>=-.1:raise ValueError('Latch has no outward return seat: '+suffix)
        out.normalize()
        across=Vector((1,0,0));across=(across-out*across.dot(out)).normalized()
        up=out.cross(across).normalized()
        def rings_mesh(name,rings,material=None):
            vertices=[]
            for depth,width,height,radius in rings:
                vertices.extend(hit+out*depth+across*x+up*z for x,z in rounded_loop(width,height,radius,samples=3))
            return geo.mesh(name,vertices,loft_faces(12,len(rings)),material,panel.users_collection[0])
        pocket=rings_mesh('LatchHousingSocket',[(.028,.027,.051,.002),(-.018,.027,.051,.002)])
        geo.boolean(panel,pocket);bpy.data.objects.remove(pocket,do_unlink=True)
        formed=rings_mesh('FittedLatchHousing',[(.0015,.034,.060,.003),(-.0002,.034,.060,.003),
                                              (-.0002,.026,.050,.002),(-.017,.026,.050,.002)],housing.data.materials[0])
        replace_world_mesh(housing,[v.co for v in formed.data.vertices],[tuple(p.vertices) for p in formed.data.polygons],smooth=False)
        bpy.data.objects.remove(formed,do_unlink=True)
        mouth=rings_mesh('LatchReceiverMouth',[(.006,.009,.018,.001),(-.006,.009,.018,.001)])
        geo.boolean(housing,mouth);bpy.data.objects.remove(mouth,do_unlink=True)
        for original_z,offset in ((.775,-.020),(.814,.020)):
            bolt=bpy.data.objects['LOD0_LatchFastener_'+suffix+str(original_z)]
            center=hit+across*.008+up*offset
            socket=geo.tube('LatchFastenerRecess',[center+out*.0005,center+out*.006],.00305,
                            None,panel.users_collection[0],sides=6)
            geo.boolean(housing,socket);bpy.data.objects.remove(socket,do_unlink=True)
            shaped=geo.tube('LatchFaceFastener',[center+out*.0005,center+out*.0015],.003,
                            bolt.data.materials[0],panel.users_collection[0],sides=6)
            replace_world_mesh(bolt,[v.co for v in shaped.data.vertices],[tuple(p.vertices) for p in shaped.data.polygons],smooth=False)
            bpy.data.objects.remove(shaped,do_unlink=True)
            bolt['fitted_fastener_seat']=json.dumps({'bottom_center_m':list(center+out*.0005),
                'outward_normal':list(out),'depth_m':.001,'head_radius_m':.003,
                'socket_radius_m':.00305,'contact':'Finite bottom cap; flush with faceplate'},sort_keys=True)
        preserve_surface_normals(panel,[normals]);geo.project_uv(panel);geo.project_uv(housing)
        housing['fitted_latch_seat']=json.dumps({'center_m':list(hit),'outward_normal':list(out),
            'flange_size_m':[.034,.060],'socket_size_m':[.027,.051],'body_size_m':[.026,.050,.017],
            'flange_seat_overlap_m':.0002,'simulation':'Modeled housing and receiver only; no internal latch simulation'},sort_keys=True)


HARDWARE_CHAMFERS = ('LOD0_AuxFillerGrip', 'LOD0_BatteryClamp', 'LOD0_ClimateSwitch_-0.062', 'LOD0_ClimateSwitch_0', 'LOD0_ClimateSwitch_0.062', 'LOD0_CoilPack_-10', 'LOD0_CoilPack_-11', 'LOD0_CoilPack_-12', 'LOD0_CoilPack_-13', 'LOD0_CoilPack_10', 'LOD0_CoilPack_11', 'LOD0_CoilPack_12', 'LOD0_CoilPack_13', 'LOD0_DoorLatch_FL', 'LOD0_DoorLatch_FR', 'LOD0_DoorLatch_RL', 'LOD0_DoorLatch_RR', 'LOD0_FrontLRailBase', 'LOD0_FrontLSeatSwitch', 'LOD0_FrontRRailBase', 'LOD0_FrontRSeatSwitch', 'LOD0_GloveboxHandle', 'LOD0_HandleTouch_FL', 'LOD0_HandleTouch_FR', 'LOD0_HandleTouch_RL', 'LOD0_HandleTouch_RR', 'LOD0_HoodHingeFixed_-1_-1', 'LOD0_HoodHingeFixed_-1_1', 'LOD0_HoodHingeFixed_1_-1', 'LOD0_HoodHingeFixed_1_1', 'LOD0_InstrumentShadeWing_-1', 'LOD0_InstrumentShadeWing_1', 'LOD0_Pedal_AcceleratorGrip0', 'LOD0_Pedal_AcceleratorGrip1', 'LOD0_Pedal_AcceleratorGrip2', 'LOD0_Pedal_AcceleratorGrip3', 'LOD0_Pedal_AcceleratorGrip4', 'LOD0_Pedal_BrakeGrip0', 'LOD0_Pedal_BrakeGrip1', 'LOD0_Pedal_BrakeGrip2', 'LOD0_Pedal_BrakeGrip3', 'LOD0_Pedal_BrakeGrip4', 'LOD0_RearLRailBase', 'LOD0_RearRRailBase', 'LOD0_SteeringButton_-10', 'LOD0_SteeringButton_-11', 'LOD0_SteeringButton_-12', 'LOD0_SteeringButton_10', 'LOD0_SteeringButton_11', 'LOD0_SteeringButton_12', 'LOD0_TrunkHingeFixed_-1_-1', 'LOD0_TrunkHingeFixed_-1_1', 'LOD0_TrunkHingeFixed_1_-1', 'LOD0_TrunkHingeFixed_1_1', 'LOD0_WindowSwitchPod_FL', 'LOD0_WindowSwitchPod_FR', 'LOD0_WindowSwitchPod_RL', 'LOD0_WindowSwitchPod_RR', 'LOD0_WindowSwitch_FL0', 'LOD0_WindowSwitch_FL1', 'LOD0_WindowSwitch_FR0', 'LOD0_WindowSwitch_FR1', 'LOD0_WindowSwitch_RL0', 'LOD0_WindowSwitch_RR0')


def hardware_chamfers():
    additional=('LOD0_Airbox_-1','LOD0_Airbox_1','LOD0_EnduranceRadio','LOD0_FuseBox',
                'LOD0_RearBattery','LOD0_IntakePlenum_-1','LOD0_IntakePlenum_1','LOD0_ExpansionTank',
                'LOD0_CentralResonator','LOD0_RearMuffler_-1','LOD0_RearMuffler_1','LOD0_RoofConsole')
    # These fourteen complete convex-envelope trials retain all original flat
    # mating faces and recover896 triangles for visible structural repairs.
    additional+=('LOD0_BrakeDuctInterior_L','LOD0_BrakeDuctInterior_R','LOD0_CrewLogBinder',
                 'LOD0_Glovebox','LOD0_InstrumentShade','LOD0_Pedal_AcceleratorArm',
                 'LOD0_Pedal_BrakeArm','LOD0_ValleyHeatShield','LOD0_WaterToAirChargeCooler_-1',
                 'LOD0_WaterToAirChargeCooler_1','LOD0_FrontBeltRelease_-1',
                 'LOD0_FrontBeltRelease_1','LOD0_RearBeltRelease_-1','LOD0_RearBeltRelease_1')
    additional+=('LOD0_CabinUndertray_-1','LOD0_CabinUndertray_1','LOD0_CentralRadiator',
                 'LOD0_MainGrilleRail_0','LOD0_MainGrilleRail_1','LOD0_MainGrilleRail_2',
                 'LOD0_MainGrilleRail_3','LOD0_SillTread_L','LOD0_SillTread_R',
                 'LOD0_TankStrap_-0.313','LOD0_TankStrap_0.313','LOD0_TunnelHeatShield',
                 'LOD0_Wiper_LClip','LOD0_Wiper_RClip','LOD0_Wiper_LSpringRail','LOD0_Wiper_RSpringRail')
    # Ten small optical/plate housings fund the full facet-following thread
    # routes. All sixty complete flat seats remain exact; no blade is changed.
    additional+=('LOD0_CenterBrakeEmitter','LOD0_ProjectorEmitter_L-1','LOD0_ProjectorEmitter_L1',
                 'LOD0_ProjectorEmitter_R-1','LOD0_ProjectorEmitter_R1',
                 'LOD0_ReadingLens_-1','LOD0_ReadingLens_1','LOD0_RearReflector_L',
                 'LOD0_RearReflector_R','LOD0_RegistrationPlate')
    for name in HARDWARE_CHAMFERS+additional:
        obj=bpy.data.objects[name]
        bevels=[m for m in obj.modifiers if m.type=='BEVEL']
        if len(bevels)!=1 or bevels[0].segments!=2:raise ValueError('Hardware profile changed: '+name)
        bevels[0].segments=1
        obj['manufacturing_form']='Straight machined or molded chamfer; full original envelope, material and assembly retained'


def boolean_surface_diagonals():
    """Repair only witnessed crossings in the final original panel surfaces."""
    import sys
    from pathlib import Path
    from . import boolean_surface
    # Share the independently controlled exact predicate with source QA. Its
    # library has no scene, report, filesystem or top-level diagnostic work.
    qa_path=str(Path(__file__).resolve().with_name('qa'))
    sys.path.insert(0,qa_path)
    try:
        from self_geometry import scan
        for name in ('LOD0_FrontBumper','LOD0_FrontFender_L','LOD0_FrontFender_R',
                     'LOD0_Door_FL','LOD0_Door_FR','LOD0_Door_RL','LOD0_Door_RR'):
            obj=bpy.data.objects[name]
            print('SEDAN_FINAL_BOOLEAN '+name+' '+json.dumps(geo.evaluated_counts(obj)),flush=True)
            # This is the existing final evaluated sliver cleanup, now ordered
            # before the exact self test instead of after the whole finish pass.
            geo.repair_triangulation(obj)
            proof=boolean_surface.repair(obj,scan,geo.evaluated_counts,allow_sliver_flip=True)
            obj['attributed_diagonal_repair']=json.dumps(
                {key:value for key,value in proof.items() if key!='proof'},sort_keys=True)
    finally:
        sys.path.remove(qa_path)


def apply(*, include_header_return=True):
    bpy.context.view_layer.update()
    mirrors()
    cabin()
    grille()
    coherent_a_pillars()
    windows_and_pillars()
    roof_closing_faces()
    roof_inner_returns()
    if include_header_return:
        connected_header_returns()
    door_returns()
    door_cards()
    rear_inner_hems()
    headliner_mounts()
    pressed_door_returns()
    hardware_chamfers()
    door_latches()
    boolean_surface_diagonals()
    bpy.context.view_layer.update()
