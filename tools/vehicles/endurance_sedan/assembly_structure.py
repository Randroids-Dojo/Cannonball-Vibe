"""Reports-only coherent floor/driveline construction trial14, never auto-adopted.

The caller supplies an unsaved current full08 scene after frozen wheelhouse candidate08.
All dimensions below are original packaging trials. The probe reports every
remaining contact; successful construction alone is not acceptance.
"""
import itertools, math
import bmesh, bpy
from mathutils import Vector
from . import geometry as geo
from .floor_panels import freeze,coat_cut_faces,remove
from . import assembly_sections as sections
from . import assembly_fields as owned

DIFFERENTIAL_SHIFT_Y=-.045
TRUNK_DECK_TOP=.3885
TRUNK_DECK_BOTTOM=.3845
REAR_SPLIT_Y=-1.650
FRONT_FIREWALL_Y=.757
CUTS={}

def points(obj):
    bpy.context.view_layer.update();ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh()
    try:return [tuple(ev.matrix_world@v.co) for v in m.vertices]
    finally:ev.to_mesh_clear()

def replace(old,new):
    name=old.name
    if any(abs(old.matrix_world[i][j]-(1 if i==j else 0))>1e-7 for i in range(4) for j in range(4)):
        raise ValueError('Fixed source-meter replacement expected: '+name)
    old.modifiers.clear();old.data=new.data
    for m in new.modifiers:
        copy=old.modifiers.new(m.name,m.type)
        for p in m.bl_rna.properties:
            if not p.is_readonly and p.identifier not in ('name','type','rna_type'):
                try:setattr(copy,p.identifier,getattr(m,p.identifier))
                except (AttributeError,TypeError):pass
    bpy.data.objects.remove(new,do_unlink=True)
    return old

def copy_mesh(obj,name,collection):
    result=obj.copy();result.data=obj.data.copy();result.name=name;collection.objects.link(result)
    return result

def hull_volume(name,objects,padding,collection,material,low=-.150):
    cloud=[]
    for obj in objects:
        for p in points(obj):
            for dx,dy in itertools.product((-padding,padding),repeat=2):
                cloud.append((p[0]+dx,p[1]+dy,p[2]+padding))
                cloud.append((p[0]+dx,p[1]+dy,low))
    bm=bmesh.new()
    for p in sorted(set(cloud)):bm.verts.new(p)
    bm.verts.ensure_lookup_table()
    op=bmesh.ops.convex_hull(bm,input=list(bm.verts),use_existing_faces=False)
    if op.get('geom_unused'):bmesh.ops.delete(bm,geom=op['geom_unused'],context='VERTS')
    if op.get('geom_interior'):
        interior=[x for x in op['geom_interior'] if x.is_valid]
        if interior:bmesh.ops.delete(bm,geom=interior,context='VERTS')
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    data=bpy.data.meshes.new(name+'Mesh');bm.to_mesh(data);bm.free()
    obj=bpy.data.objects.new(name,data);collection.objects.link(obj);data.materials.append(material);geo.project_uv(obj)
    return obj

def difference(obj,cutter):
    coordinates=points(cutter)
    CUTS.setdefault(obj.name,[]).append({'cutter':cutter.name,'bounds':[[min(p[i] for p in coordinates) for i in range(3)],[max(p[i] for p in coordinates) for i in range(3)]]})
    coating=obj.data.materials[0]
    # A local single-coating tool keeps the real cutter material untouched.
    tool=copy_mesh(cutter,'PrivateSingleCoatingTool',obj.users_collection[0])
    freeze(tool);tool.data.materials.clear();tool.data.materials.append(coating)
    for face in tool.data.polygons:face.material_index=0
    try:geo.boolean(obj,tool);coat_cut_faces(obj,coating)
    finally:remove(tool)

def union(obj,other):
    coating=obj.data.materials[0]
    geo.boolean(obj,other,'UNION');coat_cut_faces(obj,coating)

def finish(obj):
    if obj.name in owned.CAPTURED_VERTICES:owned.clean(obj)
    else:geo.repair_triangulation(obj)
    obj.data.update()
    obj.data.normals_split_custom_set([tuple(p.normal) for p in obj.data.polygons for _ in p.loop_indices])
    geo.project_uv(obj)

def native_box(name,center,size,material,collection,parent,radius=.001):
    obj=geo.box(name,center,size,material,collection,parent,radius=radius)
    for m in obj.modifiers:
        if m.type=='BEVEL':m.segments=1
    freeze(obj);return obj

