"""Original nineteen-inch wheels, tires and layered ventilated brakes."""

import math

from . import geometry as geo
from . import tire_surface


def sector(name, parent, collection, material, center_x, thickness, inner, outer, start=-98, end=-42, bevel_segments=2):
    # Eight arc segments over56 degrees keep the maximum circular chord
    # error below0.412mm at the largest 220.5 mm radius. Endpoints/radii stay
    # fixed; this reserves geometry for actual panel seats and body joints.
    angles = [math.radians(start + (end - start) * i / 8) for i in range(9)]
    outline = [(outer * math.sin(a), outer * math.cos(a)) for a in angles]
    outline += [(inner * math.sin(a), inner * math.cos(a)) for a in reversed(angles)]
    obj = geo.prism_x(name, outline, center_x - thickness / 2, center_x + thickness / 2, material, collection, parent)
    geo.bevel(obj, .002, bevel_segments)
    return obj


def build(collection, mats, pivots, spec):
    radius = spec['geometry']['wheel_radius_m']
    half = spec['geometry']['tire_width_m'] / 2
    radial = spec['original_packaging']['wheel_tessellation_revision22']
    detail = spec['original_packaging']['primitive_detail_revision24']
    if (detail['brake_hat_segments'], detail['caliper_bevel_segments']) != (24, 1):
        raise ValueError('Brake detail needs a new measured construction revision')
    if tuple(radial[key] for key in ('tire_segments', 'rim_barrel_segments', 'friction_face_segments')) != (60, 36, 36):
        raise ValueError('Wheel tessellation needs a new measured construction revision')
    profile = [(-half + .017, .2413), (-half + .004, .262), (-half, .287),
               (-half + .004, .311), (-half + .013, .328), (-half + .028, radius)]
    for offset in (-.068, -.023, .023, .068):
        profile.extend([(offset - .0030, radius), (offset - .0020, radius - .004),
                        (offset + .0020, radius - .004), (offset + .0030, radius)])
    profile.extend([(half - .028, radius), (half - .013, .328), (half - .004, .311),
               (half, .287), (half - .004, .262), (half - .017, .2413)]
    )
    for suffix in ('FL', 'FR', 'RL', 'RR'):
        wheel = pivots['Wheel_' + suffix]
        suspension = pivots['Suspension_' + suffix]
        side = -1 if suffix.endswith('L') else 1
        tire = geo.ring_x('LOD0_Tire_' + suffix, profile, (0, 0, 0), mats['rubber'], collection, wheel, radial['tire_segments'])
        tire['clearance_role'] = 'tire'
        # Four4mm channels are part of the actual tire profile. Temporary
        # guides reproduce the locked native shoulder field, then are removed
        # after subtracting the genuine recessed shoulder cuts.
        construction_guides=[]
        for j in range(28):
            a = j * math.tau / 28
            for sign in (-1, 1):
                points=[]
                # The pre-shoulder segment is almost straight over16.5 mm;
                # its redundant middle sample costs1,792 triangles per car.
                for x in (.083,.0995,.106,.110):
                    t=(x-.083)/.027
                    shoulder_radius=radius if x<=half-.028 else radius+(.328-radius)*(x-(half-.028))/.015
                    points.append((sign*x,(shoulder_radius-.0003)*math.sin(a+t*.026),(shoulder_radius-.0003)*math.cos(a+t*.026)))
                sipe=geo.tube('LOD0_ShoulderSipe_' + suffix + f'_{j}_{sign}', points, .0007, mats['trim'], collection, wheel, sides=4)
                construction_guides.append(sipe)
        tire_surface.cut_shoulders(tire, construction_guides)
        rim_profile = [(-.108, .227), (-.108, .2445), (-.100, .247), (-.094, .242),
                       (.094, .242), (.100, .247), (.108, .2445), (.108, .227)]
        geo.ring_x('LOD0_RimBarrel_' + suffix, rim_profile, (0, 0, 0), mats['wheel'], collection, wheel, radial['rim_barrel_segments'])
        for j in range(10):
            angle = j * math.tau / 10
            # Tapered, slightly swept forged spokes; broad roots, slimmer tips.
            points = [(side * .087, .061 * math.sin(angle), .061 * math.cos(angle)),
                      (side * .090, .148 * math.sin(angle + .045), .148 * math.cos(angle + .045)),
                      (side * .099, .229 * math.sin(angle + .055), .229 * math.cos(angle + .055))]
            geo.tube('LOD0_ForgedSpoke_' + suffix + '_' + str(j), points, [.017, .013, .009], mats['wheel'], collection, wheel, sides=6)
        geo.tube('LOD0_WheelHub_' + suffix, [(side * .098 - .009, 0, 0), (side * .098 + .009, 0, 0)], .067, mats['wheel'], collection, wheel, sides=32)
        for j in range(5):
            a = j * math.tau / 5
            y, z = .049 * math.sin(a), .049 * math.cos(a)
            geo.tube('LOD0_LugBolt_' + suffix + '_' + str(j), [(side * .105, y, z), (side * .115, y, z)], .0075, mats['metal'], collection, wheel, sides=6)
        geo.tube('LOD0_ValveStem_' + suffix, [(side * .100, .180, .110), (side * .118, .180, .110)], .0035, mats['rubber'], collection, wheel, sides=8)
        r = .1995 if suffix.startswith('F') else .178
        thickness = .036 if suffix.startswith('F') else .022
        disk_center = side * .025
        # Separate friction faces leave a visible ventilation gap.
        face_thickness = .009 if suffix.startswith('F') else .006
        for face_side in (-1, 1):
            offset = disk_center + face_side * (thickness - face_thickness) / 2
            geo.ring_x('LOD0_BrakeFace_' + suffix + str(face_side), [(-face_thickness / 2, .104), (-face_thickness / 2, r),
                       (face_thickness / 2, r), (face_thickness / 2, .104)], (offset, 0, 0), mats['metal'], collection, wheel, radial['friction_face_segments'])
        geo.ring_x('LOD0_BrakeHat_' + suffix, [(-.018, .043), (-.018, .106), (.018, .106), (.018, .043)], (disk_center, 0, 0), mats['alloy'], collection, wheel, detail['brake_hat_segments'])
        for j in range(30):
            a = j * math.tau / 30
            y0,z0=.111*math.sin(a),.111*math.cos(a)
            y1,z1=(r-.005)*math.sin(a+.10),(r-.005)*math.cos(a+.10)
            dy,dz=y1-y0,z1-z0
            length=math.hypot(dy,dz)
            ny,nz=-dz/length*.0023,dy/length*.0023
            vane=geo.prism_x('LOD0_RotorVane_'+suffix+'_'+str(j),[(y0+ny,z0+nz),(y1+ny,z1+nz),(y1-ny,z1-nz),(y0-ny,z0-nz)],disk_center-thickness/2+face_thickness,disk_center+thickness/2-face_thickness,mats['metal'],collection,wheel)
            vane['maximum_lod']=1
        for face_side in (-1, 1):
            x = disk_center + face_side * (thickness / 2 + .010)
            sector('LOD0_CaliperCheek_' + suffix + str(face_side), suspension, collection, mats['caliper'], x, .013, r - .036, r + .020, bevel_segments=detail['caliper_bevel_segments'])
        sector('LOD0_CaliperBridge_' + suffix, suspension, collection, mats['caliper'], disk_center, thickness + .024, r + .006, r + .021, bevel_segments=detail['caliper_bevel_segments'])
