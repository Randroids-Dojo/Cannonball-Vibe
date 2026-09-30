"""Add finite dashboard carrier and hidden knob bosses, preserving controls."""
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def apply(geo,row):
    dashboard=bpy.data.objects['LOD0_DashboardCore']
    receiver=BVHTree.FromObject(dashboard,bpy.context.evaluated_depsgraph_get())
    # Existing source transforms are identity for stationary cabin assemblies.
    if dashboard.matrix_world!=bpy.data.objects['LOD0_ClimateKnob_-0.143'].matrix_world:
        raise ValueError('Unexpected stationary cabin frame')
    switches=[bpy.data.objects['LOD0_ClimateSwitch_'+str(x)] for x in (-.062,0,.062)]
    backs=[max(v[1] for v in row(obj)['vertices']) for obj in switches]
    if max(backs)-min(backs)>2e-7:raise ValueError('Switches lack a common actual seating plane')
    front=backs[0];hits=[]
    for x in (-.176,.176):
        for z in (.776,.800):
            point=receiver.ray_cast(Vector((x,.3,z)),Vector((0,1,0)),.4)[0]
            if point is None:raise ValueError('Dashboard carrier lacks actual upper support')
            hits.append(tuple(point))
    back=hits[0][1]
    if max(abs(p[1]-back) for p in hits)>2e-7:raise ValueError('Upper carrier support is not one actual plane')
    outline=[(front,.699),(front,.800),(back,.800),(back,.776),(front+.016,.758),(front+.010,.699)]
    material=bpy.data.materials['Material_Trim'];collection=dashboard.users_collection[0]
    carrier=geo.prism_x('LOD0_ClimateControlCarrier',outline,-.176,.176,material,collection,dashboard.parent)
    objects=[carrier];proof=[{'object':carrier.name,'outline_yz_m':outline,'width_m':.352,
                             'receiver':dashboard.name,'receiver_plane_y_m':back,
                             'upper_bearing_domain_xz_m':[[-.176,.176],[.776,.800]],
                             'native_ray_corners':hits,'switch_front_plane_y_m':front}]
    for x in (-.143,.143):
        knob=bpy.data.objects['LOD0_ClimateKnob_'+str(x)]
        knob_back=max(v[1] for v in row(knob)['vertices'])
        if not 0<front-knob_back<.003:raise ValueError('Unexpected knob to carrier interval')
        points=[(x,knob_back,.733),(x,front,.733)]
        boss=geo.tube('LOD0_ClimateKnobBoss_'+str(x),points,.019,material,collection,dashboard.parent,sides=8)
        objects.append(boss);proof.append({'object':boss.name,'axis_endpoints_m':points,'radius_m':.019,'sides':8,
                                          'front_receiver':knob.name,'rear_receiver':carrier.name})
    bpy.context.view_layer.update()
    keys=('duplicate_faces','nonmanifold_edges','degenerate_faces','degenerate_triangles',
          'triangulated_duplicate_faces','triangulated_nonmanifold_edges','nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals')
    for obj,p in zip(objects,proof):
        p['native']=geo.evaluated_counts(obj)
        if any(p['native'][k] for k in keys):raise ValueError('Invalid climate mount: '+obj.name)
        obj['original_construction_revision26']='Finite mounted climate carrier; actual receivers preserved'
        obj['maximum_lod']=0
    return objects,proof
