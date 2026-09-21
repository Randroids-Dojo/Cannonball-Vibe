"""Extend two front liner ends using the actual fresh body envelope."""
import json,math
import bpy
from mathutils import Vector


def apply(geo,row,body):
    staged=[];proof=[]
    angles=[-27,-24,-21]+[-18+4.5*i for i in range(49)]+[201,204,207]
    try:
        for side,symbol in ((-1,'L'),(1,'R')):
            obj=bpy.data.objects['LOD0_WheelArchLiner_F'+symbol]
            if obj.modifiers or len(obj.data.vertices)!=196:raise ValueError('Unexpected current liner topology')
            before=row(obj);old_vertices=[v.co.copy() for v in obj.data.vertices]
            verts=[];surface=[];exact_old_count=0
            for i,angle_deg in enumerate(angles):
                a=math.radians(angle_deg);hits=[]
                for radius in (.444,.449):
                    point=body.ray_cast(Vector((side*2,1.46+radius*math.cos(a),.3433+radius*math.sin(a))),Vector((-side,0,0)),3)[0]
                    if point is None:raise ValueError('Extended liner has no original body receiver')
                    hits.append(abs(point.x))
                outer=min(.918,min(hits)-.003)
                if outer<=.465:raise ValueError('Extended molded shell inverts')
                station=[Vector((side*x,1.46+r*math.cos(a),.3433+r*math.sin(a))) for x,r in ((.465,.444),(outer,.444),(outer,.449),(.465,.449))]
                if -18<=angle_deg<=198:
                    original_index=round((angle_deg+18)/4.5)
                    actual=old_vertices[original_index*4:original_index*4+4]
                    if max((p-q).length for p,q in zip(station,actual))>2e-7:
                        raise ValueError('Fresh original body differs at existing liner station')
                    station=actual;exact_old_count+=4
                verts.extend(station)
                surface.append({'angle_degrees':angle_deg,'body_outer_abs_x_m':hits,'outer_abs_x_m':outer})
            faces=[]
            for i in range(len(angles)-1):
                for j in range(4):faces.append((4*i+j,4*i+(j+1)%4,4*(i+1)+(j+1)%4,4*(i+1)+j))
            faces.extend([(3,2,1,0),tuple(4*(len(angles)-1)+j for j in range(4))])
            trial=geo.mesh('Private_Extended_'+obj.name,verts,faces,obj.data.materials[0],obj.users_collection[0],obj.parent,smooth=True)
            staged.append((obj,trial));bpy.context.view_layer.update()
            after=row(trial);quality=geo.evaluated_counts(trial)
            keys=('duplicate_faces','nonmanifold_edges','degenerate_faces','degenerate_triangles',
                  'triangulated_duplicate_faces','triangulated_nonmanifold_edges','nonfinite_corner_normals','zero_corner_normals','nonunit_corner_normals')
            if any(quality[k] for k in keys):raise ValueError('Invalid extended molded liner')
            if min(v[2] for v in after['vertices'])<.135:raise ValueError('Declared body clearance violated')
            proof.append({'object':obj.name,'original_vertices_preserved_exactly':exact_old_count,
                          'triangles_before':len(before['triangles']),'triangles_after':len(after['triangles']),
                          'minimum_z_m':min(v[2] for v in after['vertices']),'angular_stations_degrees':angles,
                          'body_return':surface,'native':quality})
        for obj,trial in staged:
            old=obj.data;obj.data=trial.data
            obj['front_liner_revision26']='Extended lower returns;49 original stations exact'
            obj['molded_body_return']=json.dumps(next(p['body_return'] for p in proof if p['object']==obj.name),sort_keys=True)
            if old.users==0:bpy.data.meshes.remove(old)
        return [o for o,_ in staged],proof
    finally:
        for _,trial in staged:
            if bpy.data.objects.get(trial.name)==trial:
                data=trial.data;bpy.data.objects.remove(trial,do_unlink=True)
                if data.users==0:bpy.data.meshes.remove(data)
