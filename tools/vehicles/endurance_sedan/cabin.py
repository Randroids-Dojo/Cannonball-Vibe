"""Complete original five-seat cabin and endurance equipment packaging."""

import math

from mathutils import Euler, Vector

from . import geometry as geo
from . import model
from . import roof_trim, restraints
from .exterior import attach, screen


def text_mesh(name, text, position, size, material, collection, parent, rotation=(math.pi / 2, 0, 0)):
    import bmesh
    import bpy

    curve = bpy.data.curves.new(name + 'Lettering', 'FONT')
    curve.body = text
    curve.size = size
    curve.align_x = 'CENTER'
    curve.align_y = 'CENTER'
    curve.extrude = .00012
    curve.resolution_u = 3
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    obj.parent = parent
    obj.location = position
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    obj.select_set(False)
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data);bm.free()
    geo.project_uv(obj)
    obj['lettering_provenance'] = 'Original labels using Blender bundled Bfont outlines'
    obj['maximum_lod'] = 0
    return obj


def seat(collection, lod, mats, name, cx, cy, rear=False):
    width = .475 if rear else .49
    geo.box('LOD0_' + name + 'RailBase', (cx, cy, .324), (width - .10, .47, .045), mats['metal'], collection, lod, radius=.006)
    geo.box('LOD0_' + name + 'CushionFrame', (cx, cy, .408), (width, .51, .12), mats['leather'], collection, lod, radius=.045)
    geo.box('LOD0_' + name + 'CushionInsert', (cx, cy + .018, .476), (width - .137, .436, .054), mats['leather'], collection, lod, radius=.019)
    for side in (-1, 1):
        geo.ellipsoid('LOD0_' + name + 'ThighBolster' + str(side), (cx + side * (width / 2 - .052), cy, .472), (.103, .477, .123), mats['leather'], collection, lod, 20, 10)
    back_rot = Euler((math.radians(18 if not rear else 9), 0, 0))
    geo.box('LOD0_' + name + 'BackShell', (cx, cy - .236, .788), (width, .143, .636), mats['trim'], collection, lod, radius=.035, rotation=back_rot)
    geo.box('LOD0_' + name + 'BackInsert', (cx, cy - .151, .794), (width - .145, .064, .545), mats['leather'], collection, lod, radius=.024, rotation=back_rot)
    for side in (-1, 1):
        geo.ellipsoid('LOD0_' + name + 'BackBolster' + str(side), (cx + side * (width / 2 - .058), cy - .146, .796), (.111, .13, .581), mats['leather'], collection, lod, 20, 12)
    for side in (-1, 1):
        x = cx + side * .070
        geo.tube('LOD0_' + name + 'HeadrestPost' + str(side), [(x, cy - (.35 if not rear else .264), 1.073), (x, cy - (.425 if not rear else .264), 1.158)], .006, mats['metal'], collection, lod, sides=8)
    geo.box('LOD0_' + name + 'Headrest', (cx, cy - (.45 if not rear else .27), 1.163), (.255, .134, .173), mats['leather'], collection, lod, radius=.037)
    for side in (-1, 1):
        x = cx + side * .151
        geo.tube('LOD0_' + name + 'BackPiping' + str(side), [(x, cy - .126, .565), (x, cy - .126, .81), (x, cy - .191, 1.027)], .0008, mats['stitch'], collection, lod, sides=4)
    for j in range(5):
        y = cy - .12 + j * .065
        geo.tube('LOD0_' + name + 'CushionSeam' + str(j), [(cx - .14, y, .504), (cx + .14, y, .504)], .0006, mats['stitch'], collection, lod, sides=4)
    if not rear:
        geo.box('LOD0_' + name + 'SeatSwitch', (cx + (.252 if cx > 0 else -.252), cy - .035, .407), (.012, .087, .016), mats['alloy'], collection, lod, radius=.004)
        geo.box('LOD0_' + name + 'MapPocket', (cx, cy - .333, .755), (.327, .018, .275), mats['fabric'], collection, lod, radius=.017)


