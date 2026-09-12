"""Original Meridian exterior assemblies, authored in meters and editable."""

import math

from mathutils import Euler, Vector

from . import geometry as geo
from . import model
from . import rear_optics


def nose_y(x):
    return 2.40-.15*(abs(x)/.825)**3


def tail_y(x):
    return -2.54+.105*(abs(x)/.83)**3


def fascia_strip(name,cx,cz,width,height,front,back,material,collection,parent,conform_front=False,steps=24,vertical_steps=1):
    """Closed curved ribbon with end walls; front/back are Y(X) profiles."""
    if conform_front:
        # Sample the same complete body contour in both X and Z. A separate
        # nose curve projected the old outer lamp corners up to29 mm forward.
        vertices=[];faces=[];stride=vertical_steps+1;layer=(steps+1)*stride
        for function in (front,back):
            for i in range(steps+1):
                x=cx-width/2+width*i/steps
                for j in range(vertical_steps+1):
                    z=cz-height/2+height*j/vertical_steps
                    vertices.append((x,function(x)+model.front_surface_y(x,z)-nose_y(x),z))
        for i in range(steps):
            for j in range(vertical_steps):
                a=i*stride+j;b=(i+1)*stride+j
                faces.extend([(a,b,b+1,a+1),(a+layer,a+1+layer,b+1+layer,b+layer)])
        boundary=[i*stride for i in range(steps+1)]
        boundary += [steps*stride+j for j in range(1,vertical_steps+1)]
        boundary += [i*stride+vertical_steps for i in reversed(range(steps))]
        boundary += [j for j in reversed(range(1,vertical_steps))]
        for a,b in zip(boundary,boundary[1:]+boundary[:1]):faces.append((a,a+layer,b+layer,b))
        obj=geo.mesh(name,vertices,faces,material,collection,parent,smooth=True)
        obj['fit_surface']='Original pre-cut body X/Z ray, same contour as the optical aperture'
        return obj
    vertices=[]
    for i in range(steps+1):
        x=cx-width/2+width*i/steps
        vertices.extend([(x,back(x),cz-height/2),(x,front(x),cz-height/2),(x,front(x),cz+height/2),(x,back(x),cz+height/2)])
    faces=[]
    for i in range(steps):
        for j in range(4):
            faces.append((4*i+j,4*(i+1)+j,4*(i+1)+(j+1)%4,4*i+(j+1)%4))
    faces.extend([(3,2,1,0),tuple(4*steps+i for i in range(4))])
    return geo.mesh(name,vertices,faces,material,collection,parent,smooth=True)


def attach(obj, pivot):
    geo.parent_at_pivot(obj, pivot)
    return obj


def cut_box(body, name, center, size, collection):
    cutter = geo.box(name, center, size, None, collection, radius=0)
    geo.boolean(body, cutter)
    model.remove(cutter)


def ring_y(name, center, radius, thickness, material, collection, parent, sides=24):
    points = [(center[0] + radius * math.cos(i * math.tau / sides), center[1],
               center[2] + radius * math.sin(i * math.tau / sides)) for i in range(sides)]
    return geo.tube(name, points, thickness, material, collection, parent, sides=6, closed=True)


