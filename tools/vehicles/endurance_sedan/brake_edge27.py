"""Unsaved current-scene rotor outline and caliper strip-field proposal.

The caller owns source loading, evidence and any eventual save/export. This
module performs no file IO. All twenty objects are staged before assignment.
"""
import math
import bpy

OUTER_STATIONS=52
INNER_STATIONS=32

def normal_targets(mesh):
    targets=[None]*len(mesh.loops)
    for face in mesh.polygons:
        points=[mesh.vertices[i].co for i in face.vertices]
        if max(p.x for p in points)-min(p.x for p in points)<=1e-7:
            assert abs(face.normal.x)>.99999
            n=(math.copysign(1.,face.normal.x),0.,0.)
            for i in face.loop_indices:targets[i]=n
        else:
            radii=[math.hypot(p.y,p.z) for p in points]
            assert max(radii)-min(radii)<=1e-7 and abs(face.normal.x)<1e-6
            for i in face.loop_indices:
                p=mesh.vertices[mesh.loops[i].vertex_index].co;r=math.hypot(p.y,p.z)
                sign=math.copysign(1.,face.normal.y*p.y+face.normal.z*p.z)
                targets[i]=(0.,sign*p.y/r,sign*p.z/r)
    assert all(n is not None for n in targets)
    return targets

def whole_field_bound(mesh,targets):
    """Full barycentric normal-field error from a target cone and vertex errors."""
    mesh.calc_loop_triangles();maximum=0.;witness=None
    actual=[tuple(n.vector) for n in mesh.corner_normals]
    for index,t in enumerate(mesh.loop_triangles):
        ns=[targets[i] for i in t.loops];encoded=[actual[i] for i in t.loops]
        c=[sum(n[k] for n in ns) for k in range(3)];length=math.hypot(*c)
        assert math.isfinite(length) and length>0
        c=[v/length for v in c]
        lower=min(sum(x*y for x,y in zip(c,n)) for n in ns)
        error=max(math.dist(n,a) for n,a in zip(ns,encoded))
        assert 0<lower and error<lower
        bound=math.degrees(math.asin(error/lower))
        if bound>maximum:maximum=bound;witness={'triangle':index,'target_vector_length_lower_bound':lower,'native_vector_error_upper_bound':error}
    assert maximum<=.025,(maximum,witness)
    return {'maximum_complete_triangle_encoding_degrees':maximum,'witness':witness,
            'method':'Target normal convex sums have length >= minimum projection on the triangle target cone axis. Actual sum differs by <= maximum corner-vector error. The whole normalized-field angle is <= asin(error / lower).'}