def structure(collection, lod, mats):
    floor = geo.box('LOD0_CabinFloor', (0, -.54, .252), (1.57, 2.51, .028), mats['carpet'], collection, lod, radius=0)
    for side in (-1, 1):
        cutter = geo.tube('RearTubFloorCut', [(side * .59, -1.46, .3433), (side * 1.12, -1.46, .3433)], .4483, None, collection, sides=64)
        geo.boolean(floor, cutter)
        model.remove(cutter)
        port=geo.tube('SealedFuelCrossoverPort',[(side*.275,-.745,.210),(side*.263,-.745,.300)],.022,None,collection,sides=20)
        geo.boolean(floor,port);model.remove(port)
    geo.bevel(floor, .002, 2)
    geo.box('LOD0_Firewall', (0, .777, .592), (1.48, .033, .680), mats['trim'], collection, lod, radius=.006)
    geo.box('LOD0_TransmissionTunnel', (0, -.40, .295), (.295, 2.36, .164), mats['carpet'], collection, lod, radius=.030)
    # Sealed crossover chase behind the console; its hollow housing and floor
    # glands keep the original reservoir crossover outside occupant space.
    chase=geo.box('LOD0_RearConsoleChase',(0,-.745,.365),(.586,.239,.229),mats['trim'],collection,lod,radius=0)
    cavity=geo.box('FuelChaseCavity',(0,-.745,.354),(.560,.213,.227),None,collection,radius=0)
    geo.boolean(chase,cavity);model.remove(cavity);geo.bevel(chase,.005,2)
    geo.box('LOD0_RearBulkheadLower', (0, -1.487, .558), (1.315, .028, .585), mats['trim'], collection, lod, radius=.006)
    geo.box('LOD0_RearBulkheadUpper', (0, -1.514, .899), (1.53, .024, .097), mats['carpet'], collection, lod, radius=.006)
    geo.box('LOD0_ParcelShelf', (0, -1.678, .956), (1.49, .410, .035), mats['fabric'], collection, lod, radius=.010)
    for side in (-1, 1):
        geo.ellipsoid('LOD0_RearSpeaker_' + str(side), (side * .487, -1.71, .976), (.247, .163, .013), mats['trim'], collection, lod, 24, 8)
    # Molded lining wraps below the deep inboard roof reinforcement; the
    # side trim remains clear of the moving aperture seals and fixed pillars.
    def headliner(u, v):
        y = -1.225 + 1.32 * v
        half = model.interp(y, [(-1.27, .615), (-.45, .660), (.14, .618)])
        center = model.interp(y, [(-1.27, 1.37), (-.45, 1.45), (.14, 1.395)]) - .024
        x = (2 * u - 1) * min(half,.625)
        return (x, y, center - .027 * math.sin(math.pi * v) * (x / half) ** 2 - .025*(abs(x)/half)**6)
    lining=model.surface('LOD0_Headliner', headliner, 8, 12, .005, mats['fabric'], collection, lod)
    roof_trim.install(collection,lod,mats,lining)