def fascia(body, collection, lod, mats, pivots, spec):
    """Two low horizontal cooling slots and split optical pods; no donor grille."""
    cut_box(body, 'MainCoolingOpening', (0, 2.32, .48), (1.105, .34, .235), collection)
    geo.box('LOD0_CentralRadiator', (0, 2.155, .49), (1.09, .025, .223), mats['metal'], collection, lod, radius=.003)
    for i in range(20):
        x = -.516 + i * .0543
        geo.box('LOD0_MainGrilleUpright_' + str(i), (x, 2.332, .48), (.006, .045, .228), mats['trim'], collection, lod, radius=.001)
    for i in range(4):
        geo.box('LOD0_MainGrilleRail_' + str(i), (0, 2.342, .392 + i * .058), (1.09, .013, .007), mats['trim'], collection, lod, radius=.002)
    for side, symbol in ((-1, 'L'), (1, 'R')):
        cut_box(body, 'BrakeCoolingOpening_' + symbol, (side * .716, 2.255, .454), (.223, .39, .214), collection)
        geo.box('LOD0_BrakeDuctInterior_' + symbol, (side * .716, 2.098, .454), (.216, .024, .205), mats['rubber'], collection, lod, radius=.004)
        for i in range(3):
            fascia_strip('LOD0_BrakeDuctVane_'+symbol+str(i),side*.716,.385+i*.067,.210,.007,lambda x:nose_y(x)-.037,lambda x:nose_y(x)-.074,mats['trim'],collection,lod)
        cut_box(body, 'OpticalPodOpening_' + symbol, (side * .635, 2.30, .744), (.449, .46, .142), collection)
        fascia_strip('LOD0_HeadlightHousing_'+symbol,side*.635,.744,.442,.135,lambda x:nose_y(x)-.094,lambda x:nose_y(x)-.100,mats['trim'],collection,lod,True,16,4)
        for z in (.6785,.8095):
            fascia_strip('LOD0_HeadlightWall_'+symbol+str(z),side*.635,z,.442,.004,lambda x:nose_y(x)+.001,lambda x:nose_y(x)-.100,mats['trim'],collection,lod,True,16)
        for end in (-1,1):
            wall=fascia_strip('LOD0_HeadlightSideReturn_'+symbol+str(end),side*.635+end*.21925,.744,.0035,.127,lambda x:nose_y(x)+.001,lambda x:nose_y(x)-.100,mats['trim'],collection,lod,True,1,4)
            wall['assembly_boundary']='Closed outer bezel and housing return; clear lens is recessed2 mm'
        for j in (-1, 1):
            cx = side * .635 + j * .095
            py=model.front_surface_y(cx,.746)-.043
            ring_y('LOD0_ProjectorReflector_' + symbol + str(j), (cx,py,.746),.036,.006,mats['mirror'],collection,lod)
            geo.ellipsoid('LOD0_ProjectorOptic_'+symbol+str(j),(cx,py+.005,.746),(.059,.019,.059),mats['optical_glass'],collection,lod,20,10)
            attach(geo.box('LOD0_ProjectorEmitter_'+symbol+str(j),(cx,py+.010,.746),(.033,.004,.032),mats['headlight'],collection,lod,radius=.009),pivots['Light_Head_F'+symbol])
        attach(fascia_strip('LOD0_HeadlightGuide_'+symbol,side*.635,.792,.402,.008,lambda x:nose_y(x)-.010,lambda x:nose_y(x)-.016,mats['headlight'],collection,lod,True,16),pivots['Light_Head_F'+symbol])
        fascia_strip('LOD0_HeadlightCover_'+symbol,side*.635,.744,.435,.127,lambda x:nose_y(x)-.001,lambda x:nose_y(x)-.004,mats['optical_glass'],collection,lod,True,16,4)
        indicator = pivots['Light_Indicator_F' + symbol]
        # An independent narrow amber strip is visible through the clear cover.
        attach(fascia_strip('LOD0_FrontIndicator_'+symbol,side*.635,.692,.390,.008,lambda x:nose_y(x)-.010,lambda x:nose_y(x)-.017,mats['indicator_left' if side<0 else 'indicator_right'],collection,lod,True,16),indicator)
        cut_box(body, 'TailOpticalOpening_' + symbol, (side * .65, -2.4225, .868), (.423, .320, .127), collection)
        rear_optics.build(side,symbol,collection,lod,mats,pivots)
    # Recessed central identifier surround and a continuous quiet lower valance.
    cut_box(body, 'RearRegistrationRecess', (0, -2.512, .606), (.51, .14, .141), collection)
    geo.box('LOD0_RegistrationRecess', (0, -2.463, .606), (.49, .018, .126), mats['trim'], collection, lod, radius=.012)
    geo.box('LOD0_RegistrationPlate', (0, -2.520, .606), (.43, .002, .098), mats['plate'], collection, lod, radius=.0005)
    fascia_strip('LOD0_RearLowerValance',0,.288,1.64,.101,tail_y,lambda x:tail_y(x)+.065,mats['trim'],collection,lod)
    fascia_strip('LOD0_FrontSplitter',0,.219,1.73,.024,nose_y,lambda x:nose_y(x)-.14,mats['trim'],collection,lod)
    for side, symbol in ((-1, 'L'), (1, 'R')):
        for j in (-1, 1):
            center = (side * .647 + j * .045, -2.504, .312)
            ring_y('LOD0_ExhaustLip_' + symbol + str(j), center, .035, .004, mats['wheel'], collection, lod)
            geo.hollow_tube('LOD0_ExhaustTail_' + symbol + str(j), (center[0], -2.505, .312), (center[0], -2.31, .312), .031, .0015, mats['metal'], collection, lod, segments=24)
        geo.box('LOD0_RearReflector_' + symbol, (side * .746, -2.455, .405), (.135, .007, .014), mats['taillight'], collection, lod, radius=.002)
    # The brake center emitter follows the parcel shelf, independently of trunk.
    location = spec['hardpoints_source_m']['Light_Brake_Center']
    attach(geo.box('LOD0_CenterBrakeEmitter', location, (.29, .012, .011), mats['brake'], collection, lod, radius=.002), pivots['Light_Brake_Center'])


