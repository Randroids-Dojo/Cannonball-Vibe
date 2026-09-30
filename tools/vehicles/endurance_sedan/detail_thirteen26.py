"""Thirteen measured revolved details with unchanged engineering profiles."""
import math
import bpy


def recipes():
    rim = [(-.108,.227),(-.108,.2445),(-.100,.247),(-.094,.242),
           (.094,.242),(.100,.247),(.108,.2445),(.108,.227)]
    result = []
    for suffix in ('FL','FR','RL','RR'):
        side = -1 if suffix.endswith('L') else 1
        result.append(('LOD0_RimBarrel_'+suffix, 'ring', rim, (0,0,0), 36,32))
        radius = .1995 if suffix.startswith('F') else .178
        thickness = .036 if suffix.startswith('F') else .022
        face = .009 if suffix.startswith('F') else .006
        profile = [(-face/2,.104),(-face/2,radius),(face/2,radius),(face/2,.104)]
        for s in (-1,1):
            center = (side*.025+s*(thickness-face)/2,0,0)
            result.append(('LOD0_BrakeFace_'+suffix+str(s),'ring',profile,center,36,32))
    result.append(('LOD0_SteeringRim','tube',.176,.018,48,40))
    return result


def apply(geo,row):
    staged=[];proof=[]
    try:
        for name,kind,profile,center,old_count,new_count in recipes():
            obj=bpy.data.objects[name]
            if obj.type!='MESH' or obj.modifiers or len(obj.material_slots)!=1:
                raise ValueError('Unexpected detail construction: '+name)
            old=row(obj)
            def make(n,label):
                args=(label,obj.data.materials[0],obj.users_collection[0],obj.parent)
                if kind=='ring':
                    made=geo.ring_x(args[0],profile,center,*args[1:],n)
                else:
                    points=[(profile*math.cos(i*math.tau/n),0,profile*math.sin(i*math.tau/n)) for i in range(n)]
                    made=geo.tube(args[0],points,center,*args[1:],sides=10,closed=True)
                made.matrix_parent_inverse=obj.matrix_parent_inverse.copy()
                made.rotation_mode=obj.rotation_mode
                made.location=obj.location.copy()
                made.scale=obj.scale.copy()
                if obj.rotation_mode=='QUATERNION':made.rotation_quaternion=obj.rotation_quaternion.copy()
                elif obj.rotation_mode=='AXIS_ANGLE':made.rotation_axis_angle=obj.rotation_axis_angle[:]
                else:made.rotation_euler=obj.rotation_euler.copy()
                bpy.context.view_layer.update()
                return made
            original=make(old_count,'Private_Original_'+name)
            try:
                expected=row(original);expected['name']=name
                if expected!=old:raise ValueError('Original current native recipe differs: '+name)
            finally:
                mesh=original.data;bpy.data.objects.remove(original,do_unlink=True)
                if mesh.users==0:bpy.data.meshes.remove(mesh)
            new=make(new_count,'Private_Reduced_'+name);staged.append((obj,new))
            after=row(new);info=geo.evaluated_counts(new)
            defects=('duplicate_faces','nonmanifold_edges','degenerate_faces','degenerate_triangles',
                     'triangulated_duplicate_faces','triangulated_nonmanifold_edges',
                     'nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals')
            if any(info[k] for k in defects):raise ValueError('Reduced detail invalid: '+name)
            bounds=lambda r:[[min(v[k] for v in r['vertices']),max(v[k] for v in r['vertices'])] for k in range(3)]
            a,b=bounds(old),bounds(after)
            delta=max(abs(x-y) for aa,bb in zip(a,b) for x,y in zip(aa,bb))
            if delta>2e-7:raise ValueError('Cardinal native envelope changed: '+name)
            outer=max(p[1] for p in profile) if kind=='ring' else profile+center
            proof.append({'object':name,'kind':kind,'profile_or_centerline_radius_m':profile,
                          'center_or_cross_section_radius_m':center,'segments_before':old_count,
                          'segments_after':new_count,'triangles_before':len(old['triangles']),
                          'triangles_after':len(after['triangles']),'original_recipe_exact':True,
                          'bounds_before_m':a,'bounds_after_m':b,'bound_delta_max_m':delta,
                          'analytic_outer_chord_error_bound_m':outer*(1-math.cos(math.pi/new_count)),
                          'native':info,'fit_and_visual_acceptance':False})
        for obj,new in staged:
            old_mesh=obj.data;obj.data=new.data
            obj['detail_reserve_revision26']='Fixed dimensional profiles with measured radial sampling'
            if old_mesh.users==0:bpy.data.meshes.remove(old_mesh)
        return [obj for obj,_ in staged],proof
    finally:
        for _,new in staged:
            if bpy.data.objects.get(new.name)==new:
                mesh=new.data;bpy.data.objects.remove(new,do_unlink=True)
                if mesh.users==0:bpy.data.meshes.remove(mesh)