def dashboard(collection, lod, mats, pivots, spec):
    geo.box('LOD0_DashboardCore', (0, .621, .822), (1.565, .33, .232), mats['trim'], collection, lod, radius=.046)
    geo.box('LOD0_DashboardUpper', (0, .603, .935), (1.55, .278, .054), mats['carpet'], collection, lod, radius=.018)
    geo.box('LOD0_DashBeltTrim', (0, .442, .83), (1.504, .015, .030), mats['wheel'], collection, lod, radius=.005)
    for cx, w in ((-.679, .118), (-.079, .121), (.099, .121), (.678, .118)):
        geo.box('LOD0_VentHousing_' + str(cx), (cx, .442, .886), (w, .026, .070), mats['rubber'], collection, lod, radius=.008)
        for j in range(4):
            louver=geo.box('LOD0_VentLouver_' + str(cx) + str(j), (cx, .426, .864 + .014 * j), (w - .018, .011, .004), mats['trim'], collection, lod, radius=.001)
            louver.modifiers[0].segments=1
    geo.box('LOD0_Glovebox', (.463, .446, .701), (.440, .019, .152), mats['leather'], collection, lod, radius=.006)
    geo.box('LOD0_GloveboxHandle', (.463, .432, .757), (.065, .009, .012), mats['alloy'], collection, lod, radius=.002)
    cluster = Vector(spec['hardpoints_source_m']['Instrument_Cluster'])
    geo.box('LOD0_InstrumentBinnacle', cluster + Vector((0, .017, .005)), (.431, .081, .171), mats['carpet'], collection, lod, radius=.022, rotation=Euler((math.radians(-15), 0, 0)))
    # Physical anti-glare shade, above the eye-to-display rays. This blocks
    # upward display light from the windshield while retaining the locked eye.
    geo.box('LOD0_InstrumentShade', cluster+Vector((0,-.0625,.097)),(.448,.125,.008),mats['carpet'],collection,lod,radius=.003)
    for side in (-1,1):
        geo.box('LOD0_InstrumentShadeWing_'+str(side),cluster+Vector((side*.220,-.0605,.078)),(.008,.116,.038),mats['carpet'],collection,lod,radius=.002)
    screen('LOD0_InstrumentDisplay', cluster + Vector((0, -.028, .007)), (.398, .149), mats['screen'], collection, lod, pivots['Instrument_Cluster'], tilt=math.radians(-15))
    # These source-only labels give the parked Blender cabin a readable display.
    # Runtime replaces the screen with actual speed, gear, RPM, fuel and warnings.
    label = text_mesh('LOD0_InstrumentSourceLegend', '0    N    750 RPM', tuple(cluster + Vector((0, -.031, .023))), .021, mats['headlight'], collection, lod, (math.radians(75), 0, 0))
    label['source_preview_only'] = True
    screen('LOD0_NavigationScreen', (0, .463, 1.007), (.238, .137), mats['screen'], collection, lod, tilt=math.radians(-12))
    geo.box('LOD0_NavigationSurround', (0, .481, 1.010), (.261, .037, .160), mats['carpet'], collection, lod, radius=.012)
    text_mesh('LOD0_NavigationTitle', 'MERIDIAN', (0, .456, 1.045), .018, mats['cabin_lettering'], collection, lod)
    # The auxiliary center display is a parked branded screen, not a claim of
    # implemented navigation. All driving values live in the runtime cluster.
    geo.box('LOD0_CenterConsole', (0, -.08, .451), (.279, 1.15, .270), mats['trim'], collection, lod, radius=.026)
    geo.box('LOD0_ConsoleArmrest', (0, -.468, .589), (.267, .336, .060), mats['leather'], collection, lod, radius=.022)
    geo.box('LOD0_SelectorGate', (0, .191, .593), (.215, .201, .012), mats['wheel'], collection, lod, radius=.006)
    geo.box('LOD0_SelectorLever', (0, .185, .640), (.074, .083, .084), mats['leather'], collection, lod, radius=.023)
    for side in (-1, 1):
        geo.ellipsoid('LOD0_Cupholder_' + str(side), (side * .068, -.113, .589), (.094, .147, .018), mats['rubber'], collection, lod, 20, 8)
    for cx in (-.143, .143):
        geo.tube('LOD0_ClimateKnob_' + str(cx), [(cx, .425, .733), (cx, .401, .733)], .024, mats['wheel'], collection, lod, sides=24)
        text_mesh('LOD0_ClimateSetpoint_' + str(cx), '20', (cx, .399, .733), .014, mats['cabin_lettering'], collection, lod)
    for cx in (-.062, 0, .062):
        geo.box('LOD0_ClimateSwitch_' + str(cx), (cx, .419, .737), (.050, .016, .019), mats['trim'], collection, lod, radius=.004)
    # Endurance additions occupy the passenger/console area without blocking eyes.
    geo.box('LOD0_EnduranceRadio', (.360, .480, .636), (.161, .097, .049), mats['trim'], collection, lod, radius=.006)
    text_mesh('LOD0_RadioDisplay', 'CREW  01', (.360, .429, .646), .011, mats['cabin_lettering'], collection, lod)
    geo.tube('LOD0_RadioCable', [(.429, .430, .616), (.471, .297, .535), (.515, .30, .449)], .003, mats['rubber'], collection, lod, sides=6)
    geo.box('LOD0_CrewLogBinder', (.41, -.36, .516), (.25, .32, .029), mats['fabric'], collection, lod, radius=.003)