def closures_and_trim(collection, lod, mats, pivots, spec):
    sleeve_segments=spec['original_packaging']['primitive_detail_revision24']['hinge_sleeve_segments']
    if sleeve_segments!=8:
        raise ValueError('Hinge sleeve detail needs a new measured construction revision')
    for side, symbol in ((-1, 'L'), (1, 'R')):
        for axle, cy in (('F', -.385), ('R', -1.085)):
            suffix = axle + symbol
            pivot = pivots['Door_' + suffix]
            cx = side * (model.width(cy) - .010)
            # Recess pocket with inset pull and a split keyless pad, not a decal.
            attach(geo.ellipsoid('LOD0_HandlePocket_' + suffix, (cx, cy, .884), (.017, .179, .046), mats['rubber'], collection, lod, 20, 8), pivot)
            attach(geo.box('LOD0_Handle_' + suffix, (cx + side * .008, cy, .884), (.021, .139, .018), mats['paint'], collection, lod, radius=.006), pivot)
            attach(geo.box('LOD0_HandleTouch_' + suffix, (cx + side * .019, cy + .048, .884), (.0015, .015, .010), mats['trim'], collection, lod, radius=.0005), pivot)
        geo.box('LOD0_RockerBlade_' + symbol, (side * .914, -.025, .227), (.037, 2.07, .046), mats['trim'], collection, lod, radius=.009)
        # Discreet perimeter belt line follows original panel curvature.
        for axle,ys in (('F',(.586,.0,-.535)),('R',(-.655,-1.13,-1.655))):
            attach(geo.tube('LOD0_WindowBelt_'+axle+symbol,[(side*.884,y,1.011) for y in ys],.005,mats['trim'],collection,lod,sides=6),pivots['Door_'+axle+symbol])
    for name, ya, yb, xh in (('Hood', .819, 2.192, .717), ('Trunk', -2.351, -2.036, .746)):
        pivot = pivots['Hood_Hinge' if name == 'Hood' else 'Trunk_Hinge']
        halfwidth=.756 if name=='Hood' else .774
        # Hem flange and visible stamped underside ribs move with the closure.
        perimeter=[(-xh+2*xh*t,ya) for t in (0,.25,.5,.75,1)]
        perimeter += [(xh,ya+(yb-ya)*t) for t in (.25,.5,.75,1)]
        perimeter += [(xh-2*xh*t,yb) for t in (.25,.5,.75,1)]
        perimeter += [(-xh,yb-(yb-ya)*t) for t in (.25,.5,.75)]
        points = [(x, y, model.closure_z(name,x,y,halfwidth)-.0012-.007) for x,y in perimeter]
        attach(geo.tube('LOD0_' + name + 'Hem', points, .007, mats['paint'], collection, lod, sides=6, closed=True), pivot)
        for side in (-1, 1):
            x=side*(.68 if name=='Hood' else xh*.80)
            radius=.009
            points = [(x, ya+(yb-ya)*t, model.closure_z(name,x,ya+(yb-ya)*t,halfwidth)-.0012-radius) for t in (.06,.14,.22,.30,.38,.46,.54,.62,.70,.78,.86,.94)]
            rib=geo.tube('LOD0_' + name + 'Rib_' + str(side), points, radius, mats['trim'], collection, lod, sides=6)
            rib['assembly_boundary']='Stamped underside stiffener seated against inner skin; closure-local original geometry'
            attach(rib,pivot)
        for side in (-1, 1):
            x = side * xh * .61
            y=pivot.location.y;z=pivot.location.z
            direction=1 if name=='Hood' else -1
            geo.tube('LOD0_'+name+'HingePin_'+str(side),[(x-.037,y,z),(x+.037,y,z)],.004,mats['metal'],collection,lod,sides=12)
            for end in (-1,1):
                a,b=sorted((x+end*.015,x+end*.033))
                geo.hollow_tube('LOD0_'+name+'HingeFixedKnuckle_'+str(side)+'_'+str(end),(a,y,z),(b,y,z),.008,.0035,mats['metal'],collection,lod,segments=sleeve_segments)
                geo.box('LOD0_'+name+'HingeFixed_'+str(side)+'_'+str(end),(x+end*.024,y-direction*.022,z-.002),(.018,.028,.008),mats['metal'],collection,lod,radius=.001)
            barrel=geo.hollow_tube('LOD0_'+name+'HingeMovingKnuckle_'+str(side),(x-.012,y,z),(x+.012,y,z),.008,.0035,mats['metal'],collection,lod,segments=sleeve_segments)
            barrel['contact_policy']='Concentric 4 mm pin within 4.5 mm bore; 0.5 mm radial bearing clearance'
            attach(barrel,pivot)
            attach_y=.850 if name=='Hood' else -2.068
            attach_z=model.closure_z(name,x,attach_y,halfwidth)-(.0102 if name=='Hood' else .0114)
            points=[(x,y,z),(x,.806,.985),(x,attach_y,attach_z)] if name=='Hood' else [(x,y,z),(x,-2.024,.975),(x,attach_y,attach_z)]
            arm=geo.tube('LOD0_'+name+'OffsetArm_'+str(side),points,.009,mats['metal'],collection,lod,sides=8)
            bore=geo.tube('HingeArmBearingBore',[(x-.025,y,z),(x+.025,y,z)],.0053,mats['metal'],collection,sides=12)
            geo.boolean(arm,bore);model.remove(bore)
            attach(arm,pivot)
    for name, pivot in pivots.items():
        if not name.startswith('Door_'):
            continue
        side = -1 if name.endswith('L') else 1
        y = pivot.location.y
        for z in pivot['hardware_pin_heights_m']:
            # Concealed vertical pin and separately editable bearing sleeves.
            x=pivot.location.x;label='LOD0_'+name+'Hinge_'+str(z)
            geo.tube(label+'Pin',[(x,y,z-.028),(x,y,z+.028)],.004,mats['metal'],collection,lod,sides=12)
            for end in (-1,1):
                a,b=sorted((z+end*.011,z+end*.026))
                fixed=geo.hollow_tube(label+'FixedKnuckle_'+str(end),(x,y,a),(x,y,b),.0065,.002,mats['metal'],collection,lod,segments=sleeve_segments)
                fixed['contact_policy']='Concentric4 mm pin within4.5 mm bore;0.5 mm radial bearing clearance'
                mount=geo.box(label+'FixedMount_'+str(end),(x-side*.012,y+.004,(a+b)/2),(.024,.012,b-a),mats['metal'],collection,lod,radius=.001)
                mount.modifiers[0].segments=1
            moving=geo.hollow_tube(label+'MovingKnuckle',(x,y,z-.009),(x,y,z+.009),.0065,.002,mats['metal'],collection,lod,segments=sleeve_segments)
            moving['contact_policy']='Concentric4 mm pin within4.5 mm bore;0.5 mm radial bearing clearance'
            attach(moving,pivot)
            front=name.startswith('Door_F')
            # The folded arm welds to the outside of the separately modeled
            # bearing sleeve. It does not cross the pin or need a second bore.
            # A bore through the capped curved tube created a valid-looking
            # ngon whose Blender tessellation duplicated one triangle.
            points=[(x-side*.010,y-.003,z),(x-side*(.089 if front else .060),y-(.045 if front else .040),z),
                    (x-side*(.080 if front else .070),y-(.140 if front else .115),z)]
            arm=geo.tube(label+'FoldedArm',points,.005,mats['metal'],collection,lod,sides=8)
            arm['assembly_boundary']='Folded steel arm welded to outer moving sleeve; actual separate sleeve carries the pin bore'
            attach(arm,pivot)


