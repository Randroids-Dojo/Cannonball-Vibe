"""Inspectable V8/AWD/endurance packaging. Geometry, not a mechanical simulator."""

import math

import bpy
from mathutils import Euler, Vector

from . import geometry as geo
from . import model
from .exterior import attach, cut_box


def engine(collection, lod, mats, pivots, spec):
    detail = spec['original_packaging']['primitive_detail_revision24']
    if (detail['fan_shroud_path_segments'], detail['turbo_segments'], detail['turbo_rings'],
        detail['cooler_fin_long_edge_chamfer_m'], detail['cooler_fin_end_edge_chamfer_m']) != (24, 20, 10, .0007, 0):
        raise ValueError('Cooling hardware detail needs a new measured construction revision')
    geo.box('LOD0_V8Crankcase', (0, 1.393, .491), (.451, .698, .341), mats['alloy'], collection, lod, radius=.028)
    geo.box('LOD0_Sump', (0, 1.442, .318), (.422, .512, .061), mats['alloy'], collection, lod, radius=.016)
    for side in (-1, 1):
        geo.box('LOD0_V8CylinderBank_' + str(side), (side * .219, 1.390, .656), (.265, .693, .229), mats['alloy'], collection, lod, radius=.019, rotation=Euler((0, side * math.radians(31), 0)))
        geo.box('LOD0_CamCover_' + str(side), (side * .257, 1.394, .778), (.233, .673, .052), mats['trim'], collection, lod, radius=.017, rotation=Euler((0, side * math.radians(31), 0)))
        for j in range(4):
            y = 1.145 + j * .157
            geo.box('LOD0_CoilPack_' + str(side) + str(j), (side * .263, y, .813), (.087, .064, .024), mats['trim'], collection, lod, radius=.006)
        # Two turbo housings occupy the hot V; shield and charge pipes are visible.
        geo.ellipsoid('LOD0_HotVTurbo_' + str(side), (side * .111, 1.274, .811), (.145, .181, .137), mats['metal'], collection, lod, detail['turbo_segments'], detail['turbo_rings'])
        geo.tube('LOD0_TurboIntake_' + str(side), [(side * .111, 1.321, .819), (side * .29, 1.626, .839), (side * .48, 1.867, .79)], .034, mats['rubber'], collection, lod, sides=12)
        geo.box('LOD0_Airbox_' + str(side), (side * .48, 1.867, .770), (.220, .210, .180), mats['trim'], collection, lod, radius=.022)
        for j in range(5):
            rib=geo.box('LOD0_AirboxRib_' + str(side) + str(j), (side * .48, 1.79 + j * .039, .860), (.196, .008, .004), mats['trim'], collection, lod, radius=.001)
            rib.modifiers[0].segments=1
        geo.box('LOD0_WaterToAirChargeCooler_'+str(side),(side*.130,1.688,.810),(.230,.260,.140),mats['alloy'],collection,lod,radius=.012)
        geo.tube('LOD0_HotChargePipe_'+str(side),[(side*.101,1.28,.817),(side*.107,1.495,.839),(side*.130,1.561,.817)],.030,mats['alloy'],collection,lod,sides=12)
        geo.tube('LOD0_ColdChargePipe_'+str(side),[(side*.240,1.673,.811),(side*.365,1.576,.748),(side*.355,1.418,.744)],.028,mats['alloy'],collection,lod,sides=12)
        geo.box('LOD0_IntakePlenum_'+str(side),(side*.354,1.463,.716),(.105,.403,.120),mats['trim'],collection,lod,radius=.016)
        geo.tube('LOD0_ChargeCoolantHose_'+str(side),[(side*.204,1.71,.756),(side*.378,1.935,.687),(side*.485,2.081,.55)],.012,mats['rubber'],collection,lod,sides=10)
        geo.tube('LOD0_Downpipe_' + str(side), [(side * .090, 1.238, .795), (side * .290, 1.08, .620), (side * .280, .941, .390), (side * .117, .23, .220)], .034, mats['metal'], collection, lod, sides=12)
        geo.box('LOD0_StrutTower_' + str(side), (side * .530, 1.390, .840), (.180, .275, .160), mats['paint'], collection, lod, radius=.030)
        geo.tube('LOD0_StrutTop_' + str(side), [(side * .535, 1.445, .914), (side * .535, 1.445, .930)], .062, mats['metal'], collection, lod, sides=24)
        for j in range(3):
            a = j * math.tau / 3
            geo.tube('LOD0_StrutNut_' + str(side) + str(j), [(side * .535 + .048 * math.cos(a), 1.445 + .048 * math.sin(a), .931),
                         (side * .535 + .048 * math.cos(a), 1.445 + .048 * math.sin(a), .937)], .006, mats['metal'], collection, lod, sides=6)
        geo.tube('LOD0_EngineHarness_' + str(side), [(side * .333, 1.093, .810), (side * .345, 1.4, .829), (side * .357, 1.701, .798)], .008, mats['rubber'], collection, lod, sides=6)
    geo.box('LOD0_ValleyHeatShield', (0, 1.397, .856), (.203, .327, .017), mats['alloy'], collection, lod, radius=.006)
    geo.box('LOD0_RadiatorStack', (0, 2.035, .535), (1.245, .080, .422), mats['metal'], collection, lod, radius=.008)
    geo.box('LOD0_ChargeCoolingRadiator', (0, 2.107, .464), (1.056, .069, .221), mats['alloy'], collection, lod, radius=.009)
    for i in range(36):
        # Retain all long-edge chamfers; the concealed ends use planar caps.
        cx,cy,cz=-.505+i*.0289,2.144,.464
        hx,hy,chamfer=.003,.002,detail['cooler_fin_long_edge_chamfer_m']
        ring=[(-hx+chamfer,-hy),(hx-chamfer,-hy),(hx,-hy+chamfer),(hx,hy-chamfer),
              (hx-chamfer,hy),(-hx+chamfer,hy),(-hx,hy-chamfer),(-hx,-hy+chamfer)]
        vertices=[(cx+x,cy+y,cz+sign*.201/2) for sign in (-1,1) for x,y in ring]
        faces=[tuple(reversed(range(8))),tuple(range(8,16))]+[(j,(j+1)%8,(j+1)%8+8,j+8) for j in range(8)]
        geo.mesh('LOD0_CoolerFin_'+str(i),vertices,faces,mats['metal'],collection,lod)
    for side in (-1, 1):
        segments=detail['fan_shroud_path_segments']
        points = [(side * .277 + .153 * math.cos(i * math.tau / segments), 1.973, .583 + .153 * math.sin(i * math.tau / segments)) for i in range(segments)]
        geo.tube('LOD0_FanShroud_' + str(side), points, .014, mats['trim'], collection, lod, sides=6, closed=True)
        for j in range(7):
            a = j * math.tau / 7
            geo.tube('LOD0_FanBlade_' + str(side) + str(j), [(side * .277 + .036 * math.cos(a), 1.974, .583 + .036 * math.sin(a)),
                     (side * .277 + .143 * math.cos(a + .16), 1.974, .583 + .143 * math.sin(a + .16))], .012, mats['trim'], collection, lod, sides=4)
    geo.box('LOD0_ExpansionTank', (-.624, 1.025, .734), (.166, .186, .193), mats['alloy'], collection, lod, radius=.029)
    geo.tube('LOD0_CoolantCap', [(-.624, 1.025, .830), (-.624, 1.025, .847)], .027, mats['trim'], collection, lod, sides=16)
    geo.box('LOD0_FuseBox', (.585, 1.007, .740), (.232, .184, .134), mats['trim'], collection, lod, radius=.014)
    geo.tube('LOD0_CoolantHose', [(-.559, 1.107, .698), (-.439, 1.817, .575), (-.491, 2.007, .518)], .017, mats['rubber'], collection, lod, sides=10)
    geo.tube('LOD0_FrontStrutBrace', [(-.535, 1.455, .919), (-.354, .933, .917), (.354, .933, .917), (.535, 1.455, .919)], .010, mats['wheel'], collection, lod, sides=8)


