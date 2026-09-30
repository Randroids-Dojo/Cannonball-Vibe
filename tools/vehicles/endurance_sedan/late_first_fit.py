"""Build fitted dashboard, tail passages and tank feet from the current scene.

No scene I/O, historical payload or external source supplies the geometry.
"""
import math
import bpy
from mathutils import Vector
from . import geometry as geo, assembly_fields as owned
from .floor_panels import freeze,remove,coat_cut_faces
from . import boolean_surface
from .qa.self_geometry import scan

def build():
    """Apply once to an unsaved combined pilot; return changed objects and proof."""
    if bpy.context.scene.get('cb_late_first_fit_applied'):raise ValueError('Late fit02 must be applied once')
    objects=bpy.data.objects;ref=objects['LOD0_DashboardCore'];collection=ref.users_collection[0];parent=ref.parent;mat=ref.data.materials[0]
    changed={};refs={};cuts={};proof={'scope':'First finite dashboard/fascia/foot correction, not complete mechanical or source approval','intended_seats':[]}
    def prepare(name):
        obj=objects[name];owned.CLEANUP.pop(name,None);refs[name]=owned.capture(obj);changed[name]=obj;return obj
    def points(obj):
        ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());m=ev.to_mesh()
        try:return [tuple(ev.matrix_world@v.co)for v in m.vertices]
        finally:ev.to_mesh_clear()
    def cut(obj,tool):
        coords=points(tool);cuts.setdefault(obj.name,[]).append({'tool':tool.name,'bounds':[[min(p[i]for p in coords)for i in range(3)],[max(p[i]for p in coords)for i in range(3)]]})
        copy=tool.copy();copy.data=tool.data.copy();collection.objects.link(copy);copy.name='PrivateLateCut'
        try:
            freeze(copy);copy.data.materials.clear();copy.data.materials.append(obj.data.materials[0])
            for p in copy.data.polygons:p.material_index=0
            geo.boolean(obj,copy);coat_cut_faces(obj,obj.data.materials[0])
        finally:remove(copy)
    core=prepare('LOD0_DashboardCore');upper=prepare('LOD0_DashboardUpper')
    cut(core,upper);proof['intended_seats'].append([core.name,upper.name,'Actual upholstered upper-shell recess'])
    for obj in (core,upper):
        cut(obj,objects['LOD0_NavigationSurround']);proof['intended_seats'].append([obj.name,'LOD0_NavigationSurround','Actual case-foot recess'])
    # The column is a fixed molded shroud; its unchanged true axis and radius
    # receive a 1.5 mm radial fit clearance through the dashboard core.
    start=Vector((-.43,.260,.834));end=Vector((-.43,.536,.731));axis=(end-start).normalized()
    bore=geo.tube('PrivateSteeringColumnPassage',[start-axis*.050,end+axis*.075],.0445,None,collection,sides=16)
    cut(core,bore);remove(bore)
    proof['column_passage']={'original_endpoints':[list(start),list(end)],'radius_m':.0445,'guard':'Actual complete clearance measured separately'}
    for name,front in [('LOD0_Glovebox',.45675)]+[(n,.45625)for n in sorted(objects.keys())if n.startswith('LOD0_VentHousing_')]:
        pts=points(objects[name]);lo=[min(p[i]for p in pts)for i in range(3)];hi=[max(p[i]for p in pts)for i in range(3)]
        tool=geo.box('PrivateGuardPocket_'+name,((lo[0]+hi[0])/2,(.3+front)/2,(lo[2]+hi[2])/2),(hi[0]-lo[0]+.0025,front-.3,hi[2]-lo[2]+.0025),None,collection,radius=0)
        cut(core,tool);remove(tool)
    bumper=prepare('LOD0_RearBumper');valance=prepare('LOD0_RearLowerValance')
    cut(bumper,valance);proof['intended_seats'].append([bumper.name,valance.name,'Original continuous valance in an actual fitted body recess'])
    for suffix in ('L','R'):
        reflector=objects['LOD0_RearReflector_'+suffix];cut(bumper,reflector)
        proof['intended_seats'].append([bumper.name,reflector.name,'Original reflector body recess'])
    # Small eight-corner twin-outlet aperture, with 8 mm corner chamfers.
    # Both the rear body and the retained lower-valance mesh get real passages.
    hx,hz,ch=.091,.046,.008
    ring=[(-hx+ch,-hz),(hx-ch,-hz),(hx,-hz+ch),(hx,hz-ch),(hx-ch,hz),(-hx+ch,hz),(-hx,hz-ch),(-hx,-hz+ch)]
    for side in (-1,1):
        vertices=[(side*.647+x,y,.312+z)for y in(-2.560,-2.268)for x,z in ring]
        faces=[tuple(reversed(range(8))),tuple(range(8,16))]+[(i,(i+1)%8,(i+1)%8+8,i+8)for i in range(8)]
        tool=geo.mesh('PrivateTwinTailOpening_'+str(side),vertices,faces,None,collection)
        for obj in (bumper,valance):cut(obj,tool)
        remove(tool)
    proof['rear_passages']={'center_x_m':[-.647,.647],'y_m':[-2.560,-2.268],'z_center_m':.312,'width_height_m':[.182,.092],'corner_chamfer_m':.008}
    for side in(-1,1):
        name='LOD0_AuxTankFoot_'+str(side)+'_-1.7';obj=objects[name];freeze(obj)
        for vertex in obj.data.vertices:vertex.co.y-=.018
        obj.data.update();geo.project_uv(obj);changed[name]=obj
    proof['foot_shift']={'names':['LOD0_AuxTankFoot_-1_-1.7','LOD0_AuxTankFoot_1_-1.7'],'translation_source_m':[0,-.018,0],'support_contract':'Complete current-scene foot caps mate with tank and carpet; caller verifies actual geometry'}
    proof['exact_repairs']={};proof['fields']={}
    for name,obj in list(changed.items()):
        if name not in refs:continue
        owned.clean(obj)
        proof['exact_repairs'][name]=boolean_surface.repair(obj,scan,geo.evaluated_counts)
        proof['fields'][name]=owned.restore(obj,refs[name])
        if not proof['fields'][name]['native_encoding']['passed']:raise ValueError('Original-field native encoding failed: '+name)
    proof['cuts']=cuts
    bpy.context.scene['cb_late_first_fit_applied']=True
    return changed,proof
