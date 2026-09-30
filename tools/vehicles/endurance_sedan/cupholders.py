"""Original hollow cup inserts and matching closed console pockets.

Reports-only candidate. At production adoption replace the old ellipsoid
cupholder loop with build(console, mats['rubber']) after console construction.
No source save/export, report-file input, new material or gameplay behavior.
"""
import math
import bpy
from . import geometry as geo
from .floor_panels import freeze
from .pillar_joints import normal_reference
from .surface_normals import mark_fold_edges,restore_owned

SEGMENTS=32
CENTER_Y=-.113
CENTER_X=.068
RECEIVING_INRADIUS=.040
WALL_THICKNESS=.0015
POCKET_CLEARANCE=.0012
LIP_OUTER_RADIUS=.044
LIP_THICKNESS=.002
LIP_CHAMFER=.0005
RECEIVING_DEPTH=.060
BOTTOM_THICKNESS=.003


def geometry(cx,top):
    factor=math.cos(math.pi/SEGMENTS)
    receiving=RECEIVING_INRADIUS/factor
    outside=(RECEIVING_INRADIUS+WALL_THICKNESS)/factor
    upper=top+LIP_THICKNESS
    floor=upper-RECEIVING_DEPTH
    bottom=floor-BOTTOM_THICKNESS
    profile=[(receiving,upper),(LIP_OUTER_RADIUS-LIP_CHAMFER,upper),
             (LIP_OUTER_RADIUS,upper-LIP_CHAMFER),(LIP_OUTER_RADIUS,top),
             (outside,top),(outside,bottom),(receiving,floor)]
    vertices=[(cx+r*math.cos(math.tau*i/SEGMENTS),CENTER_Y+r*math.sin(math.tau*i/SEGMENTS),z)
              for r,z in profile for i in range(SEGMENTS)]
    faces=[]
    for a,b in [(i,i+1) for i in range(5)]+[(6,0)]:
        for i in range(SEGMENTS):
            j=(i+1)%SEGMENTS
            faces.append((a*SEGMENTS+i,a*SEGMENTS+j,b*SEGMENTS+j,b*SEGMENTS+i))
    lower_center=len(vertices);vertices.append((cx,CENTER_Y,bottom))
    inner_center=len(vertices);vertices.append((cx,CENTER_Y,floor))
    for i in range(SEGMENTS):
        j=(i+1)%SEGMENTS
        faces.append((lower_center,5*SEGMENTS+i,5*SEGMENTS+j))
        faces.append((inner_center,6*SEGMENTS+j,6*SEGMENTS+i))
    return vertices,faces,{'center_source_xy_m':[cx,CENTER_Y],'segments':SEGMENTS,
        'receiving_inradius_m':RECEIVING_INRADIUS,'receiving_vertex_radius_m':receiving,
        'wall_inradius_m':RECEIVING_INRADIUS+WALL_THICKNESS,'wall_vertex_radius_m':outside,
        'console_top_z_m':top,'lip_top_z_m':upper,'receiving_floor_z_m':floor,'outer_bottom_z_m':bottom,
        'cavity_floor_z_m':bottom-POCKET_CLEARANCE,'receiving_depth_m':RECEIVING_DEPTH,
        'bottom_thickness_m':BOTTOM_THICKNESS,'lip_outer_radius_m':LIP_OUTER_RADIUS,
        'lip_chamfer_m':LIP_CHAMFER,'wall_thickness_m':WALL_THICKNESS,
        'pocket_inradius_m':RECEIVING_INRADIUS+WALL_THICKNESS+POCKET_CLEARANCE,
        'pocket_vertex_radius_m':(RECEIVING_INRADIUS+WALL_THICKNESS+POCKET_CLEARANCE)/factor,
        'pocket_side_bottom_clearance_m':POCKET_CLEARANCE,
        'finite_mount':'Only the flange underside contacts the original flat console top; the recessed wall and bottom have1.2mm nominal air clearance.'}


