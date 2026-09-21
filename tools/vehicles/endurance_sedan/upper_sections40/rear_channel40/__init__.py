"""Actual-input construction of the paired rear channel, receiver and supports.

This package performs no file IO and has no Blender dependency. Every point
comes from current role geometry and stated dimensional construction rules.
It returns private arrays; the caller owns native staging and verification.
"""
import copy, math
from .contract import CONTRACT
from .vectors import f32, unit, sub, cross
from .mesh import empty, old_face, new_face
from . import receiver, channel, supports, maths, bounded_stock

NORMAL_PARENTS = {
    'LOD0_Door_RR': (511,513,531,532,533,534,547,548,549,550,719,720,721,722,1042,1057),
    'LOD0_Door_RL': (451,453,519,520,521,522,535,536,537,538,695,696,697,698,1001,1009,1010),
    'LOD0_StampedPillar_BR': (20,21), 'LOD0_StampedPillar_BL': (20,21),
}
RETAINED = ('retained','retained_fragment','retained_cap_fragment')


def _face_records(row, faces):
    return [{'face':i,'indices':row['triangles'][i][:],
             'positions_m':[row['vertices'][v][:] for v in row['triangles'][i]],
             'material':row['materials'][row['triangle_materials'][i]]} for i in faces]


def _weights(p,a,b,c):
    u,v,w=sub(b,a),sub(c,a),sub(p,a); n=cross(u,v)
    drop=max(range(3),key=lambda k:abs(n[k])); i,j=[k for k in range(3) if k!=drop]
    den=u[i]*v[j]-u[j]*v[i]
    if abs(den)<1e-18: raise ValueError('Degenerate original field triangle')
    y=(w[i]*v[j]-w[j]*v[i])/den; z=(u[i]*w[j]-u[j]*w[i])/den
    return [1-y-z,y,z]


def _actual_reference_fields(old,row):
    """Transport once from the actual input field at actual native points.

    Encoding is subsequently checked directly against this same source over
    the whole retained triangle. There is no accumulated angular allowance.
    The declared incident parents have a new normalized-corner interpolation.
    Geometry, UV, material and the geometry-domain labels are untouched.
    """
    revision=set(NORMAL_PARENTS.get(old['name'],()))
    authored=[]
    for i,(t,d,owner) in enumerate(zip(row['triangles'],row['domains'],row['owners'])):
        if d not in RETAINED: continue
        ls=old['triangle_loops'][owner]; ot=old['triangles'][owner]
        ns=[]
        for v in t:
            if v in ot and row['vertices'][v]==old['vertices'][v]:
                ns.append(old['normals'][ls[ot.index(v)]][:]); continue
            w=_weights(row['vertices'][v],*[old['vertices'][q] for q in ot])
            ns.append(unit([sum(w[j]*old['normals'][ls[j]][k] for j in range(3)) for k in range(3)]))
        row['normal_corner_targets'][i]=ns
        if owner in revision: authored.append(i)
    row['normal_domain_revision']={'revision':54,'source_parents':sorted(revision),
        'new_interpolation_faces':authored,'outside_claim':'complete original normalized field, 0.025 degree native bound',
        'inside_claim':'new interpolation of original transported corner/source directions'}


def _lobe(old, vertices, amount):
    row=empty(old); changed=set(vertices)
    owned={i for i,t in enumerate(old['triangles']) if any(v in changed for v in t)}
    for i in sorted(changed):
        p=old['vertices'][i]; ring=old['vertices'][8*(i//8):8*(i//8)+8]
        center=[sum(q[k] for q in ring)/8 for k in range(3)]
        direction=unit(sub(center,p)); row['vertices'][i]=f32([p[k]+amount*direction[k] for k in range(3)])
    for i,t in enumerate(old['triangles']):
        if i in owned: new_face(row,t,'authored_hidden_rubber_lobe',old['triangle_materials'][i],i)
        else: old_face(row,old,i)
    displacement=max(math.dist(old['vertices'][i],row['vertices'][i]) for i in changed)
    if displacement>.001501: raise ValueError('Hidden rubber retreat exceeded dimensional limit')
    return row,{'changed_vertices':sorted(changed),'owned_faces':sorted(owned),'net_triangles':0,
                'maximum_displacement_m':displacement}


def build(input_rows, contract=None, observe=None):
    """Return ten fresh role arrays, masks, construction references and counts.

    ``input_rows`` must contain the current evaluated native fields for the
    ten output roles plus both unchanged rear aperture seals. Topology is
    explicitly versioned. No archived shape, report or source path is read.
    ``observe`` is an optional diagnostic callback, never an acceptance test.
    """
    contract=CONTRACT if contract is None else contract
    rows=copy.deepcopy(input_rows); parts={}; construction={}; masks={}
    expected={'Door_RR':1652,'Door_RL':1660,'RoofSideRail_R':1420,'RoofSideRail_L':1412}
    for side in ('R','L'):
        expected.update({'DoorFrame_R'+side:300,'DoorGlassSeal_R'+side:400,'StampedPillar_B'+side:44})
    for suffix,count in expected.items():
        name='LOD0_'+suffix
        if len(rows[name]['triangles'])!=count: raise ValueError(('Input role topology drift',name,count))
        if rows[name].get('name',name)!=name: raise ValueError('Input role identity drift')
        rows[name]['name']=name
    for side in ('R','L'):
        s=contract['sides'][side]
        dn='LOD0_Door_R'+side; sn='LOD0_DoorGlassSeal_R'+side; fn='LOD0_DoorFrame_R'+side
        rn='LOD0_RoofSideRail_'+side; bn='LOD0_StampedPillar_B'+side
        rail_ref=_face_records(rows[rn],s['rail_lower_reference_faces'])
        rs=supports.receiving_wall_scope(rows,side,rail_ref)
        bs={'object':bn,'aft_cap_faces':_face_records(rows[bn],s['B_root_faces'])}
        masks[side]={'Door':{'unchanged_top_parents':s['Door_top_faces'][:],
              'complete_end_band_parents':_face_records(rows[dn],s['Door_end_faces'])},
            'lobe_vertices':s['lobe_vertices'][:],
            'sash':{'complete_inward_parent_faces':_face_records(rows[fn],s['sash_inward_faces'])},
            'fixed_rail':rs,'fixed_B_return':bs}
    if observe: observe('frozen_input_masks',copy.deepcopy(masks))
    for side in ('R','L'):
        s=contract['sides'][side]; mask=masks[side]
        dn='LOD0_Door_R'+side; sn='LOD0_DoorGlassSeal_R'+side; fn='LOD0_DoorFrame_R'+side
        for name,entry in ((dn,receiver.build(rows[dn],mask['Door'],side)),
                           (sn,_lobe(rows[sn],s['lobe_vertices'],contract['lobe_retreat_m']))):
            parts[name],construction[name]=entry; rows[name]=entry[0]
        parts[fn],construction[fn]=channel.build(rows,side,{'sash':mask['sash']},bounded_stock.plane_miter)
        rows[fn]=parts[fn]
    for side in ('R','L'):
        for kind,key in (('rail','fixed_rail'),('B','fixed_B_return')):
            mask=masks[side][key]; name=mask['object']
            parts[name],construction[name]=supports.build(rows,side,kind,mask,maths.plane_miter)
            rows[name]=parts[name]
    for name,row in parts.items():
        _actual_reference_fields(input_rows[name],row)
    return {'parts':parts,'construction':construction,'source_masks':masks,
            'net_triangles':sum(len(row['triangles'])-len(input_rows[n]['triangles']) for n,row in parts.items()),
            'field_revision':54,'fresh_input_only':True}
