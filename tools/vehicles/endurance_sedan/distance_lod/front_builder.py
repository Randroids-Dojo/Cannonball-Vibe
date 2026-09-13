"""Closed current-native mixed front copies at both existing lower levels."""
import bpy


def build(source,parent,collection,*,feature,encoder,paint,selective,geometry,shell_certificate,reference):
    if parent is None or parent.name not in {'Visual_LOD1','Visual_LOD2'}:
        raise ValueError('Mixed current front applies only to both declared lower levels')
    adapter=feature.Adapter(source,paint,encoder,reference)
    attempts=[]
    for ratio in selective.ratios(.065):
        obj=source.copy();obj.data=source.data.copy();obj.name='LOD'+parent.name[-1]+'_MixedProtectedFront'
        collection.objects.link(obj);world=source.matrix_world.copy();obj.parent=parent;obj.matrix_world=world
        bpy.context.view_layer.update();item={'ratio':ratio};accepted=False
        try:
            baseline=feature.verify(obj,reference)
            if baseline['maximum_native_normal_angle_degrees']!=0.:
                raise ValueError('Native source copy changed original field')
            protection=adapter.prepare(obj)
            if ratio<1:
                modifier=obj.modifiers.new('Protected current mixed front','DECIMATE')
                modifier.ratio=adapter.configure(obj,modifier,protection,ratio)
                modifier.use_collapse_triangulate=True;item['native_requested_ratio']=modifier.ratio
                bpy.context.view_layer.objects.active=obj;bpy.ops.object.modifier_apply(modifier=modifier.name)
            if obj.data.validate(clean_customdata=False):raise ValueError('Native validate changed geometry')
            obj.data.update();item['field']=adapter.restore(obj,protection)
            geometry.repair_triangulation(obj);item['final_original_field']=feature.verify(obj,reference)
            item['counts']=geometry.evaluated_counts(obj)
            if any(item['counts'][k] for k in ('nonmanifold_edges','degenerate_triangles','duplicate_faces',
                    'triangulated_nonmanifold_edges','triangulated_duplicate_faces','zero_corner_normals',
                    'nonfinite_corner_normals','nonunit_corner_normals')):
                raise ValueError('Generated mixed front geometry/raw normal invalid')
            item['self']=shell_certificate(selective.native_row(obj))
            if item['self']['status']!='passed':raise ValueError('Generated mixed front indexed self intersection')
            item['status']='passed';accepted=True
        except Exception as error:item.update(status='rejected',failure=type(error).__name__+': '+str(error))
        attempts.append(item)
        print('MIXED_FRONT_ATTEMPT '+obj.name+' '+str(ratio)+' '+item['status'],flush=True)
        if accepted:
            return obj,{'source_component':source.name,'parent':parent.name,'attempts':attempts,
                'domain':reference['domain'],'caller_binding_digest':reference['binding_digest'],
                'source_protected_triangles':reference['triangles'],
                'representation':'Separate complete closed mixed-material current native front; never rebatch after field proof'}
        data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if data.users==0:bpy.data.meshes.remove(data)
    raise ValueError('No valid current mixed front: '+str(attempts))