def underside(body, collection, lod, mats):
    cut_box(body, 'DrivelineTunnelVoid', (0, -.10, .226), (.49, 2.38, .283), collection)
    for side in (-1, 1):
        tray=geo.box('LOD0_FrontUndertray_' + str(side), (side * .461, 1.568, .166), (.61, 1.39, .018), mats['trim'], collection, lod, radius=0)
        cutter=geo.tube('FrontTrayWheelCut',[(side*.46,1.46,.3433),(side*1.15,1.46,.3433)],.4483,None,collection,sides=64)
        geo.boolean(tray,cutter);model.remove(cutter);geo.bevel(tray,.002,2)
        geo.box('LOD0_CabinUndertray_' + str(side), (side * .446, -.271, .13745), (.386, 1.72, .0049), mats['trim'], collection, lod, radius=.001)
        geo.tube('LOD0_LongitudinalRail_' + str(side), [(side * .64, 1.014, .225), (side * .64, -1.34, .219), (side * .568, -1.65, .282)], .025, mats['paint'], collection, lod, sides=6)
        geo.tube('LOD0_ExhaustMidPipe_' + str(side), [(side * .117, .25, .220), (side * .117, -.665, .215), (side * .117, -1.340, .240), (side * .51, -1.720, .306), (side * .60, -2.035, .292)], .030, mats['metal'], collection, lod, sides=12)
        geo.box('LOD0_RearMuffler_' + str(side), (side * .591, -2.083, .313), (.291, .413, .149), mats['metal'], collection, lod, radius=.041)
        geo.tube('LOD0_RearMufflerOutlet_' + str(side), [(side * .591, -2.230, .313), (side * .648, -2.439, .312)], .032, mats['metal'], collection, lod, sides=12)
    geo.box('LOD0_TunnelHeatShield', (0, -.129, .274), (.409, 1.53, .009), mats['alloy'], collection, lod, radius=.003)
    geo.box('LOD0_CentralResonator', (0, -.640, .217), (.361, .332, .089), mats['metal'], collection, lod, radius=.026)
    geo.box('LOD0_TunnelBrace', (0, .140, .178), (.644, .095, .023), mats['wheel'], collection, lod, radius=.006)
    geo.ellipsoid('LOD0_SevenSpeedTransaxle', (0, .567, .346), (.363, .643, .309), mats['alloy'], collection, lod, 24, 12)
    geo.ellipsoid('LOD0_DctBellhousing',(0,.941,.399),(.410,.265,.310),mats['alloy'],collection,lod,24,12)
    geo.tube('LOD0_PropShaft', [(0, .223, .319), (0, -1.415, .347)], .031, mats['metal'], collection, lod, sides=12)
    geo.ellipsoid('LOD0_RearDifferential', (0, -1.46, .353), (.323, .277, .242), mats['alloy'], collection, lod, 20, 10)
    final_drive=geo.ellipsoid('LOD0_FrontFinalDrive',(0,1.46,.301),(.27,.25,.178),mats['alloy'],collection,lod,24,12)
    cut_box(body,'FrontFinalDriveUnderfloorPocket',(0,1.46,.244),(.300,.300,.300),collection)
    for casing in ('LOD0_Sump','LOD0_V8Crankcase'):
        # Real mating recesses remove overlapping casing volume. The final
        # drive remains independently editable with a shared bolted interface.
        geo.boolean(bpy.data.objects[casing],final_drive)
        bpy.data.objects[casing]['mating_interface']='Shaped zero-interpenetration recess for LOD0_FrontFinalDrive'
    final_drive['mating_interface']='Removable original front final-drive case seated in shaped sump/crankcase recess'
    geo.tube('LOD0_ForwardReturnDrive',[(.196,.84,.32),(.25,1.13,.295),(.125,1.46,.301)],.025,mats['alloy'],collection,lod,sides=12)
    for y, axle in ((1.46, 'F'), (-1.46, 'R')):
        geo.tube('LOD0_' + axle + 'Subframe', [(-.455, y - .169, .305), (-.38, y + .163, .313), (.38, y + .163, .313), (.455, y - .169, .305)], .024, mats['wheel'], collection, lod, sides=6)
        for side in (-1, 1):
            geo.tube('LOD0_' + axle + 'HalfShaft_' + str(side), [(side * .116, y, .35), (side * .744, y, .343)], .020, mats['metal'], collection, lod, sides=10)
            for anchor_y in (y - .19, y + .17):
                geo.tube('LOD0_' + axle + 'LowerLink_' + str(side) + str(anchor_y), [(side * .356, anchor_y, .265), (side * .535, y, .292)], .016, mats['alloy'], collection, lod, sides=8)
            geo.tube('LOD0_' + axle + 'Damper_' + str(side), [(side * .535, y, .356), (side * .510, y - .016, .816)], .022, mats['metal'], collection, lod, sides=12)


