"""Six small cylindrical details; preserve exact axes, extents and materials."""
import math
import bpy


def recipes():
    result=[]
    for suffix in ('FL','FR','RL','RR'):
        side=-1 if suffix.endswith('L') else 1
        result.append(('LOD0_WheelHub_'+suffix,
                       [(side*.098-.009,0,0),(side*.098+.009,0,0)],.067,32,24))
    for x in (-.143,.143):
        result.append(('LOD0_ClimateKnob_'+str(x),[(x,.425,.733),(x,.401,.733)],.024,24,16))
    return result


def apply(geo,row):
    staged=[];proof=[]
    try:
        for name,points,radius,old_sides,new_sides in recipes():
            obj=bpy.data.objects[name]
            if obj.type!='MESH' or obj.modifiers or len(obj.material_slots)!=1:
                raise ValueError('Unexpected small-cylinder construction: '+name)
            before=row(obj)
            collection=obj.users_collection[0]
            original=geo.tube('Private_Original_'+name,points,radius,obj.data.materials[0],collection,obj.parent,sides=old_sides)
            try:
                original.matrix_world=obj.matrix_world.copy()
                bpy.context.view_layer.update()
                expected=row(original);expected['name']=name
                if expected!=before:
                    raise ValueError('Actual detail differs from original current native recipe: '+name)
            finally:
                data=original.data;bpy.data.objects.remove(original,do_unlink=True)
                if data.users==0:bpy.data.meshes.remove(data)
            candidate=geo.tube('Private_Reduced_'+name,points,radius,obj.data.materials[0],collection,obj.parent,sides=new_sides)
            candidate.matrix_world=obj.matrix_world.copy()
            staged.append((obj,candidate))
            bpy.context.view_layer.update();after=row(candidate)
            bounds=lambda r:[[min(v[k] for v in r['vertices']),max(v[k] for v in r['vertices'])] for k in range(3)]
            a,b=bounds(before),bounds(after)
            if max(abs(x-y) for aa,bb in zip(a,b) for x,y in zip(aa,bb))>1e-7:
                raise ValueError('Native detail envelope changed: '+name)
            info=geo.evaluated_counts(candidate)
            defect_keys=('duplicate_faces','nonmanifold_edges','degenerate_faces','degenerate_triangles',
                         'triangulated_duplicate_faces','triangulated_nonmanifold_edges',
                         'nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals')
            if any(info[k] for k in defect_keys):
                raise ValueError('Invalid reduced cylindrical detail: '+name)
            proof.append({'object':name,'axis_endpoints_local_m':points,'radius_m':radius,
                          'radial_segments_before':old_sides,'radial_segments_after':new_sides,
                          'triangles_before':len(before['triangles']),'triangles_after':len(after['triangles']),
                          'complete_circular_surface_chord_error_max_m':radius*(1-math.cos(math.pi/new_sides)),
                          'bounds_before_m':a,'bounds_after_m':b,'native':info,
                          'original_recipe_exact':True,
                          'scope':'New radial detail sampling with fixed endpoints, radius, parent, material, physical UV frequency and cardinal envelope. New facet geometry and native normals; no original full-field preservation claim. Actual visual/assembly/motion QA remains required.'})
        for obj,candidate in staged:
            old_data=obj.data;obj.data=candidate.data
            obj['radial_detail_revision26']='Native cylinder sampling; exact radius/axis retained'
            if old_data.users==0:bpy.data.meshes.remove(old_data)
        return [obj for obj,_ in staged],proof
    finally:
        for _,candidate in staged:
            if bpy.data.objects.get(candidate.name)==candidate:
                data=candidate.data;bpy.data.objects.remove(candidate,do_unlink=True)
                if data.users==0:bpy.data.meshes.remove(data)