def build(collection,parent,mats):
    changed={};original_fields={};proof={'original_choices':{},'named_interfaces':[]};private=[]
    def remember(o):changed[o.name]=o;return o
    try:
        # Case and shaft positions are explicitly fictional geometry. Wheel,
        # spring, seat, belt and rail anchors are not touched.
        diff=bpy.data.objects['LOD0_RearDifferential'];freeze(diff)
        for v in diff.data.vertices:v.co.y+=DIFFERENTIAL_SHIFT_Y
        diff.data.update();geo.project_uv(diff);remember(diff)
        shaft=geo.tube('PrivatePropShaft',[(0,.223,.319),(0,-1.415+DIFFERENTIAL_SHIFT_Y,.347)],.031,mats['metal'],collection,parent,sides=12)
        remember(replace(bpy.data.objects['LOD0_PropShaft'],shaft))
        for side in (-1,1):
            shaft=geo.tube('PrivateRearHalfShaft',[(side*.116,-1.46+DIFFERENTIAL_SHIFT_Y,.310),(side*.744,-1.46,.343)],.020,mats['metal'],collection,parent,sides=10)
            remember(replace(bpy.data.objects['LOD0_RHalfShaft_'+str(side)],shaft))
            route=[(side*.090,1.238,.795),(side*.090,1.120,.795),(side*.090,.985,.795),(side*.290,.950,.610),(side*.280,.941,.390),
                   (side*.265,.820,.210),(side*.235,.680,.190),(side*.220,.400,.200),(side*.117,.230,.220)]
            down=geo.tube('PrivateLowDownpipe',route,.034,mats['metal'],collection,parent,sides=12)
            remember(replace(bpy.data.objects['LOD0_Downpipe_'+str(side)],down))
            muffler=native_box('PrivateRearMuffler',(side*.540,-2.087,.305),(.240,.370,.140),mats['metal'],collection,parent,.030)
            remember(replace(bpy.data.objects['LOD0_RearMuffler_'+str(side)],muffler))
        shield=native_box('PrivateShortHeatShield',(0,(-.894+.205)/2,.274),(.409,.205+.894,.009),mats['alloy'],collection,parent,.003)
        remember(replace(bpy.data.objects['LOD0_TunnelHeatShield'],shield))
        # An actual underside cavity leaves the seat's outside frame and all
        # support planes fixed while clearing the existing cylinder and straps.
        rail=bpy.data.objects['LOD0_FrontRRailBase'];original_fields[rail.name]=owned.capture(rail)
        pocket=native_box('PrivateExtinguisherBay',(.430,-.1685,.2905),(.089,.301,.105),mats['metal'],collection,None,.002)
        difference(rail,pocket);remove(pocket);finish(rail);remember(rail)

        carpet=mats['carpet']
        # Lower original subframe cradle; wheel/control-arm/spring endpoints
        # remain unchanged. Finite mounting tabs remain a measured next step.
        cradle=geo.tube('PrivateRearCradle',[(-.455,-1.629,.240),(-.38,-1.297,.169),(.38,-1.297,.169),(.455,-1.629,.240)],.024,mats['metal'],collection,parent,sides=6)
        remember(replace(bpy.data.objects['LOD0_RSubframe'],cradle))
        outer=sections.volume('PrivateCabinOuterEnvelope',collection,carpet)
        inner=sections.volume('PrivateCabinInnerEnvelope',collection,carpet,inner=True,low=-.15)
        private.extend((outer,inner));inside=[inner]
        floor=sections.shell('PrivateFormedFloor',collection,carpet,parent)
        limit=geo.box('PrivateCabinYEnd',(0,-.6,.4),(2,2.714,2),carpet,collection,radius=0)
        geo.boolean(floor,limit,'INTERSECT');remove(limit)
        for side in (-1,1):
            cutter=geo.tube('PrivateRearFloorWheelCut',[(side*.670,-1.46,.3433),(side*1.12,-1.46,.3433)],.4505,None,collection,sides=96)
            difference(floor,cutter);remove(cutter)
            port=geo.tube('PrivateFuelFloorPort',[(side*.275,-.745,.210),(side*.263,-.745,.300)],.022,None,collection,sides=20)
            difference(floor,port);remove(port)
        tower_tools=[]
        for side in (-1,1):
            damper=bpy.data.objects['LOD0_RDamper_'+str(side)];vertices=points(damper)
            lo=[min(v[i] for v in vertices)-.005 for i in range(3)];hi=[max(v[i] for v in vertices)+.005 for i in range(3)];lo[2]=.360
            tower=geo.box('LOD0_RearDamperEnclosure_'+str(side),[(a+b)/2 for a,b in zip(lo,hi)],[b-a for a,b in zip(lo,hi)],mats['carpet'],collection,parent,radius=0)
            tool=copy_mesh(tower,'PrivateDamperEnclosureOuter',collection);private.append(tool);tower_tools.append(tool)
            ilo=[v+.002 for v in lo];ihi=[v-.002 for v in hi];ilo[2]=.20
            void=geo.box('PrivateDamperEnclosureVoid',[(a+b)/2 for a,b in zip(ilo,ihi)],[b-a for a,b in zip(ilo,ihi)],mats['carpet'],collection,radius=0)
            difference(tower,void);remove(void);difference(floor,tool);remember(tower)
        # Rebate the floor against the retained closed trim, never cut open the trim.
        for symbol in ('L','R'):difference(floor,bpy.data.objects['LOD0_RearWheelhouseTrim_'+symbol])
        difference(floor,bpy.data.objects['LOD0_FootRest'])
        center_box=geo.box('PrivateTunnelSplit',(0,-.45,.5),(.460,3.0,2.0),carpet,collection,radius=0)
        tunnel=copy_mesh(floor,'PrivateFormedTransmissionTunnel',collection)
        geo.boolean(tunnel,center_box,'INTERSECT');difference(floor,center_box);remove(center_box)
        finish(floor);finish(tunnel)
        remember(replace(bpy.data.objects['LOD0_CabinFloor'],floor));remember(replace(bpy.data.objects['LOD0_TransmissionTunnel'],tunnel))
        # Smaller hollow crossover cover lies entirely between the unchanged seats/console.
        chase=native_box('PrivateRearChase',(0,(-.839-.665)/2,.365),(.586,.174,.229),mats['trim'],collection,parent,0)
        chase_void=geo.box('PrivateChaseInner',(0,(-.839-.665)/2,.354),(.560,.148,.227),carpet,collection,radius=0)
        difference(chase,chase_void);remove(chase_void)
        remember(replace(bpy.data.objects['LOD0_RearConsoleChase'],chase))
        # A real flared tunnel backs each removed lower-console face; the
        # unchanged upper console still owns the four controls and two cups.
        for name in ('LOD0_CenterConsole','LOD0_RearBulkheadLower','LOD0_RearConsoleChase'):
            obj=bpy.data.objects[name]
            if name!='LOD0_RearConsoleChase':original_fields[name]=owned.capture(obj)
            else:freeze(obj)
            difference(obj,outer)
            if name=='LOD0_RearBulkheadLower':
                for tool in tower_tools:difference(obj,tool)
            finish(obj);remember(obj)
        # A separate manufactured liner occupies the actual cabin/body boundary.
        bottom=[(-.740,.262),(-.206,.262),(-.186,.504),(.186,.504),(.206,.262),(.740,.262)]
        outline=bottom+[(.740,.932),(-.740,.932)]
        vertices=[(x,y,z) for y in (.757,.760) for x,z in outline];n=len(outline)
        faces=[tuple(reversed(range(n))),tuple(n+i for i in range(n))]
        faces += [(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)]
        liner=geo.mesh('PrivateFormedFirewall',vertices,faces,mats['trim'],collection,parent)
        finish(liner);remember(replace(bpy.data.objects['LOD0_Firewall'],liner))
        dash=bpy.data.objects['LOD0_DashboardCore'];original_fields[dash.name]=owned.capture(dash)
        cutter=geo.box('PrivateDashboardHiddenRearCut',(0,(.75575+1.50)/2,.75),(3,1.50-.75575,2),mats['trim'],collection,radius=0)
        difference(dash,cutter);remove(cutter);finish(dash);remember(dash)
        console=bpy.data.objects['LOD0_CenterConsole']
        for side in (-1,1):
            pocket=native_box('PrivateBucklePocket',(side*.160,-.318,.496),(.070,.057,.083),mats['trim'],collection,None,.002)
            difference(console,pocket);remove(pocket)
        cavity=native_box('PrivateConsoleHollow',(0,-.080,.395),(.256,1.126,.240),mats['trim'],collection,None,.004)
        difference(console,cavity);remove(cavity)
        armrest=bpy.data.objects['LOD0_ConsoleArmrest']
        support_z=min(p[2] for p in points(armrest))
        compact=geo.box('PrivateCompactArmrestPocket',(0,(-.63725-.29875)/2,(support_z+.8)/2),(.2695,.3385,.8-support_z),mats['trim'],collection,radius=0)
        difference(console,compact);remove(compact);finish(console)
        proof['compact_armrest_pocket']={'x_m':[-.13475,.13475],'y_m':[-.63725,-.29875],'base_z_m':support_z,'top_z_m':.8,'isolated_native_evidence':'console-compact08.json','assembled_rebind':'pending'}
        pad=geo.box('LOD0_SelectorSeatingPad',(0,.191,.5865),(.200,.186,.001),mats['rubber'],collection,parent,radius=0)
        remember(pad)

        # Flat raised cargo deck clears the two exhaust cases. Its real fuel
        # passage follows the same existing line rather than an invented hole.
        deck=geo.box('PrivateRaisedCargoDeck',(0,(-2.430+REAR_SPLIT_Y)/2,(TRUNK_DECK_TOP+TRUNK_DECK_BOTTOM)/2),
                     (1.476,REAR_SPLIT_Y+2.430,TRUNK_DECK_TOP-TRUNK_DECK_BOTTOM),carpet,collection,parent,radius=0)
        for side in (-1,1):
            wheel_void=geo.tube('PrivateDeckWheelCut',[(side*.670,-1.46,.3433),(side*1.12,-1.46,.3433)],.4505,None,collection,sides=96)
            difference(deck,wheel_void);remove(wheel_void)
        route=[(.49,-1.99,.460),(.473333333333,-1.99,.410),(.378,-1.99,.410),(.378,-1.99,.350),(.354,-1.99,.210),(.354,-1.36,.210),(.43,-1.27,.210)]
        line=geo.tube('PrivateCargoFuelRoute',route,.006,mats['rubber'],collection,parent,sides=8)
        remember(replace(bpy.data.objects['LOD0_FuelTransferLine'],line))
        start=Vector(route[2]);end=Vector(route[3]);axis=(end-start).normalized()
        center=start+(end-start)*(((TRUNK_DECK_TOP+TRUNK_DECK_BOTTOM)/2-start.z)/(end.z-start.z))
        port=geo.tube('PrivateRaisedFloorFuelBore',[center-axis*.08,center+axis*.08],.018,None,collection,sides=24)
        difference(deck,port);remove(port)
        gland=geo.hollow_tube('PrivateRaisedFloorGland',center-axis*.017,center+axis*.017,.019,.010,mats['rubber'],collection,parent,segments=16)
        remember(replace(bpy.data.objects['LOD0_FuelBulkheadGland'],gland));finish(deck)
        remember(replace(bpy.data.objects['LOD0_TrunkCarpet'],deck))
        for name,delta in (('LOD0_RearBattery',.063),('LOD0_BatteryClamp',.0625),('LOD0_EnduranceToolBag',.060),('LOD0_ToolBagHandle',.060)):
            obj=bpy.data.objects[name];freeze(obj)
            for v in obj.data.vertices:v.co.z+=delta
            obj.data.update();geo.project_uv(obj);remember(obj)
        # Preserve original exterior body surfaces outside the explicitly
        # authored cabin/cargo pockets. These are real open-underbody pockets.
        proof['body_cleanup_failures']=[]
        for body_name in ('LOD0_StructuralBody','LOD0_RearBumper'):
            body=bpy.data.objects[body_name];original_fields[body_name]=owned.capture(body)
            # Only the central formed cavity opens the original body floor.
            # It does not remove the complete cabin/body footprint.
            central=copy_mesh(inner,'PrivateBodyCentralCavity',collection)
            strip=geo.box('PrivateCavityStrip',(0,-.45,.5),(.452,3,2),carpet,collection,radius=0)
            geo.boolean(central,strip,'INTERSECT');remove(strip)
            difference(body,central);remove(central)
            for side in (-1,1):
                void=hull_volume('PrivateMufflerClearance',[bpy.data.objects['LOD0_RearMuffler_'+str(side)]],.006,collection,carpet)
                difference(body,void);remove(void)
            if body_name=='LOD0_StructuralBody':
                for side in (-1,1):
                    route=[(side*.090,1.238,.795),(side*.090,1.120,.795),(side*.090,.985,.795),(side*.290,.950,.610),(side*.280,.941,.390),
                           (side*.265,.820,.210),(side*.235,.680,.190),(side*.220,.400,.200),(side*.117,.230,.220)]
                    tool=geo.tube('PrivateDownpipeBodyPassage',route,.040,mats['metal'],collection,sides=12)
                    difference(body,tool);remove(tool)
                route=[(-.455,-1.629,.240),(-.38,-1.297,.169),(.38,-1.297,.169),(.455,-1.629,.240)]
                tool=geo.tube('PrivateRearCradleBodyPassage',route,.030,mats['metal'],collection,sides=12)
                difference(body,tool);remove(tool)
            # Diagnostic12 retains failures and native inherited corner fields.
            # It does not accept the body or flatten/reproject its exterior.
            try:owned.clean(body)
            except ValueError as error:
                proof['body_cleanup_failures'].append({'name':body.name,'error':str(error),'counts':geo.evaluated_counts(body)})
                raise
            remember(body)
        # Finite simple mounts: every top/bottom face has an explicitly named
        # actual mating plane. Exact fit and all unrelated pairs are checked.
        for fore,cy,zfloor in (('Front',-.18,.266),('Rear',-1.10,.296)):
            for side,s in ((-1,'L'),(1,'R')):
                for offset in (-.12,.12):
                    x=side*.43+offset
                    for label,lo,hi,mat in (('FloorPedestal',zfloor,.3015,mats['metal']),('SeatIsolator',.3465,.348,mats['rubber'])):
                        name='LOD0_'+fore+s+label+str(offset)
                        mount=geo.box(name,(x,cy,(lo+hi)/2),(.040,.300,hi-lo),mat,collection,parent,radius=0)
                        remember(mount)
        for side in (-1,1):
            for y,lo in ((-2.10,.295),(-1.70,.240)):
                name='LOD0_CargoDeckPedestal_'+str(side)+'_'+str(y)
                remember(geo.box(name,(side*.250,y,(lo+TRUNK_DECK_BOTTOM)/2),(.040,.040,TRUNK_DECK_BOTTOM-lo),mats['metal'],collection,parent,radius=0))
                name='LOD0_AuxTankFoot_'+str(side)+'_'+str(y)
                remember(geo.box(name,(side*.250,y,(TRUNK_DECK_TOP+.420)/2),(.040,.040,.420-TRUNK_DECK_TOP),mats['rubber'],collection,parent,radius=0))
        for y in (-1.980,-1.942):
            remember(geo.box('LOD0_TransferPumpFoot_'+str(y),(.537,y,(TRUNK_DECK_TOP+.415)/2),(.016,.018,.415-TRUNK_DECK_TOP),mats['rubber'],collection,parent,radius=0))
        # Preserve the rejected chase triangulation in13, then use only the
        # existing exact-witness repair on14; no geometric tolerance change.
        from . import boolean_surface
        from .qa.self_geometry import scan
        def row(obj):
            m=obj.data;m.calc_loop_triangles();return {'name':obj.name,'vertices':[tuple(v.co) for v in m.vertices],'triangles':[tuple(t.vertices) for t in m.loop_triangles]}
        chase=bpy.data.objects['LOD0_RearConsoleChase']
        proof['chase_exact_repair']=boolean_surface.repair(chase,scan,geo.evaluated_counts)
        proof['body_exact_diagonal_repair']={name:boolean_surface.repair(bpy.data.objects[name],scan,geo.evaluated_counts) for name in ('LOD0_StructuralBody','LOD0_RearBumper')}
        proof['original_surface_fields']={name:owned.restore(bpy.data.objects[name],refs) for name,refs in original_fields.items()}
        proof['original_cut_bounds']={name:CUTS.get(name,[]) for name in original_fields}
        proof['new_scope04']='scope04.json; finite mounts and all changed/rest fit still pending'
        proof['original_choices']={'differential_translation_y_m':DIFFERENTIAL_SHIFT_Y,'rear_wheel_hardpoints':'unchanged',
            'muffler_centers_source_m':[[s*.540,-2.087,.305] for s in (-1,1)],'muffler_dimensions_m':[.240,.370,.140],
            'cargo_deck_top_bottom_m':[TRUNK_DECK_TOP,TRUNK_DECK_BOTTOM],'cargo_deck_front_y_m':REAR_SPLIT_Y,
            'fuel_gland_center_m':list(center),'fuel_gland_axis':list(axis),'floor_base_profile_yz_m':sections.BASE_PROFILE,
            'floor_crown_profile_yz_m':sections.CROWN_PROFILE,'x_stations_m':sections.X_STATIONS,'y_stations_m':sections.Y_STATIONS,'center_separation_planes_x_m':[-.230,.230],
            'caveat':'Native construction trial; all contacts/fields/topology still require the associated report and correction.'}
        return changed,proof
    finally:
        for obj in private:
            if obj.name in bpy.data.objects:remove(obj)