def moving_controls(collection, lod, mats, pivots):
    wheel = pivots['SteeringWheel_Pivot']
    points = [(.176 * math.cos(i * math.tau / 48), 0, .176 * math.sin(i * math.tau / 48)) for i in range(48)]
    geo.tube('LOD0_SteeringRim', points, .018, mats['leather'], collection, wheel, sides=10, closed=True)
    geo.box('LOD0_SteeringAirbag', (0, -.005, -.006), (.142, .072, .117), mats['leather'], collection, wheel, radius=.025)
    for side in (-1, 1):
        geo.tube('LOD0_SteeringSpoke_' + str(side), [(side * .058, 0, .008), (side * .148, 0, .018)], .021, mats['trim'], collection, wheel, sides=6)
        for j in range(3):
            geo.box('LOD0_SteeringButton_' + str(side) + str(j), (side * (.089 + .018 * j), -.024, .018), (.012, .004, .016), mats['wheel'], collection, wheel, radius=.001)
    geo.tube('LOD0_SteeringLowerSpoke', [(0, .0, -.045), (0, .0, -.150)], .023, mats['wheel'], collection, wheel, sides=6)
    column_drop=wheel.location.z-.910
    geo.tube('LOD0_SteeringColumn', [(-.43, .260, .889+column_drop), (-.43, .536, .786+column_drop)], .043, mats['trim'], collection, lod, sides=16)
    for side in (-1, 1):
        geo.tube('LOD0_ColumnStalk_' + str(side), [(-.43 + side * .032, .284, .884+column_drop), (-.43 + side * .135, .275, .888+column_drop)], .006, mats['trim'], collection, lod, sides=8)
    for name, w, h in (('Pedal_Accelerator', .047, .126), ('Pedal_Brake', .086, .078)):
        pivot = pivots[name]
        geo.box('LOD0_' + name + 'Arm', (0, -.028, .049), (.018, .023, .109), mats['metal'], collection, pivot, radius=.005)
        geo.box('LOD0_' + name + 'Pad', (0, -.047, .069), (w, .019, h), mats['rubber'], collection, pivot, radius=.006)
        for j in range(5):
            geo.box('LOD0_' + name + 'Grip' + str(j), (0, -.058, .069 - h * .35 + j * h * .175), (w * .82, .0018, .003), mats['metal'], collection, pivot, radius=.0004)
    geo.box('LOD0_FootRest', (-.647, .626, .307), (.077, .055, .185), mats['rubber'], collection, lod, radius=.008, rotation=Euler((math.radians(-18), 0, 0)))


def doors_and_belts(collection, lod, mats, pivots, spec):
    for suffix, pivot in ((n.removeprefix('Door_'), p) for n, p in pivots.items() if n.startswith('Door_')):
        side = -1 if suffix.endswith('L') else 1
        y = -.04 if suffix.startswith('F') else -.89
        attach(geo.box('LOD0_Armrest_' + suffix, (side * .771, y, .675), (.088, .366, .062), mats['leather'], collection, lod, radius=.018), pivot)
        attach(geo.box('LOD0_WindowSwitchPod_' + suffix, (side * .733, y + .08, .711), (.035, .142, .012), mats['wheel'], collection, lod, radius=.003), pivot)
        for j in range(2 if suffix.startswith('F') else 1):
            attach(geo.box('LOD0_WindowSwitch_' + suffix + str(j), (side * .731, y + .044 + j * .049, .719), (.021, .031, .004), mats['trim'], collection, lod, radius=.001), pivot)
        attach(geo.box('LOD0_InnerPull_' + suffix, (side * .785, y + (.165 if suffix.startswith('R') else .218), .850), (.036, .129, .036), mats['alloy'], collection, lod, radius=.011), pivot)
        attach(geo.ellipsoid('LOD0_DoorSpeaker_' + suffix, (side * .786, y + (.129 if suffix.startswith('R') else .214), .483), (.017, .187, .143), mats['trim'], collection, lod, 20, 10), pivot)
        attach(geo.box('LOD0_DoorPocket_' + suffix, (side * .777, y + (.040 if suffix.startswith('R') else -.035), .414), (.061, .23 if suffix.startswith('R') else .32, .073), mats['fabric'], collection, lod, radius=.016), pivot)
    # Preserve the four existing outboard buckle/release assemblies exactly.
    for side in (-1, 1):
        for row in ('Front', 'Rear'):
            bx = side * .148
            by = -.318 if row == 'Front' else -1.23
            geo.box('LOD0_' + row + 'BeltBuckle_' + str(side), (bx, by, .496), (.037, .047, .073), mats['trim'], collection, lod, radius=.005)
            geo.box('LOD0_' + row + 'BeltRelease_' + str(side), (bx, by, .534), (.026, .033, .003), mats['brake'], collection, lod, radius=.0006)
    restraints.build(collection, lod, mats, spec)


def build(collection, lod, mats, pivots, spec):
    structure(collection, lod, mats)
    for row, y in (('Front', -.18), ('Rear', -1.10)):
        for side, x in (('L', -.43), ('R', .43)):
            seat(collection, lod, mats, row + side, x, y, row == 'Rear')
    geo.box('LOD0_RearCenterCushion', (0, -1.107, .451), (.36, .481, .116), mats['leather'], collection, lod, radius=.024)
    geo.box('LOD0_RearCenterBack', (0, -1.31, .787), (.349, .144, .587), mats['leather'], collection, lod, radius=.024)
    geo.box('LOD0_RearCenterHeadrest', (0, -1.371, 1.142), (.234, .125, .157), mats['leather'], collection, lod, radius=.031)
    dashboard(collection, lod, mats, pivots, spec)
    moving_controls(collection, lod, mats, pivots)
    doors_and_belts(collection, lod, mats, pivots, spec)
