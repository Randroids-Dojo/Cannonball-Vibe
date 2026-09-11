"""Editable, driver-based Blender instrumentation; runtime uses its own display."""

import math
import struct
from collections import Counter, defaultdict

import bpy
from mathutils import Euler, Vector

from . import geometry as geo
from .cabin import text_mesh
from .mechanisms import scalar_driver, variable


def preview_only(obj):
    obj['source_preview_only']=True;obj['maximum_lod']=0
    return obj


def separate_touching_font_shells(obj):
    """Undo a point/edge weld between otherwise closed glyph contours.

    The exact oriented triangle positions, material, UV and corner normals
    remain unchanged. A source-only text preview gains separate shell indices.
    """
    old=obj.data
    edge_faces=defaultdict(list)
    for face in old.polygons:
        for edge in face.edge_keys:edge_faces[tuple(sorted(edge))].append(face.index)
    adjacent=defaultdict(set)
    for faces in edge_faces.values():
        if len(faces)==2:
            adjacent[faces[0]].add(faces[1]);adjacent[faces[1]].add(faces[0])
    component={}
    for index in range(len(old.polygons)):
        if index in component:continue
        pending=[index]
        while pending:
            face=pending.pop()
            if face in component:continue
            component[face]=index;pending.extend(adjacent[face]-component.keys())
    vertices=[];faces=[];lookup={}
    for face in old.polygons:
        indices=[]
        for vertex in face.vertices:
            key=(component[face.index],vertex)
            if key not in lookup:
                lookup[key]=len(vertices);vertices.append(tuple(old.vertices[vertex].co))
            indices.append(lookup[key])
        faces.append(indices)
    mesh=bpy.data.meshes.new(old.name+'SeparateClosedShells')
    mesh.from_pydata(vertices,[],faces);mesh.update()
    for material in old.materials:mesh.materials.append(material)
    for face,original in zip(mesh.polygons,old.polygons):
        face.material_index=original.material_index;face.use_smooth=original.use_smooth
    for original in old.uv_layers:
        layer=mesh.uv_layers.new(name=original.name)
        layer.data.foreach_set('uv',[value for corner in original.data for value in corner.uv])
    mesh.normals_split_custom_set([tuple(normal.vector) for normal in old.corner_normals])
    mesh.calc_loop_triangles();old.calc_loop_triangles()
    def canonical(data):
        return Counter(min(tuple(tuple(data.vertices[triangle.vertices[(i+j)%3]].co)
                                 for j in range(3)) for i in range(3))
                       for triangle in data.loop_triangles)
    if canonical(old)!=canonical(mesh):raise ValueError('Font shell split changed visible triangles')
    counts=Counter(tuple(sorted(edge)) for triangle in mesh.loop_triangles
                   for edge in ((triangle.vertices[0],triangle.vertices[1]),
                                (triangle.vertices[1],triangle.vertices[2]),
                                (triangle.vertices[2],triangle.vertices[0])))
    if any(count!=2 for count in counts.values()):raise ValueError('Font shell split remains nonmanifold')
    obj.data=mesh;obj['exact_position_font_shell_split']=True