def mirrors(collection, lod, mats, pivots, spec):
    for name in ('Mirror_Left', 'Mirror_Right', 'Mirror_Rear'):
        location = Vector(spec['hardpoints_source_m'][name])
        side = -1 if name == 'Mirror_Left' else 1
        size = (.146, .095, .085) if name != 'Mirror_Rear' else (.235, .024, .066)
        housing=geo.box('LOD0_' + name + 'Housing', location, size, mats['paint'] if name != 'Mirror_Rear' else mats['trim'], collection, lod, radius=.015)
        if name != 'Mirror_Rear':
            door=pivots['Door_FL' if side<0 else 'Door_FR']
            attach(housing,door)
            attach(pivots[name],door)
            attach(pivots['MirrorCamera_Left' if side<0 else 'MirrorCamera_Right'],door)
            attach(geo.tube('LOD0_' + name + 'Stalk', [(side * .865, .59, 1.015), (side * .945, .603, 1.043)], .015, mats['trim'], collection, lod, sides=10),door)
        else:
            # Native windshield/housing measurements define two real flush
            # attachments. The bent arm clears the optic and glass surfaces.
            stalk=geo.tube('LOD0_RearMirrorStalk',[(0,.212,1.293),(0,.224,1.293),
                (0,.218,1.328),(0,.160913706,1.348937035),
                (0,.171318009,1.363625526)],.0035,mats['trim'],collection,lod,sides=12)
            stalk['assembly_boundary']='Flush housing attachment and separate windshield mounting button; original inspection geometry'
            contact=Vector((0,.173052058,1.366073608))
            inward=Vector((0,-.578017294,-.816024482)).normalized()
            tangent=Vector((0,-inward.z,inward.y))
            corners=[contact+Vector((x,0,0))+tangent*t for x,t in
                     ((-.017,-.013),(.017,-.013),(.017,.013),(-.017,.013))]
            vertices=corners+[p+inward*.003 for p in corners]
            pad=geo.mesh('LOD0_RearMirrorMountPad',vertices,
                [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],
                mats['trim'],collection,lod)
            pad['contact_policy']='Named flush adhesive interface on windshield inner face; stalk cap seats on opposite pad face'
        center = location + Vector((0, -size[1] / 2 - .002, 0))
        if name == 'Mirror_Rear':
            center.y -= .0001
        screen('LOD0_' + name + 'Surface', center, (size[0] * .87, size[2] * .87), mats['mirror'], collection, lod, pivots[name])


def screen(name, center, size, material, collection, parent, pivot=None, tilt=0):
    """Single 0..1 display UV rectangle, with declared solid back thickness."""
    rotation = Euler((tilt, 0, 0)).to_matrix()
    vertices = [Vector(center) + rotation @ Vector((x * size[0] / 2, 0, z * size[1] / 2))
                for x, z in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    obj = geo.mesh(name, vertices, [(0, 1, 2, 3)], material, collection, parent)
    # Face normal is -Y, towards a driver behind the dashboard/mirror housing.
    uv = obj.data.uv_layers.active
    for loop in obj.data.polygons[0].loop_indices:
        # Normal recalculation can reorder face loops on a tilted display.
        # Derive coordinates from geometry instead of assigning by loop order.
        vertex=obj.data.vertices[obj.data.loops[loop].vertex_index].co
        local=rotation.transposed()@(vertex-Vector(center))
        uv.data[loop].uv=(local.x/size[0]+.5,local.z/size[1]+.5)
    solid = obj.modifiers.new('Display backing', 'SOLIDIFY')
    solid.thickness = .001
    solid.offset = -1
    obj['uv_purpose'] = 'Single viewport image; full face UV 0..1'
    if pivot is not None:
        attach(obj, pivot)
    return obj