def trunk(body, collection, lod, mats, pivots):
    geo.box('LOD0_TrunkCarpet', (0, -2.157, .306), (1.476, .580, .023), mats['carpet'], collection, lod, radius=.007)
    geo.box('LOD0_AuxiliaryTank', (0, -1.92, .56), (.90, .48, .28), mats['alloy'], collection, lod, radius=.016)
    for x in (-.313, .313):
        geo.box('LOD0_TankStrap_' + str(x), (x, -1.92, .7041), (.035, .491, .006), mats['wheel'], collection, lod, radius=.001)
        geo.tube('LOD0_TankStrapReturn_' + str(x), [(x, -2.171, .702), (x, -2.171, .409), (x, -1.669, .409), (x, -1.669, .702)], .008, mats['wheel'], collection, lod, sides=4)
    # Original two-lobe main reservoir straddles the .49 m exhaust tunnel.
    # Gross volume is measured after rounding; nominal usable capacity is75 L.
    for side in (-1,1):
        center=(side*.428,-.60,.188)
        cut_box(body,'MainTankBodyPocket_'+str(side),(center[0],center[1],.180),(.376,1.352,.132),collection)
        tank=geo.box('LOD0_MainFuelLobe_'+str(side),center,(.364,1.34,.094),mats['trim'],collection,lod,radius=.010)
        wheel_space=geo.tube('ReservoirWheelTubClearance',[(side*.565,-1.46,.3433),(side*1.10,-1.46,.3433)],.462,None,collection,sides=64)
        geo.boolean(tank,wheel_space);model.remove(wheel_space)
        tank['nominal_pair_capacity_l']=75.0
        tank['assembly']='Original paired main reservoir; shared usable75 L, not each'
        crossover=geo.tube('LOD0_MainTankCrossover_'+str(side),[(side*.27,-.745,.235),(side*.265,-.745,.421),(side*.10,-.745,.421)],.009,mats['rubber'],collection,lod,sides=10)
        crossover['assembly_boundary']='Finite coplanar butt seat at X side*.100; 9mm cap centered Y-.745/Z.421; connected meshes occupy opposing halfspaces'
    bridge=geo.tube('LOD0_MainTankCrossoverBridge',[(-.10,-.745,.421),(.10,-.745,.421)],.009,mats['rubber'],collection,lod,sides=10)
    bridge['assembly_boundary']='Two individually bounded 9mm coplanar end seats at X+/-.100; modeled plumbing, no transfer simulation'
    geo.tube('LOD0_AuxFillNeck', [(-.341, -1.94, .700), (-.501, -1.973, .781), (-.560, -2.03, .797),(-.560,-2.03,.824)], .022, mats['metal'], collection, lod, sides=12)
    geo.tube('LOD0_AuxFillerCollar',[(-.560,-2.03,.814),(-.560,-2.03,.832)],.028,mats['metal'],collection,lod,sides=16)
    geo.tube('LOD0_AuxFillerCap',[(-.560,-2.03,.832),(-.560,-2.03,.848)],.032,mats['trim'],collection,lod,sides=16)
    geo.box('LOD0_AuxFillerGrip',(-.560,-2.03,.852),(.043,.010,.010),mats['wheel'],collection,lod,radius=.002)
    vent=geo.tube('LOD0_AuxVent', [(.380, -1.87, .70), (.494, -1.945, .777), (.697, -2.155, .800),(.936,-2.155,.800)], .006, mats['rubber'], collection, lod, sides=8)
    vent['assembly_boundary']='Original vent path through seated quarter-panel union; modeled passive hardware only'
    vent_port=geo.tube('VentQuarterPassage',[(.775,-2.155,.800),(.961,-2.155,.800)],.011,None,collection,sides=16)
    geo.boolean(body,vent_port);model.remove(vent_port)
    geo.hollow_tube('LOD0_VentBulkheadUnion',(.788,-2.155,.800),(.808,-2.155,.800),.0097,.0017,mats['metal'],collection,lod,segments=12)
    flange=geo.hollow_tube('LOD0_VentBulkheadFlange',(.784,-2.155,.800),(.790,-2.155,.800),.016,.008,mats['metal'],collection,lod,segments=12)
    flange['contact_policy']='Interior flange seats on quarter-panel inner face X .790; shank radius9.7 mm in radius11 mm passage'
    geo.tube('LOD0_VentRolloverValve',[(.380,-1.87,.696),(.403,-1.880,.731)],.012,mats['metal'],collection,lod,sides=12)
    geo.tube('LOD0_VentExternalCover',[(.934,-2.155,.800),(.943,-2.155,.800)],.014,mats['trim'],collection,lod,sides=12)
    pump=geo.box('LOD0_TransferPump', (.527, -1.961, .460), (.095, .159, .09), mats['trim'], collection, lod, radius=.010)
    geo.tube('LOD0_TransferPumpInlet',[(.450,-1.920,.460),(.4795,-1.920,.460)],.008,mats['rubber'],collection,lod,sides=12)
    for x in (.451,.478):
        geo.tube('LOD0_PumpInletUnion_'+str(x),[(x-.003,-1.920,.460),(x+.003,-1.920,.460)],.012,mats['metal'],collection,lod,sides=8)
    line_points=[(.49,-1.99,.460),(.47,-1.99,.400),(.401333333,-1.997333333,.364),
                 (.35,-1.99,.210),(.35,-1.36,.210),(.43,-1.27,.210)]
    bore_start=Vector(line_points[0]);bore_end=Vector(line_points[1])
    bore_start-=(bore_end-bore_start).normalized()*.012
    outlet_bore=geo.tube('TransferPumpOutletBore',[bore_start,bore_end],.0075,None,collection,sides=12)
    geo.boolean(pump,outlet_bore);model.remove(outlet_bore)
    geo.tube('LOD0_FuelTransferLine',line_points,.006,mats['rubber'],collection,lod,sides=8)
    # A sealed bulkhead fitting provides the required real passage through the
    # trunk floor, rather than pretending a pipe can pass through solid carpet.
    floor_port=geo.tube('FuelBulkheadPassage',[(.43,-2.001428571,.450),(.336666667,-1.988095238,.170)],.018,None,collection,sides=24)
    geo.boolean(body,floor_port)
    geo.boolean(bpy.data.objects['LOD0_TrunkCarpet'],floor_port);model.remove(floor_port)
    underfloor_chase=geo.tube('TransferLineBodyPassage',[(.35,-2.015,.210),(.35,-1.36,.210),(.43,-1.27,.210),(.46,-1.235,.210)],.014,None,collection,sides=16)
    geo.boolean(body,underfloor_chase);model.remove(underfloor_chase)
    gland=geo.hollow_tube('LOD0_FuelBulkheadGland',(.387333333,-1.995333333,.322),(.376666667,-1.993809524,.290),.019,.010,mats['rubber'],collection,lod,segments=16)
    gland['contact_policy']='Compressible rubber floor gland:19 mm outer radius in18 mm bore; nominal1 mm radial seating interference only; not a rigid-part exception'
    geo.box('LOD0_RearBattery', (-.577, -2.129, .432), (.213, .258, .213), mats['trim'], collection, lod, radius=.011)
    geo.box('LOD0_BatteryClamp', (-.577, -2.129, .543), (.035, .277, .008), mats['wheel'], collection, lod, radius=.002)
    geo.box('LOD0_EnduranceToolBag', (.325, -2.325, .418), (.479, .198, .179), mats['fabric'], collection, lod, radius=.039)
    geo.tube('LOD0_ToolBagHandle', [(.244, -2.325, .51), (.261, -2.325, .545), (.387, -2.325, .545), (.404, -2.325, .51)], .007, mats['fabric'], collection, lod, sides=6)
    geo.box('LOD0_LuggageBulkheadCover', (0, -1.531, .736), (1.331, .022, .253), mats['carpet'], collection, lod, radius=.006)
    # Secured under the front passenger seat, outside both footwell envelopes.
    geo.tube('LOD0_FireExtinguisher', [(.43, -.304, .306), (.43, -.033, .306)], .035, mats['wheel'], collection, lod, sides=24)
    for y in (-.262, -.085):
        geo.tube('LOD0_ExtinguisherStrap_' + str(y), [(.391, y, .278), (.394, y, .337), (.466, y, .337), (.469, y, .278)], .003, mats['metal'], collection, lod, sides=6)


def build(body, collection, lod, mats, pivots, spec):
    engine(collection, lod, mats, pivots, spec)
    underside(body, collection, lod, mats)
    trunk(body, collection, lod, mats, pivots)
