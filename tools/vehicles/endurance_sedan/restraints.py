"""Original static stowed restraints, with editable ribbons and finite rail mounts.

Nominal coordinates and provenance are locked by specification revision17.
This geometry does not simulate occupants, textile dynamics or crash loads.
"""
import math
from mathutils import Vector, Matrix
from . import geometry as geo


def build(collection, lod, mats, spec):
    contract = spec['original_packaging']['restraints_revision17']
    if (contract['web_width_m'], contract['buckle_branch_width_m'], contract['closed_web_thickness_m']) != (.045, .025, .004):
        raise ValueError('Restraint recipe and locked specification differ')
    made = {}
    trim, fabric, metal, red = mats['trim'], mats['fabric'], mats['metal'], mats['brake']

    def mesh(name, vertices, faces, material):
        obj = geo.mesh(name, vertices, faces, material, collection, lod)
        obj['construction_role'] = 'static stowed restraint assembly'
        made[name] = obj
        return obj

    def box(name, center, size, material, radius=0, basis=None):
        center = Vector(center)
        basis = basis or Matrix.Identity(3)
        coordinates = [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                       (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]
        vertices = [center + basis @ Vector(tuple(p[i]*size[i]/2 for i in range(3))) for p in coordinates]
        obj = mesh(name, vertices, [(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)], material)
        if radius:
            modifier = obj.modifiers.new('One segment small hardware bevel', 'BEVEL')
            modifier.width = min(radius, min(size)*.4)
            modifier.segments = 1
            modifier.limit_method = 'ANGLE'
            modifier.angle_limit = .45
        return obj

    def web(name, path, width=.045):
        points = [Vector(point) for point in path]
        normals = []
        for a, b in zip(points, points[1:]):
            tangent = (b-a).normalized()
            assert abs(tangent.x) < 1e-7
            normals.append(Vector((0, -tangent.z, tangent.y)))
        rings = []
        for index, point in enumerate(points):
            if index == 0:
                normal = normals[0]
            elif index == len(points)-1:
                normal = normals[-1]
            else:
                normal = (normals[index-1]+normals[index]).normalized()
                normal /= normal.dot(normals[index])
            rings += [point + Vector((sx*width/2, 0, 0)) + sy*.002*normal for sx, sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        faces = []
        for index in range(len(points)-1):
            for side in range(4):
                nxt = (side+1)%4
                faces.append((index*4+side,index*4+nxt,(index+1)*4+nxt,(index+1)*4+side))
        faces += [(3,2,1,0),tuple(range((len(points)-1)*4,len(points)*4))]
        return mesh(name, rings, faces, fabric)

    def clamp(name, x, y, z, width):
        # Actual rectangular throat seats the two web faces and both selvedges.
        outer = [(x-width/2-.004,y-.006),(x+width/2+.004,y-.006),
                 (x+width/2+.004,y+.006),(x-width/2-.004,y+.006)]
        inner = [(x-width/2,y-.002),(x+width/2,y-.002),(x+width/2,y+.002),(x-width/2,y+.002)]
        vertices = [(a,b,c) for c in (z,z+.028) for a,b in outer+inner]
        faces = []
        for i in range(4):
            j=(i+1)%4
            faces += [(i,j,j+8,i+8),(i+4,i+12,j+12,j+4),
                      (i,i+4,j+4,j),(i+8,j+8,j+12,i+12)]
        return mesh(name,vertices,faces,metal)

    paths = {}
    for side in (-1,1):
        suffix = str(side)
        paths[suffix] = [(side*.704,-1.499,1.21),(side*.704,-1.38,1.00),
                         (side*.704,-1.02,.52),(side*.704,-.88,.37),(side*.704,-.88,.325)]
        web('LOD0_RearBeltWeb_'+suffix,paths[suffix])
        box('LOD0_RearBeltGuide_'+suffix,(side*.704,-1.495,1.208),(.053,.019,.038),trim,.004)
        # Existing outboard buckle/release meshes remain untouched.
        a,b = Vector(paths[suffix][1]),Vector(paths[suffix][2])
        tangent = (b-a).normalized(); normal = Vector((0,-tangent.z,tangent.y))
        point = a+(b-a)*((1.-.65)/(1.-.52))
        basis = Matrix((Vector((1,0,0)),normal,-tangent)).transposed()
        box('LOD0_RearBeltTongue_'+suffix,point+normal*.005,(.037,.006,.045),metal,.004,basis)
        box('LOD0_RearBeltLowerPlate_'+suffix,(side*.6575,-.88,.321),(.145,.035,.008),metal)
        clamp('LOD0_RearBeltLowerClamp_'+suffix,side*.704,-.88,.325,.045)

    def framed_web(name, sections, width):
        rings=[]
        for point, across, normal in sections:
            p=Vector(point); a=Vector(across).normalized(); n=Vector(normal)
            rings += [p+sx*width/2*a+sy*.002*n for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        faces=[]
        for index in range(len(sections)-1):
            for side in range(4):
                j=(side+1)%4
                faces.append((index*4+side,index*4+j,(index+1)*4+j,(index+1)*4+side))
        faces += [(3,2,1,0),tuple(range((len(sections)-1)*4,len(sections)*4))]
        return mesh(name,rings,faces,fabric)

    def side_clamp(name, x, y, z, width):
        # Width follows Y; 4 mm cloth occupies the 12.5 mm seat partition gap.
        outer=[(x-.003,y-width/2-.004),(x+.003,y-width/2-.004),
               (x+.003,y+width/2+.004),(x-.003,y+width/2+.004)]
        inner=[(x-.002,y-width/2),(x+.002,y-width/2),
               (x+.002,y+width/2),(x-.002,y+width/2)]
        vertices=[(a,b,c) for c in (z,z+.028) for a,b in outer+inner]
        faces=[]
        for i in range(4):
            j=(i+1)%4
            faces += [(i,j,j+8,i+8),(i+4,i+12,j+12,j+4),
                      (i,i+4,j+4,j),(i+8,j+8,j+12,i+12)]
        return mesh(name,vertices,faces,metal)

    for side in (-1,1):
        suffix=str(side)
        top=Vector((side*.696,-.622,1.155)); bottom=Vector((side*.737,-.622,.44))
        tangent=(bottom-top).normalized(); across=Vector((-tangent.z,0,tangent.x))
        normal=Vector((0,1,0))
        framed_web('LOD0_FrontBeltWeb_'+suffix,
            [(tuple(top),tuple(across),(0,1,0)),(tuple(bottom),tuple(across),(0,1,0))],.045)
        box('LOD0_FrontBeltGuide_'+suffix,(side*.696,-.614,1.155),(.053,.019,.038),trim,.008)
        box('LOD0_FrontBeltLowerGuide_'+suffix,(side*.737,-.614,.44),(.053,.019,.038),metal,.004)
        point=top+(bottom-top)*((1.155-.626)/(1.155-.44))
        basis=Matrix((across,normal,-tangent)).transposed()
        box('LOD0_FrontBeltTongue_'+suffix,point-normal*.005,(.037,.006,.045),metal,.004,basis)
        paths['front_'+suffix]=[tuple(top),tuple(bottom)]

    # The center restraint lies in front of the back, across the empty cushion,
    # then folds into the existing gap. It never descends into the tunnel/chase.
    upper=[Vector((.10,-1.224,1.025)),Vector((.10,-1.234,.555)),Vector((.10,-1.21,.516))]
    t0=(upper[1]-upper[0]).normalized(); t1=(upper[2]-upper[1]).normalized()
    n0=Vector((0,-t0.z,t0.y)); n1=Vector((0,-t1.z,t1.y))
    corner=(n0+n1).normalized(); corner/=corner.dot(n1)
    center_sections=[(tuple(upper[0]),(1,0,0),tuple(n0)),
        (tuple(upper[1]),(1,0,0),tuple(corner)),
        (tuple(upper[2]),(1,0,0),(0,0,1)),
        ((.115,-1.14,.516),(1,0,0),(0,0,1)),
        ((.155,-1.10,.516),(1,-1,0),(0,0,1)),
        ((.178,-1.075,.516),(0,-1,0),(0,0,1)),
        ((.186,-1.075,.516),(0,-1,0),(1,0,1)),
        ((.186,-1.075,.343),(0,-1,0),(1,0,0))]
    framed_web('LOD0_RearCenterBelt',center_sections,.045)
    box('LOD0_RearCenterBeltGuide',(.10,-1.2285,1.025),(.053,.019,.038),trim,.008)
    a,b=upper[:2]; tangent=(b-a).normalized(); normal=Vector((0,-tangent.z,tangent.y))
    point=a+(b-a)*((1.025-.72)/(1.025-.555))
    basis=Matrix((Vector((1,0,0)),normal,-tangent)).transposed()
    box('LOD0_RearCenterBeltTongue',point+normal*.005,(.037,.006,.045),metal,.004,basis)
    branch_sections=[((-.10,-.9435,.511),(1,0,0),(0,0,1)),
        ((-.10,-1.035,.511),(1,0,0),(0,0,1)),
        ((-.12,-1.07,.516),(1,-1,0),(0,0,1)),
        ((-.155,-1.075,.516),(0,-1,0),(0,0,1)),
        ((-.186,-1.075,.516),(0,-1,0),(-1,0,1)),
        ((-.186,-1.075,.343),(0,-1,0),(-1,0,0))]
    framed_web('LOD0_RearCenterBuckleWeb',branch_sections,.025)
    rotation=Matrix.Rotation(-math.pi/2,3,'X')
    box('LOD0_RearCenterBeltBuckle',(-.10,-.98,.5365),(.037,.047,.073),trim,.005,rotation)
    box('LOD0_RearCenterBeltRelease',(-.10,-.942,.5365),(.026,.033,.003),red,.0006,rotation)
    # Separate short metal anchors attach to existing rear rail bases without
    # crossing the center tunnel or penetrating any seat foam or shell.
    for side, width, label in ((1,.045,'Belt'),(-1,.025,'Buckle')):
        box('LOD0_RearCenter'+label+'LowerPlate',(side*.224,-1.075,.337),(.086,.065,.012),metal)
        side_clamp('LOD0_RearCenter'+label+'LowerClamp',side*.186,-1.075,.343,width)
    return {'objects':made,'paths':{**paths,
        'center_sections':center_sections,'buckle_sections':branch_sections}}
