"""Proposed current-scene shoulder target ownership. No file or scene IO.

capture immediately after creating the pre-bevel body; after_bevel after the
native cap/strength classification; finish after TRIANGULATE and repair, before
any shared surface/reference capture. The caller supplies the same analytic
source point/normal functions used by the construction and the native codec.
"""
import math
import struct
from collections import defaultdict

SOURCE='cb_shoulder_source_face'
POST='cb_shoulder_post_face'
ANGLE=.025
T_START=14./3.
Y_START=1.82
Y_FULL=1.9883333333333333
T_FULL_END=7.+1./3.
T_END=8.

def require(test,message):
    if not test:raise ValueError(message)

def finite(values):return all(type(x) in (int,float) and math.isfinite(x) for x in values)
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def angle(a,b):
    c=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*c),dot(a,b)))
def unit(n):
    require(len(n)==3 and finite(n),'Invalid authored or native normal')
    length=math.hypot(*n);require(length>1e-12,'Zero authored or native normal')
    return tuple(x/length for x in n)
def smooth(x):
    x=max(0.,min(1.,x));return x*x*x*(10.-15.*x+6.*x*x)
def weight(t,y):
    return smooth((t-T_START)/(5.-T_START))*smooth((y-Y_START)/(Y_FULL-Y_START))*smooth((T_END-t)/(T_END-T_FULL_END))

def edge_parameter(point,points,parameters):
    """Actual original edge in native coordinates, unchanged 1 micrometre guard."""
    require(len(point)==3 and finite(point) and len(points)==len(parameters)>=3,'Invalid finite edge inventory')
    choices=[]
    for i,(a,b) in enumerate(zip(points,points[1:]+points[:1])):
        d=sub(b,a);length=dot(d,d);require(length>0,'Degenerate original edge')
        fraction=max(0.,min(1.,dot(sub(point,a),d)/length))
        projected=tuple(x+fraction*v for x,v in zip(a,d));distance=math.dist(point,projected)
        if distance>1e-6:continue
        pa,pb=parameters[i],parameters[(i+1)%len(parameters)]
        value=tuple(x+fraction*(y-x) for x,y in zip(pa[:2],pb[:2]))
        choices.append({'edge':i,'fraction':fraction,'distance_m':distance,'parameters':value,'projected_point':projected})
    require(bool(choices),'New retained corner has no original finite edge within 1um')
    best=min(choices,key=lambda r:(r['distance_m'],r['edge']))
    ties=[r for r in choices if r['distance_m']<=best['distance_m']+1e-10]
    require(all(math.dist(r['parameters'],best['parameters'])<=1e-7 for r in ties),'Ambiguous finite edge parameter')
    return best

def mesh_physical(mesh):
    return {'vertices':[tuple(v.co) for v in mesh.vertices],
        'edges':[tuple(e.vertices) for e in mesh.edges],
        'faces':[(tuple(p.vertices),p.material_index,p.use_smooth) for p in mesh.polygons],
        'loops':[(l.vertex_index,l.edge_index) for l in mesh.loops],
        'materials':[m.name if m else None for m in mesh.materials],
        'uv':{u.name:[tuple(v.uv) for v in u.data] for u in mesh.uv_layers}}