def build(collection,lod,mats,pivots,controls,spec):
    old=bpy.data.objects.get('LOD0_InstrumentSourceLegend')
    if old:bpy.data.objects.remove(old,do_unlink=True)
    for name,value,maximum in (('source_sim_speed_mph',0,250),('source_sim_rpm',750,7500),('source_sim_fuel_l',82,175),('source_sim_gear',0,7),
                               ('source_sim_damage',0,1),('source_sim_cooling_condition',1,1),
                               ('source_sim_tire_condition',1,1),('source_sim_handbrake',0,1)):
        controls[name]=float(value)
        controls.id_properties_ui(name).update(min=-1 if name.endswith('gear') else 0,max=maximum,description='Blender inspection state only; runtime reads its authoritative vehicle/run state')
    rest=Vector(spec['hardpoints_source_m']['Instrument_Cluster'])+Vector((0,-.030,.007))
    rotation=Euler((math.radians(-15),0,0));matrix=rotation.to_matrix()
    light=bpy.data.materials.new('Preview_InstrumentGlyphs');light.use_nodes=True
    shader=light.node_tree.nodes['Principled BSDF'];shader.inputs['Base Color'].default_value=(.5,.65,.75,1)
    shader.inputs['Emission Color'].default_value=(.5,.65,.75,1);shader.inputs['Emission Strength'].default_value=.8
    def label(text,u,v,size):
        obj=text_mesh('LOD0_SourceDisplay_'+text,text,rest+matrix@Vector((u,-.001,v)),size,light,collection,lod,(math.radians(75),0,0))
        if text=='PARK BRAKE':separate_touching_font_shells(obj)
        return preview_only(obj)
    def number(prop,u,v,digits,height):
        width=height*.50;spacing=height*.68;thickness=height*.10
        # Segments: top, upper-right, lower-right, bottom, lower-left,
        # upper-left, center. Every visible segment is a closed solid mesh.
        locations=[(0,.5,True),(.5,.25,False),(.5,-.25,False),(0,-.5,True),(-.5,-.25,False),(-.5,.25,False),(0,0,True)]
        values=[(0,2,3,5,6,7,8,9),(0,1,2,3,4,7,8,9),(0,1,3,4,5,6,7,8,9),(0,2,3,5,6,8,9),(0,2,6,8),(0,4,5,6,8,9),(2,3,4,5,6,8,9)]
        for digit in range(digits):
            formula=f'(floor(value/{10**(digits-1-digit)})%10)'
            for segment,((x,z,horizontal),shown) in enumerate(zip(locations,values)):
                local=Vector((u+digit*spacing+x*width,-.001,v+z*height))
                size=(width, .0008,thickness) if horizontal else (thickness,.0008,height*.43)
                obj=preview_only(geo.box(f'LOD0_SourceDigit_{prop}_{digit}_{segment}',rest+matrix@local,size,light,collection,lod,radius=0,rotation=rotation))
                missing=sorted(set(range(10))-set(shown))
                expression=(' or '.join(formula+'=='+str(i) for i in missing)
                            if len(missing)<=len(shown)
                            else ' and '.join(formula+'!='+str(i) for i in shown))
                for path in ('hide_render','hide_viewport'):scalar_driver(obj,path,None,controls,prop,expression)
    number('source_sim_speed_mph',-.14,.026,3,.032);label('MPH',-.080,.058,.009)
    number('source_sim_rpm',-.145,-.041,4,.019);label('RPM',-.056,-.039,.008)
    number('source_sim_fuel_l',.048,-.041,3,.019);label('L',.101,-.040,.009)
    label('FUEL',.071,-.017,.008)
    for value in range(-1,8):
        gear=label('R' if value==-1 else 'N' if value==0 else str(value),.063,.030,.036)
        for path in ('hide_render','hide_viewport'):scalar_driver(gear,path,None,controls,'source_sim_gear','value!='+str(value))
    # Keep warnings above the steering-rim sightline, matching the runtime
    # display's top strip. Source23's lower row was partly occluded in Godot.
    # Blender driver inputs are float32 even when an ID property stores a
    # double. Quantize nominal thresholds to the same representation so exact
    # UI boundary values do not spuriously activate a warning. This source
    # display preview does not replace the runtime's double condition state.
    def driver_threshold(value):
        return repr(struct.unpack('<f',struct.pack('<f',value))[0])
    warnings=(('LOW FUEL','value','<',20),('DAMAGE','damage','>',.05),
              ('COOLING','cooling','<',.4),('TIRES','tires','<',.3),
              ('PANEL OPEN','max(fl,fr,rl,rr,hood,trunk)','>',.001),
              ('PARK BRAKE','handbrake','>',.02))
    bindings={'damage':'source_sim_damage','cooling':'source_sim_cooling_condition',
              'tires':'source_sim_tire_condition','handbrake':'source_sim_handbrake',
              'fl':'Door_FL_open','fr':'Door_FR_open','rl':'Door_RL_open','rr':'Door_RR_open',
              'hood':'Hood_Hinge_open','trunk':'Trunk_Hinge_open'}
    prior=[]
    for text,field,comparison,threshold in warnings:
        warning=label(text,0,.061,.009)
        value=driver_threshold(threshold)
        condition=field+comparison+value
        selected=' and '.join([*prior,condition])
        for path in ('hide_render','hide_viewport'):
            curve=scalar_driver(warning,path,None,controls,'source_sim_fuel_l','not('+selected+')')
            for name,prop in bindings.items():variable(curve,name,controls,prop)
        prior.append(field+('>=' if comparison=='<' else '<=')+value)
    for name,prop,u in (('LEFT','left_indicators',-.181),('RIGHT','right_indicators',.157)):
        glyph=label(name,u,.056,.007)
        for path in ('hide_render','hide_viewport'):
            curve=scalar_driver(glyph,path,None,controls,prop,'max(value,hazard)<.5 or (frame-1)%60>=30')
            variable(curve,'hazard',controls,'hazards')
