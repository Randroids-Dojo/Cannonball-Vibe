"""Fail-closed current-row field/scope checks; caller injects finite geometry tools."""
import math


def angle(a,b):
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross),sum(x*y for x,y in zip(a,b))))


def validate(original,raw,new,hose,metric,*,coverage,field_check,reverse_check):
    if original['name']!=raw['name'] or new['name']!=raw['name'] or new['name']!='LOD0_RadiatorStack':
        raise ValueError('Wrong named radiator field domain')
    if any(raw[k]!=new[k] for k in raw if k not in ('normals','uvs')):
        raise ValueError('Restoration changed non-field geometry/material data')
    if set(raw['uvs'])!=set(new['uvs']) or set(original['uvs'])!=set(new['uvs']):
        raise ValueError('Changed UV channel inventory')
    for normal in new['normals']:
        if len(normal)!=3 or not all(math.isfinite(x) for x in normal) or abs(math.hypot(*normal)-1)>1e-6:
            raise ValueError('Invalid native normal')
    loops={q['loop'] for q in metric['retained_corner_charts']}
    if not loops or any(type(i) is not int or not 0<=i<len(new['normals']) for i in loops):
        raise ValueError('Missing retained face inventory')
    retained=[];pocket=[];pocket_loops=set()
    for i,tri in enumerate(new['triangle_loops']):
        flags=[j in loops for j in tri]
        if any(flags) and not all(flags):raise ValueError('Mixed original/pocket field ownership')
        if all(flags):retained.append(i)
        else:pocket.append(i);pocket_loops.update(tri)
    for i in pocket_loops:
        for name in new['uvs']:
            if new['uvs'][name][i]!=raw['uvs'][name][i]:raise ValueError('Authored pocket UV changed')
        if angle(new['normals'][i],raw['normals'][i])>.025:raise ValueError('Authored pocket native normal exceeds encoding guard')
    if not retained or not pocket:raise ValueError('Incomplete named surface inventory')
    part=lambda indices:{'name':new['name'],'vertices':new['vertices'],'triangles':[new['triangles'][i] for i in indices]}
    forward=coverage(part(retained),original,maximum=1e-6)
    if forward['status']!='passed':raise ValueError('Retained surface does not match current original')
    sockets=coverage(part(pocket),hose,maximum=1e-6)
    if sockets['status']!='passed':raise ValueError('Pocket lacks complete actual hose ownership')
    fields=field_check(original,new,retained)
    if fields['status']!='passed':raise ValueError('Complete original normal/UV field exceeds guard')
    reverse=reverse_check(original,new,hose)
    if reverse['status']!='passed':raise ValueError('Original outside actual hose not preserved')
    return {'status':'passed','retained_triangles':retained,'pocket_triangles':pocket,
            'restoration_geometry_topology_material_exact':True,'pocket_uv_exact':True,
            'maximum_pocket_normal_encoding_degrees':max(angle(new['normals'][i],raw['normals'][i]) for i in pocket_loops),
            'complete_retained_surface':forward,'complete_pocket_ownership':sockets,
            'complete_retained_field':fields,'reverse_outside_actual_hose':reverse}