class Targets:
    def __init__(self,mesh,parameters,point):
        require(SOURCE not in mesh.attributes and POST not in mesh.attributes,'Duplicate shoulder construction hook')
        require(len(parameters)==len(mesh.vertices),'Incomplete source parameter inventory')
        self.vertex_parameters=[];self.source=[];self.post=None
        for vertex,p in zip(mesh.vertices,parameters):
            if p is None:self.vertex_parameters.append(None);continue
            require(len(p)==3 and finite(p) and type(p[2]) is int and p[2] in (-1,1) and 0<=p[0]<=8 and -2.54<=p[1]<=2.4,'Invalid exact source parameter')
            value=tuple(point(*p));require(len(value)==3 and finite(value),'Invalid source point')
            require(tuple(f32(x) for x in value)==tuple(vertex.co),'Source parameter does not reconstruct the native vertex exactly')
            self.vertex_parameters.append(tuple(p))
        # Snapshot plain Python IDs and arrays before adding an RNA attribute.
        for face in mesh.polygons:
            ids=tuple(face.vertices)
            self.source.append({'vertices':ids,'points':tuple(tuple(mesh.vertices[i].co) for i in ids),
                'parameters':tuple(self.vertex_parameters[i] for i in ids)})
        attr=mesh.attributes.new(name=SOURCE,type='INT',domain='FACE')
        for i,item in enumerate(attr.data):item.value=i

    def after_bevel(self,mesh,normal):
        require(self.post is None and SOURCE in mesh.attributes and POST not in mesh.attributes,'Wrong post-bevel lifecycle')
        for name in ('cb_fascia_cap','__mod_weightednormals_faceweight'):
            require(name in mesh.attributes,'Missing native cap/bevel provenance')
        tag=mesh.attributes['cb_fascia_cap'];strength=mesh.attributes['__mod_weightednormals_faceweight'];owners=mesh.attributes[SOURCE]
        require(all(a.domain=='FACE' and a.data_type=='INT' for a in (tag,strength,owners)),'Changed native face provenance schema')
        retained=[int(owners.data[f.index].value) for f in mesh.polygons if strength.data[f.index].value==16384]
        require(sorted(retained)==list(range(len(self.source))),'Missing, repeated or changed retained source-face ownership')
        for face in mesh.polygons:
            if strength.data[face.index].value!=16384:continue
            original=self.source[int(owners.data[face.index].value)]['points']
            lo=tuple(min(p[a] for p in original) for a in range(3));hi=tuple(max(p[a] for p in original) for a in range(3))
            require(all(all(lo[a]-1e-6<=mesh.vertices[v].co[a]<=hi[a]+1e-6 for a in range(3)) for v in face.vertices),'Retained face escapes its original finite source bounds')
        current=[tuple(n.vector) for n in mesh.corner_normals]
        require(all(abs(math.hypot(*n)-1.)<=1e-6 for n in current),'Invalid input native normal field')
        self.post=[];plans=[];recovered=[];selected={};edges=defaultdict(list);incident=defaultdict(list)
        for face in mesh.polygons:
            fi=int(face.index);ids=tuple(face.vertices);loops=tuple(face.loop_indices)
            row={'vertices':ids,'points':tuple(tuple(mesh.vertices[v].co) for v in ids),'loops':loops,
                'native':{v:current[l] for v,l in zip(ids,loops)},'tag':int(tag.data[fi].value),
                'strength':int(strength.data[fi].value),'targets':{},'weights':{},'boundary_sources':{}}
            self.post.append(row)
            for vi in ids:incident[vi].append(fi)
            for a,b in zip(ids,ids[1:]+ids[:1]):edges[tuple(sorted((a,b)))].append(fi)
            if row['tag'] or row['strength']!=16384:continue
            owner=int(owners.data[fi].value);require(0<=owner<len(self.source),'Invalid retained face owner')
            src=self.source[owner];ps=src['parameters'];points=src['points']
            require(all(p is not None for p in ps),'Retained side inherited cap provenance')
            if max(p[0] for p in ps)<=T_START or max(p[1] for p in ps)<=Y_START:continue
            sides={p[2] for p in ps if p[0] not in (0.,8.)}
            require(len(sides)==1,'Ambiguous source-face hemisphere')
            side=next(iter(sides));lookup={p:q for p,q in zip(points,ps)}
            for vi,li in zip(ids,loops):
                position=tuple(mesh.vertices[vi].co);exact=position in lookup
                if exact:t,y,_=lookup[position]
                else:
                    recovery=edge_parameter(position,points,ps);t,y=recovery['parameters']
                    recovered.append({'face':fi,'source_face':owner,'vertex':vi,'point':position,**recovery})
                require(min(q[0] for q in ps)<=t<=max(q[0] for q in ps) and min(q[1] for q in ps)<=y<=max(q[1] for q in ps),'Recovered parameter outside original face')
                require(position[0]*side>=-1e-7,'Source hemisphere contradicts actual point')
                w=weight(t,y)
                if w==0.:continue
                n=unit(normal(t,y,side));value=n
                row['targets'][vi]=value;row['weights'][vi]=w;selected[(fi,vi)]=value
                plans.append({'face':fi,'source_face':owner,'vertex':vi,'point':position,'parameters':(t,y,side),'weight':w,'exact_original_point':exact,'target':value})
        require(bool(plans),'Empty authored shoulder domain')
        # Author both endpoints of each finite side/fillet edge touched by the
        # side field. The old native mismatch is measured, not waived as
        # preservation. Keep generated interiors and retained cap targets.
        joins=[];propagated={}
        for edge,fs in edges.items():
            require(len(fs)==2,'Nonmanifold post-bevel source')
            for side_face,other_face in (fs,fs[::-1]):
                a,b=self.post[side_face],self.post[other_face]
                if a['tag'] or a['strength']!=16384 or b['strength']==16384 or b['tag']==1:continue
                if not any((side_face,vi) in selected for vi in edge):continue
                for vi in edge:
                    native_jump=angle(a['native'][vi],b['native'][vi])
                    # This endpoint is a newly authored side/fillet target; retain the old jump as evidence.
                    value=selected.get((side_face,vi),a['native'][vi])
                    for fi in incident[vi]:
                        row=self.post[fi]
                        if row['strength']==16384 or row['tag']==1:continue
                        # The native generated endpoint fan is in this explicit new boundary target domain.
                        key=(fi,vi)
                        if key in propagated:require(angle(propagated[key],value)<=1e-6,'Conflicting exact analytic boundary targets: '+str((key,angle(propagated[key],value))))
                        propagated[key]=value;row['boundary_sources'][vi]=(side_face,vi)
                    joins.append({'edge':edge,'side_face':side_face,'bevel_face':other_face,'vertex':vi,'before_jump_degrees':native_jump,'target':value})
        self.plans=plans;self.joins=joins;self.recovered=recovered
        self.proof={'source_faces':len(self.source),'selected_side_corners':len(plans),'edge_recovery_count':len(recovered),
            'maximum_actual_source_edge_distance_m':max((r['distance_m'] for r in recovered),default=0.),'source_edge_guard_m':1e-6,
            'finite_boundary_endpoint_rows':len(joins),'generated_boundary_corners':len(propagated),
            'maximum_prior_boundary_jump_degrees':max((j['before_jump_degrees'] for j in joins),default=0.)}
        attr=mesh.attributes.new(name=POST,type='INT',domain='FACE')
        for i,item in enumerate(attr.data):item.value=i
        mesh.attributes.remove(mesh.attributes[SOURCE])
        return self.proof

    def finish(self,mesh,encode):
        require(self.post is not None and POST in mesh.attributes and SOURCE not in mesh.attributes,'Wrong final field lifecycle')
        before=mesh_physical(mesh);current=[tuple(n.vector) for n in mesh.corner_normals];targets=list(current)
        mapped=set();face_rows=[];lookup_final=defaultdict(list)
        for face in mesh.polygons:
            owner=int(mesh.attributes[POST].data[face.index].value)
            require(0<=owner<len(self.post),'Invalid triangulated face owner')
            original=self.post[owner];lookup=dict(zip(original['vertices'],original['points']))
            require(len(face.vertices)==3,'Field must be authored after explicit triangulation')
            for li in face.loop_indices:
                vi=mesh.loops[li].vertex_index
                require(vi in lookup and tuple(mesh.vertices[vi].co)==lookup[vi],'Triangulation changed source vertex ownership')
                lookup_final[(owner,vi)].append(li)
                if vi in original['targets']:
                    w=original['weights'][vi];n=original['targets'][vi]
                    targets[li]=unit(tuple(a*(1-w)+b*w for a,b in zip(current[li],n)));mapped.add(li)
            face_rows.append({'owner':owner,'tag':original['tag'],'strength':original['strength'],'loops':list(face.loop_indices),'vertices':list(face.vertices)})
        # Resolve every endpoint from its actual final retained-side corner,
        # after native triangulation, with no interpolation of encoded IDs.
        final_joins=[]
        for face in face_rows:
            original=self.post[face['owner']]
            for vi,li in zip(face['vertices'],face['loops']):
                if vi not in original['boundary_sources']:continue
                source=original['boundary_sources'][vi];source_loops=lookup_final[source]
                require(bool(source_loops),'Missing final side endpoint')
                value=targets[source_loops[0]]
                require(all(angle(value,targets[i])<=1e-6 for i in source_loops),'One side endpoint has conflicting final targets')
                targets[li]=value;mapped.add(li);final_joins.append({'loop':li,'side_loops':source_loops,'vertex':vi})
        require(mapped and all(abs(math.hypot(*n)-1.)<=1e-6 for n in targets),'Invalid or empty final target field')
        result=encode(mesh,targets)
        require(result.get('passed') is True,'Native target codec rejected the final field')
        actual=[tuple(n.vector) for n in mesh.corner_normals]
        require(len(actual)==len(targets) and all(finite(n) and abs(math.hypot(*n)-1.)<=1e-6 for n in actual) and max(angle(a,b) for a,b in zip(targets,actual))<=ANGLE,'Final native target guard failed')
        require(mesh_physical(mesh)==before,'Normal encoding changed geometry, UV, material or face properties')
        bounds=[]
        def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
        for face in face_rows:
            a=[targets[i] for i in face['loops']];b=[actual[i] for i in face['loops']]
            cs=[cross(a[i],b[i]) for i in range(3)];ds=[dot(a[i],b[i]) for i in range(3)]
            for i,j in ((0,1),(1,2),(2,0)):
                cs.append(tuple((x+y)*.5 for x,y in zip(cross(a[i],b[j]),cross(a[j],b[i]))));ds.append((dot(a[i],b[j])+dot(a[j],b[i]))*.5)
            require(min(ds)>0.,'Unbounded complete interpolation target')
            bound=math.degrees(math.atan2(max(math.hypot(*c) for c in cs),min(ds)))
            require(bound<=ANGLE,'Complete barycentric target/native field exceeds .025 degrees')
            bounds.append(bound)
        self.proof.update(final_selected_corners=len(mapped),unchanged_target_corners=len(targets)-len(mapped),
            maximum_native_target_degrees=max(angle(a,b) for a,b in zip(targets,actual)),codec=result,
            complete_field={'maximum_degrees':max(bounds),'triangles':len(bounds),'method':'Degree-two cross/dot Bernstein convex bounds, ordinary binary64 arithmetic.'})
        mesh.attributes.remove(mesh.attributes[POST])
        return {'proof':self.proof,'targets':targets,'native':actual,'before_normals':current,'selected_loops':sorted(mapped),
            'faces':face_rows,'source_parameters':self.vertex_parameters,'source_faces':self.source,'retained_targets':self.plans,
            'edge_recoveries':self.recovered,'boundary_joins':self.joins,'final_boundary_mapping':final_joins}

def capture(mesh,parameters,point):return Targets(mesh,parameters,point)
