"""Complete finite mounting contacts and changed-five/current-global rest pairs."""
from .contracts import NAMES, RECEIVER, require, geometry_binding, digest
from . import coverage, finite_cells


def finite(actual, requested, providers):
    fi=providers.fi; cover=actual[NAMES[0]]; body=actual[RECEIVER]
    ids=[i for i,d in enumerate(requested[NAMES[0]]['triangle_domains'])
         if d in ('inner_preserved_fragment','terminal_inner','formed_side_inner','authored_inner_front')]
    require(ids,'Missing complete actual receiving inner sheet')
    inner=fi.subset(cover,ids,'_complete_inner')
    joints=[];controls=[]
    for name in NAMES[1:]:
        row=actual[name];plan=requested[name];f=plan['finite_interfaces']
        caps=[('body_land',f['body_land_triangles'],body),
              ('cover_left',f['cover_left']['triangles'],inner),
              ('cover_right',f['cover_right']['triangles'],inner)]
        footprints={}
        for label,indices,target in caps:
            require(type(indices) is list and indices and len(set(indices))==len(indices)
                    and all(type(i) is int and 0<=i<len(row['triangles']) for i in indices),
                    'Incomplete actual finite cap: '+name+'/'+label)
            cap=fi.subset(row,indices,'_'+label)
            footprints[label]={'triangles':indices,'coverage':coverage.cover(cap,target,fi)}
            for delta in (-.0002,.0002):
                shifted={**cap,'vertices':[[x,y+delta,z] for x,y,z in cap['vertices']]}
                result=coverage.cover(shifted,target,fi)
                controls.append({'name':name,'cap':label,'translation_y_m':delta,
                                 'coverage':result,'rejected':result['status']!='passed'})
        for target,kind,labels in ((body,'body',['body_land']),
                                  (cover,'cover',['cover_left','cover_right'])):
            cap_ids=[i for label in labels for i in footprints[label]['triangles']]
            full=finite_cells.full_contact(row,plan,target,cap_ids,providers.exact,fi,coverage,providers.geometry)
            passed=full['status']=='passed' and all(footprints[l]['coverage']['status']=='passed' for l in labels)
            pair=sorted((name,target['name']))
            proof={'schema':'source-valance-cover39.finite-joint.v1','pair':pair,
                   'status':'passed' if passed else 'failed','mount':name,'receiving_domain':kind,
                   'geometry_bindings':{r['name']:geometry_binding(r) for r in (row,target)},
                   'actual_finite_cap_footprints':{l:footprints[l] for l in labels},
                   'complete_contact':full,'guard_m':1e-6,
                   'scope':'Only the complete named cap surfaces in this current geometry-bound pair; no other pair exemption.'}
            proof['certificate_sha256']=digest(proof)
            joints.append(proof)
    require(len(joints)==8 and len({tuple(p['pair']) for p in joints})==8,'Missing complete joint inventory')
    require(len(controls)==24,'Missing displaced complete cap controls')
    return {'status':'passed' if all(p['status']=='passed' for p in joints) and all(c['rejected'] for c in controls) else 'failed',
            'finite_joints':joints,'displaced_cap_controls':controls,'complete_cap_count':12}


def rest(rows, joints, providers):
    expected={tuple(sorted((mount,target))) for mount in NAMES[1:] for target in (NAMES[0],RECEIVER)}
    require({tuple(j['pair']) for j in joints}==expected and len(joints)==8,'Incomplete named joint consumption')
    certificates={tuple(j['pair']):j for j in joints}
    for pair,joint in certificates.items():
        require(joint['geometry_bindings']=={n:geometry_binding(rows[n]) for n in pair},'Stale finite certificate geometry')
        require(joint['certificate_sha256']==digest({k:v for k,v in joint.items() if k!='certificate_sha256'}),'Altered finite certificate')
    geometry=providers.geometry
    boxes={n:geometry.bounds(r['vertices']) for n,r in rows.items()}
    distance=providers.Distances(rows)
    all_pairs=sorted({tuple(sorted((name,other))) for name in NAMES for other in rows if name!=other})
    pairs=[]
    for pair in all_pairs:
        a,b=pair
        if pair in certificates:
            proof=certificates[pair]
            pairs.append({'pair':list(pair),'status':'passed_finite_boundary_caps' if proof['status']=='passed' else 'failed_finite_boundary_caps',
                          'certificate_sha256':proof['certificate_sha256']})
            continue
        lower=geometry.box_distance2(boxes[a],boxes[b])**.5
        if lower>=.001001:
            pairs.append({'pair':list(pair),'status':'passed_complete_aabb','lower_bound_m':lower})
            continue
        result=distance.minimum(a,b)
        pairs.append({'pair':list(pair),'status':'passed_complete_nonmate' if result['distance_m']>=.001001 else 'failed_nonmate',
                      'measurement':result})
    failures=[p for p in pairs if p['status'].startswith('failed')]
    require(len(pairs)==5*len(rows)-15,'Incomplete changed-five/global pair domain')
    return {'status':'passed' if not failures else 'failed','pairs':pairs,'pair_count':len(pairs),
            'finite_joint_pairs':[list(p) for p in sorted(expected)],'failures':failures,
            'complete_global_geometry_bindings':{n:geometry_binding(r) for n,r in sorted(rows.items())},
            'clearance_m':.001001,'global_containment_and_continuous_openings':'separate mandatory source stages'}