def build(console,rubber,profile):
    expected={'segments':SEGMENTS,'center_abs_x_m':CENTER_X,'center_y_m':CENTER_Y,
              'receiving_inradius_m':RECEIVING_INRADIUS,'wall_thickness_m':WALL_THICKNESS,
              'pocket_clearance_m':POCKET_CLEARANCE,'lip_outer_radius_m':LIP_OUTER_RADIUS,
              'lip_thickness_m':LIP_THICKNESS,'lip_chamfer_m':LIP_CHAMFER,
              'receiving_depth_m':RECEIVING_DEPTH,'bottom_thickness_m':BOTTOM_THICKNESS,
              'console_top_z_m':.586}
    if any(profile.get(key)!=value for key,value in expected.items()):
        raise ValueError('Cupholder specification needs a newly validated construction recipe')
    if console.name!='LOD0_CenterConsole' or console.type!='MESH':
        raise ValueError('Expected original CenterConsole mesh')
    names=['LOD0_Cupholder_'+str(side) for side in (-1,1)]
    if any(bpy.data.objects.get(name) for name in names):
        raise ValueError('Replace the old ellipsoid cupholder construction; do not stack or repeat it')
    bpy.context.view_layer.update()
    if any(abs(console.matrix_world[i][j]-(1 if i==j else 0))>1e-8 for i in range(4) for j in range(4)):
        raise ValueError('Cup pockets require the declared original source-meter frame')
    freeze(console)
    points=[tuple(v.co) for v in console.data.vertices]
    top=max(p[2] for p in points)
    if abs(top-.586)>1e-7:raise ValueError('Original console top height changed')
    top_points=[p for p in points if abs(p[2]-top)<1e-8]
    if min(p[0] for p in top_points)>-.1135+1e-7 or max(p[0] for p in top_points)<.1135-1e-7:
        raise ValueError('Original console flat seat is narrower than the declared envelope')
    collection=console.users_collection[0];parent=console.parent
    coating=console.data.materials[0]
    reference=normal_reference(console)
    proofs={};objects={}
    for side,name in zip((-1,1),names):
        vertices,faces,proof=geometry(side*CENTER_X,top)
        radius=proof['pocket_vertex_radius_m']
        z0,z1=proof['cavity_floor_z_m'],top+.020
        cut_points=[(side*CENTER_X+radius*math.cos(math.tau*i/SEGMENTS),CENTER_Y+radius*math.sin(math.tau*i/SEGMENTS),z)
                    for z in (z0,z1) for i in range(SEGMENTS)]
        cut_faces=[tuple(reversed(range(SEGMENTS))),tuple(range(SEGMENTS,2*SEGMENTS))]
        cut_faces += [(i,(i+1)%SEGMENTS,(i+1)%SEGMENTS+SEGMENTS,i+SEGMENTS) for i in range(SEGMENTS)]
        cutter=geo.mesh('PrivateCupPocketCut',cut_points,cut_faces,coating,collection,parent)
        try:geo.boolean(console,cutter)
        finally:
            data=cutter.data;bpy.data.objects.remove(cutter,do_unlink=True)
            if data.users==0:bpy.data.meshes.remove(data)
        cup=geo.mesh(name,vertices,faces,rubber,collection,parent,smooth=True)
        mark_fold_edges(cup)
        cup['assembly_boundary']='Closed molded insert, original40mm clear receiving radius,60mm depth and3mm bottom; flange seated on matching console pocket.'
        objects[name]=cup;proofs[name]=proof
    # Both pocket cutters use the existing console material. Preserve its one
    # material identity and original surface field; new pocket walls are real.
    for polygon in console.data.polygons:
        if console.data.materials[polygon.material_index]!=coating:
            raise ValueError('Unexpected console Boolean material')
    console.data.materials.clear();console.data.materials.append(coating)
    for polygon in console.data.polygons:polygon.material_index=0
    geo.repair_triangulation(console)
    console.data.normals_split_custom_set([tuple(face.normal) for face in console.data.polygons for _ in face.loop_indices])
    proof=restore_owned(console,[reference])
    geo.project_uv(console)
    return objects,proofs,proof