def rotor(stage,original,geo,encode):
    old=original.data
    if original.modifiers or len(old.vertices)!=128 or len(old.polygons)!=128:
        raise ValueError('Expected actual applied 32-station friction ring')
    if len(old.materials)!=1 or list(l.name for l in old.uv_layers)!=['SurfaceMeters']:
        raise ValueError('Unexpected friction material/UV contract')
    if abs(original.get('uv_meters_per_repeat',0)-.25)>1e-12:
        raise ValueError('Unexpected physical UV repeat')
    suffix=original.name.split('_')[-1][:2]
    radius=.1995 if suffix.startswith('F') else .178
    xs=[old.vertices[i*32].co.x for i in range(4)]
    assert xs[0]==xs[1] and xs[2]==xs[3] and xs[0]<xs[2]
    expected_radii=(.104,radius,radius,.104)
    for i,r in enumerate(expected_radii):
        for j in range(32):
            p=old.vertices[i*32+j].co;a=math.tau*j/32
            assert p.x==xs[i] and abs(p.y-r*math.sin(a))<=1e-7 and abs(p.z-r*math.cos(a))<=1e-7
    vertices=[];rings=[]
    for i,r in enumerate(expected_radii):
        ids=[];count=INNER_STATIONS if i in (0,3) else OUTER_STATIONS
        for j in range(count):
            ids.append(len(vertices))
            vertices.append(tuple(old.vertices[i*32+j].co) if i in (0,3)
                            else (xs[i],r*math.sin(math.tau*j/count),r*math.cos(math.tau*j/count)))
        rings.append(ids)
    faces=[]
    for a,b in zip(rings,rings[1:]+rings[:1]):
        ia=ib=0;na=len(a);nb=len(b)
        while ia<na or ib<nb:
            left=(ia+1)*nb;right=(ib+1)*na
            current_a=a[ia%na];current_b=b[ib%nb]
            if left==right:
                faces.append((current_a,current_b,b[(ib+1)%nb],a[(ia+1)%na]));ia+=1;ib+=1
            elif left<right:
                faces.append((current_a,current_b,a[(ia+1)%na]));ia+=1
            else:
                faces.append((current_a,current_b,b[(ib+1)%nb]));ib+=1
    mesh=bpy.data.meshes.new('Private_BrakeOuter52Mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
    mesh.materials.append(old.materials[0])
    for p in mesh.polygons:p.use_smooth=True
    stage.data=mesh;stage.modifiers.clear();geo.project_uv(stage,.25)
    targets=normal_targets(mesh);encoding=encode(mesh,targets)
    assert encoding['passed'];field=whole_field_bound(mesh,targets)
    # The two original complete inner rings, all four axial stations and
    # +/-Y/Z extrema remain literal native coordinates.
    for i in (0,3):
        assert [tuple(mesh.vertices[j].co) for j in rings[i]]==[tuple(old.vertices[i*32+j].co) for j in range(32)]
    assert min(v.co.x for v in mesh.vertices)==min(v.co.x for v in old.vertices)
    assert max(v.co.x for v in mesh.vertices)==max(v.co.x for v in old.vertices)
    for axis in (1,2):
        assert min(v.co[axis] for v in mesh.vertices)==min(v.co[axis] for v in old.vertices)
        assert max(v.co[axis] for v in mesh.vertices)==max(v.co[axis] for v in old.vertices)
    radial_error=max(abs(math.hypot(mesh.vertices[j].co.y,mesh.vertices[j].co.z)-radius) for i in (1,2) for j in rings[i])
    assert radial_error<1e-7
    uv=mesh.uv_layers['SurfaceMeters'];uv_error=0.
    for face in mesh.polygons:
        if abs(face.normal.x)>.99999:
            for loop in face.loop_indices:
                p=mesh.vertices[mesh.loops[loop].vertex_index].co
                uv_error=max(uv_error,abs(uv.data[loop].uv.x-p.y/.25),abs(uv.data[loop].uv.y-p.z/.25))
    assert uv_error<=1e-5
    return {'scope':'Only outer-radius angular tessellation; actual axial/inner-ring geometry and physical UV affine field preserved.',
            'old_inner_outer_stations':[32,32],'new_inner_outer_stations':[32,52],
            'nominal_outer_radius_m':radius,'axial_planes_m':[xs[0],xs[2]],
            'maximum_native_radial_error_m':radial_error,'inner_native_rings_exact':True,
            'axis_extrema_exact':True,'friction_plane_uv_affine_residual':uv_error,
            'old_nominal_outer_chord_sag_m':radius*(1-math.cos(math.pi/32)),
            'new_nominal_outer_chord_sag_m':radius*(1-math.cos(math.pi/52)),
            'native_encoding':encoding,'whole_field':field}

def caliper(stage,original,geo,encode,row,reference):
    if len(original.modifiers)!=1 or original.modifiers[0].type!='BEVEL':
        raise ValueError('Expected actual caliper edge modifier')
    bevel=original.modifiers[0]
    if bevel.segments!=1 or abs(bevel.width-.002)>1e-8 or not bevel.harden_normals:
        raise ValueError('Unexpected actual caliper edge contract')
    graph=bpy.context.evaluated_depsgraph_get()
    mesh=bpy.data.meshes.new_from_object(original.evaluated_get(graph),preserve_all_data_layers=True,depsgraph=graph)
    stage.modifiers.clear();stage.data=mesh;mesh.update();mesh.calc_loop_triangles()
    assert len(mesh.vertices)==80 and len(mesh.polygons)==68 and len(mesh.loop_triangles)==156
    assert not any(p.use_smooth for p in mesh.polygons)
    assert [list(t.loops) for t in mesh.loop_triangles]==reference['triangle_loops'],'Caliper corner mapping changed'
    assert sorted(l.name for l in mesh.uv_layers)==sorted(reference['uvs'])
    for layer in mesh.uv_layers:
        assert len(layer.data)==len(reference['uvs'][layer.name])
        for datum,value in zip(layer.data,reference['uvs'][layer.name]):datum.uv=value
    old=row(stage);old_normals=[tuple(n.vector) for n in mesh.corner_normals]
    assert all(old[k]==reference[k] for k in old if k!='name'),'Native caliper copy differs after exact UV restoration'
    # Preserve the actual modifier-authored native codes on twenty unowned
    # polygons. The current caliper has hardened custom normals, not a zero-code flat field.
    sharp=mesh.attributes.get('sharp_edge') or mesh.attributes.new(name='sharp_edge',type='BOOLEAN',domain='EDGE')
    for value in sharp.data:value.value=True
    mesh.update()
    assert mesh.attributes.get('custom_normal') is not None,'Expected actual modifier-authored normal codes'
    preserved_codes=[tuple(value.value) for value in mesh.attributes['custom_normal'].data]
    assert [tuple(n.vector) for n in mesh.corner_normals]==old_normals,'Independent caliper spaces changed actual field'
    targets=list(old_normals);owned=[];owned_loops=[]
    for index,face in enumerate(mesh.polygons):
        points=[mesh.vertices[i].co for i in face.vertices]
        y=sum(p.y for p in points)/len(points);z=sum(p.z for p in points)/len(points)
        n=face.normal;den=math.hypot(n.y,n.z)*math.hypot(y,z)
        radial_dot=(n.y*y+n.z*z)/den if den else 0.
        if abs(n.x)>=.999 or abs(radial_dot)<=.9998:continue
        assert len(face.vertices)==4
        # All retained circular strips have nx=0. Their one-segment axial
        # chamfers have nx=+/-sqrt(1/2). Angular end closures are excluded.
        nx=0. if abs(n.x)<.001 else math.copysign(math.sqrt(.5),n.x)
        assert abs(n.x-nx)<1e-5
        sign=math.copysign(1.,radial_dot);radial=math.sqrt(1-nx*nx)
        for loop in face.loop_indices:
            p=mesh.vertices[mesh.loops[loop].vertex_index].co;r=math.hypot(p.y,p.z)
            targets[loop]=(nx,sign*radial*p.y/r,sign*radial*p.z/r);owned_loops.append(loop)
        owned.append(index)
    assert len(owned)==48 and len(owned_loops)==192
    encoding=encode(mesh,targets);assert encoding['passed']
    keep=sorted(set(range(len(mesh.loops)))-set(owned_loops))
    for loop in keep:mesh.attributes['custom_normal'].data[loop].value=preserved_codes[loop]
    mesh.update()
    assert all(tuple(mesh.corner_normals[i].vector)==old_normals[i] for i in keep),'Unowned cap/end field changed'
    after=row(stage)
    assert all(old[k]==after[k] for k in old if k!='normals'),'Caliper non-normal field changed'
    field=whole_field_bound(mesh,targets)
    # The field at both uses of each curved-strip edge is explicit, so shared
    # arc station continuity is measured rather than inferred from smooth flags.
    by_edge={};jumps=[]
    for pi in owned:
        face=mesh.polygons[pi];loops=list(face.loop_indices)
        for a,b in zip(loops,loops[1:]+loops[:1]):
            ids=(mesh.loops[a].vertex_index,mesh.loops[b].vertex_index)
            by_edge.setdefault(tuple(sorted(ids)),[]).append((pi,{ids[0]:a,ids[1]:b}))
    def angle(a,b):
        cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
        return math.degrees(math.atan2(math.hypot(*cross),sum(x*y for x,y in zip(a,b))))
    for edge,uses in by_edge.items():
        if len(uses)!=2:continue
        (_,a),(_,b)=uses
        if any(math.dist(targets[a[v]],targets[b[v]])>1e-10 for v in edge):continue
        jumps.append({'edge':list(edge),'old_degrees':max(angle(old_normals[a[v]],old_normals[b[v]]) for v in edge),
                      'new_degrees':max(angle(tuple(mesh.corner_normals[a[v]].vector),tuple(mesh.corner_normals[b[v]].vector)) for v in edge)})
    return {'scope':'Authored continuous angular normal response on existing circular strips and their axial chamfers only.',
            'owned_polygons':owned,'owned_loops':owned_loops,'protected_flat_loops':keep,
            'protected_decoded_fields_exact':True,'evaluated_geometry_uv_material_exact':True,
            'native_encoding':encoding,'whole_field':field,'shared_arc_edges':jumps,
            'maximum_old_arc_normal_jump_degrees':max(r['old_degrees'] for r in jumps),
            'maximum_new_arc_normal_jump_degrees':max(r['new_degrees'] for r in jumps)}

def apply(*,geo,row,encode,exact_scan):
    """Return (changed_objects, proof, before_rows), no source/save/export IO."""
    names=sorted('LOD0_BrakeFace_'+suffix+str(side) for suffix in ('FL','FR','RL','RR') for side in (-1,1))
    names+=sorted('LOD0_'+kind+'_'+suffix+(str(side) if side is not None else '')
                  for suffix in ('FL','FR','RL','RR') for kind,sides in
                  (('CaliperCheek',(-1,1)),('CaliperBridge',(None,))) for side in sides)
    objects={n:bpy.data.objects[n] for n in names};before={n:row(o) for n,o in objects.items()}
    staged=[];meshes=[];proof={}
    try:
        for name,obj in objects.items():
            stage=obj.copy();stage.name='Private_BrakeEdge_'+name;obj.users_collection[0].objects.link(stage);staged.append((obj,stage))
            if name.startswith('LOD0_BrakeFace_'):metric=rotor(stage,obj,geo,encode)
            else:metric=caliper(stage,obj,geo,encode,row,before[name])
            meshes.append(stage.data)
            current=row(stage);current['name']=name
            quality=geo.evaluated_counts(stage);self_result=exact_scan(current)
            assert self_result['status']=='passed',(name,self_result)
            assert all(quality[k]==0 for k in ('duplicate_faces','nonmanifold_edges','degenerate_faces','degenerate_triangles',
                'triangulated_duplicate_faces','triangulated_nonmanifold_edges','nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals'))
            assert stage.parent==obj.parent and stage.matrix_world==obj.matrix_world
            if not name.startswith('LOD0_BrakeFace_'):
                assert all(current[k]==before[name][k] for k in current if k!='normals'),'Evaluated caliper changed during freeze'
            metric.update(quality=quality,exact_self=self_result,
                          delta_triangles=quality['triangles']-len(before[name]['triangles']))
            proof[name]=metric
        assert sum(r['delta_triangles'] for r in proof.values())==640
        for obj,stage in staged:obj.modifiers.clear();obj.data=stage.data
        bpy.context.view_layer.update()
        return list(objects.values()),proof,before
    finally:
        for _,stage in staged:
            if stage.data not in meshes:meshes.append(stage.data)
            bpy.data.objects.remove(stage,do_unlink=True)
        for mesh in meshes:
            if mesh.users==0:bpy.data.meshes.remove(mesh)
