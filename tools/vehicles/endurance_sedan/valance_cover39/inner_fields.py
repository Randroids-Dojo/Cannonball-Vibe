"""Current-input cover construction: inner_fields. Source provenance is in the private port manifest."""

import copy

import math

from collections import defaultdict

import numpy as np

def prepare(row, base, declaration, closest, complete):
    def triplets(value, size):
        if not isinstance(value,list) or len(value)!=size:raise ValueError('Malformed finite declaration')
        for v in value:
            if not isinstance(v,list) or len(v)!=3 or any(isinstance(q,bool) or not isinstance(q,(int,float)) or not math.isfinite(q) for q in v):raise ValueError('Malformed finite triplet')
        return value
    def unit(value):
        n=np.asarray(value,dtype=float); length=float(np.linalg.norm(n))
        if not math.isfinite(length) or length<.5:raise ValueError('Invalid actual current field')
        return (n/length).tolist()
    def angle(a,b):return float(np.degrees(np.arctan2(np.linalg.norm(np.cross(a,b)),np.dot(a,b))))
    def weights(p,t):
        a,b,c=t; ab=b-a; ac=c-a; ap=p-a
        x=np.linalg.solve([[ab@ab,ab@ac],[ab@ac,ac@ac]],[ab@ap,ac@ap]);w=np.maximum(0,np.asarray([1-x.sum(),x[0],x[1]]));return w/w.sum()
    for packet in (row,base):
        values=packet.get('requested_triangle_normals')
        if not isinstance(values,list) or len(values)!=len(packet['triangles']):raise ValueError('Incomplete actual current corner field')
        for ns in values:
            triplets(ns,3)
            if any(abs(math.hypot(*n)-1)>1e-6 for n in ns):raise ValueError('Invalid actual current unit field')
    if row['name']!='LOD0_RearLowerValance' or base['name']!=row['name']:raise ValueError('Wrong inner field semantic')
    if row['materials']!=['Material_Trim']:raise ValueError('Unexpected current cover material')
    if len(declaration)!=5:raise ValueError('Exactly five declared finite base facets required')
    bv=np.asarray(base['vertices']);bt=bv[np.asarray(base['triangles'])];vv=np.asarray(row['vertices']);tt=vv[np.asarray(row['triangles'])]
    declared={};original_rows=[]
    for entry in declaration:
        points=triplets(entry['oriented_base_points'],3)
        matches=[i for i,t in enumerate(bt) if base['triangle_domains'][i]=='inner' and t.tolist()==points]
        if len(matches)!=1:raise ValueError('Declared original finite facet lacks unique oriented current match')
        owner=matches[0]
        if owner in declared:raise ValueError('Duplicate current finite owner')
        # Values are read from the current base, not the declaration fields.
        declared[owner]=entry;original_rows.append(dict(owner=owner,points=bt[owner].tolist(),requested_normals=copy.deepcopy(base['requested_triangle_normals'][owner])))
    selected={};current_owner={};mapping={}
    for i,d in enumerate(row['triangle_domains']):
        if d!='inner_preserved_fragment':continue
        t=tt[i];owners=[]
        for owner in declared:
            if np.any(bt[owner].min(0)>t.max(0)+2e-7) or np.any(bt[owner].max(0)<t.min(0)-2e-7):continue
            q=np.asarray([closest(p,bt[owner]) for p in t]);bound=float(np.linalg.norm(q-t,axis=1).max())
            if bound<=2e-7:owners.append((bound,owner,q))
        if not owners:continue
        bound,owner,q=min(owners,key=lambda x:(x[0],x[1]));w=np.asarray([weights(p,bt[owner]) for p in q]);a=w@np.asarray(base['requested_triangle_normals'][owner])
        selected[i]=[unit(n) for n in a];current_owner[i]=owner;mapping[i]=dict(original_barycentric=w.tolist(),whole_affine_position_bound_m=bound)
    if len(selected)!=7 or set(current_owner.values())!=set(declared):raise ValueError('Complete current seven-fragment finite ownership mismatch')
    edges=defaultdict(list)
    for i,t in enumerate(row['triangles']):
        for a,b in zip(t,t[1:]+t[:1]):edges[tuple(sorted((a,b)))].append(i)
    if any(len(p)!=2 for p in edges.values()):raise ValueError('Input lacks closed two-face edge incidence')
    boundary=[];fixed=defaultdict(list);lower=set();existing=defaultdict(list)
    for i,ns in selected.items():
        for v,n in zip(row['triangles'][i],ns):existing[v].append((i,n))
    for edge,uses in edges.items():
        if len(set(uses)&set(selected))!=1:continue
        i=next(i for i in uses if i in selected);j=next(j for j in uses if j not in selected)
        if row['triangle_domains'][j]=='authored_inner_front':
            if any(vv[v,2]!=float(np.float32(.275)) for v in edge):raise ValueError('Authored fan boundary left fixed upper level')
            lower.update(edge);kind='coplanar_lower'
        elif row['triangle_domains'][j]=='inner_preserved_fragment':
            kind='protected'
            for v in edge:fixed[v].append((j,row['requested_triangle_normals'][j][row['triangles'][j].index(v)]))
        else:raise ValueError('Unexpected unowned field boundary')
        boundary.append(dict(edge=list(edge),inside=i,outside=j,kind=kind))
    if sum(q['kind']=='protected' for q in boundary)!=6 or sum(q['kind']=='coplanar_lower' for q in boundary)!=5 or len(lower)!=7:raise ValueError('Complete fixed boundary inventory mismatch')
    common={}
    for v,choices in existing.items():
        available=fixed.get(v) or choices
        # The selected direction is an actual current boundary field value.
        # Stable geometric ordering avoids relying on incidental triangle IDs.
        _,n=min(available,key=lambda q:tuple(float(x) for x in tt[q[0]].reshape(-1)))
        n=unit(n)
        if any(angle(n,b)>.025 for _,b in available):raise ValueError('Incompatible fixed current boundary directions')
        common[v]=n
    result=copy.deepcopy(row);ns=result['requested_triangle_normals'];allowed=set();fans=[]
    for i in selected:
        ns[i]=[common[v] for v in row['triangles'][i]];allowed.update((i,k) for k in range(3))
    for i,t in enumerate(row['triangles']):
        if row['triangle_domains'][i]!='authored_inner_front' or not set(t)&lower:continue
        fans.append(i)
        for k,v in enumerate(t):
            if v in lower:ns[i][k]=common[v];allowed.add((i,k))
    if len(fans)!=15:raise ValueError('Complete lower incident-fan inventory mismatch')
    # No other corner is reassigned; genuine independently owned cap/return
    # spaces and all unrelated original fields remain verbatim.
    changed=[]
    for i,(before,after) in enumerate(zip(row['requested_triangle_normals'],ns)):
        for k,(a,b) in enumerate(zip(before,after)):
            if a!=b:
                if (i,k) not in allowed:raise ValueError('Unowned corner field changed')
                changed.append(dict(triangle=i,corner=k,vertex=row['triangles'][i][k],before=a,after=b,change_degrees=angle(a,b)))
            if not all(math.isfinite(v) for v in b) or abs(math.hypot(*b)-1)>1e-6:raise ValueError('New field target is not unit')
    boundary_proofs=[]
    for q in boundary:
        edge=q['edge'];a=[ns[q['inside']][row['triangles'][q['inside']].index(v)] for v in edge];b=[ns[q['outside']][row['triangles'][q['outside']].index(v)] for v in edge]
        proof=complete([a[0],a[1],a[0]],[b[0],b[1],b[0]])
        boundary_proofs.append(dict(**q,complete_requested_edge=proof))
    for key in row:
        if key!='requested_triangle_normals' and result[key]!=row[key]:raise ValueError('Non-normal field changed')
    result['normal_authorship422']=dict(original_finite_owners=original_rows,current_fragments=sorted(selected),current_fragment_owners=current_owner,current_fragment_mapping=mapping,authored_inner_front_fans=fans,lower_boundary_vertices=sorted(lower),allowed_corners=[list(x) for x in sorted(allowed)],changed_corners=changed,common_boundary_targets={v:common[v] for v in sorted(common)},complete_boundary_fields=boundary_proofs,unowned_requested_corners_exact=True,geometry_uv_materials_exact=True,scope='Five actual finite base inner-facet domains and only the declared lower boundary corners in fifteen already-authored incident faces. No old whole-field preservation claim within this new domain;0.025degree native target encoding remains mandatory.')
    return result
