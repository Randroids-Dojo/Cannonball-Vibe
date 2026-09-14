"""Source-driven finite finish stage: 54 seat groups and 14 header/latch groups.

No source revision, historical geometry, preparation report or model constructor
is loaded. Missing or legacy seat components fail the explicit inventory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
import numpy as np
from mathutils import Vector
import finish_interfaces as fi
from geometry import Mesh
import seat_finite_geometry as finite
import seat_finish_report as validation

GUARD=1e-6
SEATS=('FrontL','FrontR','RearL','RearR')
OLD_FOAM=('CushionInsert','ThighBolster-1','ThighBolster1',
          'BackInsert','BackBolster-1','BackBolster1')


def inventory(rows):
    names=set(rows)
    entries=validation.expected_inventory(names)
    for entry in entries:
        for name in entry['pair']:
            fi.require(name in names,'Required finite interface mesh missing: '+name)
            fi.require(rows[name].get('properties',{}).get('source_preview_only') is not True,
                       'Required shipping interface cannot be preview-only: '+name)
    for seat in SEATS:
        forbidden=['LOD0_'+seat+part for part in OLD_FOAM]
        if seat.startswith('Front'):
            forbidden.append('LOD0_'+seat+'CushionSeam0')
        fi.require(not names.intersection(forbidden),'Legacy duplicate seat component remains: '+str(sorted(names.intersection(forbidden))))
    return entries


def post_parameters(row):
    points=np.asarray(row['vertices'],dtype=float)
    fi.require(points.shape==(16,3),'Headrest post requires two ordered eight-corner rings')
    first,second=points[:8],points[8:]
    c0,c1=first.mean(0),second.mean(0)
    length=float(np.linalg.norm(c1-c0));fi.require(length>GUARD,'Zero post axis')
    axis=(c1-c0)/length
    fi.require(axis[2]>0,'Headrest post axis must run from lower to upper endpoint')
    planarity=max(float(abs((first-c0)@axis).max()),float(abs((second-c1)@axis).max()))
    translation=float(np.linalg.norm(second-first-(c1-c0),axis=1).max())
    fi.require(planarity<=GUARD and translation<=GUARD,'Nonprismatic headrest post rings')
    finite.cap(row,axis,float(axis@c0));finite.cap(row,axis,float(axis@c1))
    return {'axis':axis.tolist(),'center0':c0.tolist(),'center1':c1.tolist(),'length_m':length,
            'ring_planarity_m':planarity,'ring_translation_error_m':translation}


def support_planes(carrier):
    """Supporting planes of the CURRENT carrier, including its actual openings.

    Every constant encloses every actual carrier vertex. Hole-wall planes that
    cut the carrier are excluded. No original uncut carrier is reconstructed.
    """
    points=np.array(carrier['vertices']);tri=fi.triangles(carrier)
    normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    original=np.einsum('ij,ij->i',normals,tri[:,0])
    maxima=(points@normals.T).max(0)
    ids=np.flatnonzero(maxima-original<=GUARD)
    fi.require(len(ids)>=4,'Insufficient current carrier supporting planes')
    # Duplicate planes are harmless; preserving each actual triangle owner
    # avoids an approximate plane-bucket equivalence assertion.
    ns,ds=normals[ids],maxima[ids]
    point=points.mean(0)
    fi.require(float((ds-ns@point).min())>GUARD,'No strict current carrier core reference')
    return ns,ds,ids,point


def rigid_joint(foam,carrier):
    normal,constants,owners,point=support_planes(carrier)
    fragments=finite.clipped_boundary(foam,normal,constants,GUARD)
    containment=float((np.array(carrier['vertices'])@normal.T-constants).max())
    outside=Mesh(foam).inside(Vector(point))
    certified_outside=outside is not None and all(q%2==0 for q in outside['ray_hit_counts'])
    selected=[]
    for index,tri in enumerate(fi.triangles(foam)):
        n=fi.unit(np.cross(tri[1]-tri[0],tri[2]-tri[0]))
        ids=np.flatnonzero((normal@n<-.9999)&(np.max(abs(normal@tri.T-constants[:,None]),axis=1)<=GUARD))
        if len(ids):
            selected.append(index)
    support=fi.surface_cover(fi.subset(foam,selected,'_finite_opposed_caps'),carrier) if selected else {'status':'failed_no_finite_caps'}
    area=sum(float(np.linalg.norm(np.cross(tri[1]-tri[0],tri[2]-tri[0])))/2 for tri in fi.triangles(foam)[selected])
    return {'status':'passed' if not fragments and containment<=GUARD and certified_outside and support['status']=='passed' and area>0 else 'failed',
            'current_carrier_supporting_planes':[{'actual_face':int(i),'outward':n.tolist(),'constant_m':float(d)} for i,n,d in zip(owners,normal,constants)],
            'actual_carrier_complete_halfspace_containment_m':containment,
            'complete_foam_triangles':len(foam['triangles']),'carrier_interior_guard_m':GUARD,
            'foam_boundary_inside_contracted_carrier':fragments,
            'carrier_interior_reference_m':point.tolist(),'interior_outside_foam_three_rays':outside,
            'opposed_finite_contact_triangles':selected,'finite_contact_area_m2':area,
            'complete_actual_carrier_support':support,
            'scope':'All actual carrier vertices lie inside current supporting halfspaces. All original foam boundary triangles are excluded from their connected contracted intersection and a strict interior reference is outside foam. Complete opposed contact faces have actual carrier support. No historical carrier or open-ended pair exemption is used.'}


def pouch_parameters(backing):
    tri=fi.triangles(backing)
    n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);area=np.linalg.norm(n,axis=1);n/=area[:,None]
    expected=np.array([0.,-math.cos(math.radians(18)),-math.sin(math.radians(18))])
    ids=np.flatnonzero(n@expected>1-1e-8)
    fi.require(len(ids)>0,'Missing actual raked map-pouch mounting plane')
    index=int(max(ids,key=lambda i:area[i]))
    return {'actual_rear_normal':n[index].tolist(),'plane_constant':float(n[index]@tri[index,0]),
            'actual_carrier_face':index}


def mirror(row,sign):
    result=copy.deepcopy(row)
    if sign<0:
        result['vertices']=[[-v[0],v[1],v[2]] for v in row['vertices']]
        result['triangles']=[list(reversed(t)) for t in row['triangles']]
    return result


def stitch_joint(row,foam):
    result=finite.sewn(row,foam,.0006,np.eye(3),.15*.0006)
    if 'complete_local_boundary' in result:
        maximum=max(p[2] for f in result['complete_local_boundary'] for p in f['polygon_local_m'])
        margin=result['complete_prism_bounds_m'][1][2]-maximum
        result['entire_top_plane_boundary_clearance_m']=margin
        if margin<=GUARD:
            result['status']='failed_no_complete_top_plane_separation'
    return result


def welt_joint(row,foam,rear):
    maximum=.004 if rear else .0016
    volume=finite.certificate(row,foam,maximum=maximum)
    contact=fi.inspect_pair({row['name']:row,foam['name']:foam},('sewn_upholstery',row['name'],foam['name']))
    route=contact['complete_route_spans']
    common={'whole_solid':volume,'maximum_whole_solid_distance_allowed_m':maximum,
            'complete_route_spans':route,'actual_original_route_contacts':contact['exact_boundary_contacts'],
            'receiving_foam':foam['name']}
    if rear:
        embedding=finite.embedded_route(row,foam,route)
        route_length=sum(q['length_m'] for q in route)
        tucked=sum(q['length_m']*sum(b-a for a,b in q['uncovered_intervals']) for q in route)
        return {**common,'status':'passed' if volume['status']=='passed_complete_welt_solid_bound' and embedding['status']=='passed_complete_embedded_route' else 'failed',
                'embedded_gap_intervals':embedding,'original_route_length_m':route_length,
                'receiving_foam_embedded_route_length_m':tucked,'surface_contact_route_length_m':route_length-tucked,
                'construction_policy':'Original rear soft trim has at most 4 mm receiving-foam tuck; every original route interval has surface contact or a fully embedded finite core. No suspended visible interval is waived.'}
    complete=all(not q['uncovered_intervals'] for q in route)
    overlap=finite.finite_overlap(row,foam)
    return {**common,'status':'passed' if volume['status']=='passed_complete_welt_solid_bound' and complete and overlap else 'failed',
            'route_complete':complete,'positive_finite_overlap_witness':overlap,
            'construction_policy':'Front soft welt whole-solid envelope remains 1.6 mm with complete route contact and positive finite receiving-foam overlap.'}


def evaluate(rows,entry):
    kind=entry['kind'];names=entry['pair'];values=[rows[n] for n in names]
    if kind in ('header_butt','latch_flange','latch_screw'):
        result=fi.inspect_pair(rows,(kind,*names))
    elif kind=='seat_socket':
        params=post_parameters(values[0]);endpoint=0 if names[1].endswith('BackShell') else 1
        result=finite.socket(*values,params,endpoint)
        result.update(actual_post_parameters=params,endpoint=endpoint)
    elif kind=='seat_rigid':
        result=rigid_joint(*values)
    elif kind=='seat_pouch':
        params=pouch_parameters(values[1]);result=finite.pouch(*values,params)
        result['actual_mount_parameters']=params
    elif kind=='seat_switch':
        sign=1 if 'FrontL' in names[0] else -1
        pad,switch,frame=[mirror(v,sign) for v in values]
        low=float(np.array(switch['vertices'])[:,0].max())
        high=float(np.array(frame['vertices'])[:,0].min())
        fi.require(high>low+GUARD,'Missing finite switch mounting interval')
        result=finite.pad(pad,switch,frame,{'outer_plane_x':low,'inner_plane_x':high})
        result.update(actual_mount_planes_m=[low,high],original_coordinate_sign=sign)
    elif kind=='seat_cushion_stitch':
        result=stitch_joint(*values)
    elif kind in ('seat_front_welt','seat_rear_welt'):
        result=welt_joint(*values,rear=kind=='seat_rear_welt')
    else:
        raise ValueError('Undeclared finite domain: '+kind)
    result['status']='passed' if result['status'] in ('passed','passed_proposed_finite_sewn_domain') else 'failed'
    return {**result,**entry}


def translated(row,delta):
    result=copy.deepcopy(row)
    result['vertices']=(np.array(row['vertices'])+np.array(delta)).tolist()
    fi.validate_row(result['name'],result)
    return result


def negative_controls(rows,entries):
    controls=[]
    for entry in entries:
        kind=entry['kind'];name=entry['pair'][0];distances=[]
        if kind=='seat_socket':
            axis=np.array(post_parameters(rows[name])['axis'])
            distances=[(-.0002 if entry['pair'][1].endswith('BackShell') else .0002)*axis]
        elif kind=='seat_cushion_stitch':
            distances=[np.array([0.,0.,-.004])]
        elif kind=='seat_front_welt':
            distances=[-.004*np.array([0.,math.cos(math.radians(18)),math.sin(math.radians(18))])]
        elif kind=='seat_rear_welt':
            axis=np.array([0.,math.cos(math.radians(9)),math.sin(math.radians(9))])
            distances=[-.01*axis,.01*axis]
        elif kind=='seat_pouch':
            distances=[-.0002*np.array(pouch_parameters(rows[entry['pair'][1]])['actual_rear_normal'])]
        elif kind=='seat_switch':
            distances=[np.array([.0002 if 'FrontL' in name else -.0002,0.,0.])]
        elif kind=='seat_rigid':
            carrier=rows[entry['pair'][1]];_,_,_,point=support_planes(carrier)
            changed=finite.add_box(rows[name],point-.0001,point+.0001)
            fi.validate_row(changed['name'],changed)
            result=evaluate(rows|{name:changed},entry)
            controls.append({'name':validation.control_id(entry,0),'kind':kind,'pair':entry['pair'],
                             'mutation':'Added separate closed 200 um cube strictly within current carrier core; original contact faces unchanged',
                             'rejected':result['status']=='failed','result':result})
        elif kind in ('header_butt','latch_flange','latch_screw'):
            # Keep the established six representative header/latch controls.
            representative=next(q for q in entries if q['kind']==kind)
            if entry!=representative: continue
            if kind=='header_butt':
                name=entry['pair'][1];axis=np.array([0.,1.,0.])
            else:
                property_name='fitted_latch_seat' if kind=='latch_flange' else 'fitted_fastener_seat'
                axis=fi.unit(fi.contract(rows[name],property_name)['outward_normal'])
            distances=[-.0001*axis,.0001*axis]
        for index,delta in enumerate(distances):
            changed=translated(rows[name],delta)
            try: result=evaluate(rows|{name:changed},entry)
            except (ValueError,AssertionError) as error: result={'status':'failed','failure':str(error)}
            controls.append({'name':validation.control_id(entry,index),'kind':kind,'pair':entry['pair'],
                             'translated_mesh':name,'closed_translation_m':delta.tolist(),
                             'rejected':result['status']=='failed','result':result})
    controls.append(fi.crossing_pad_control())
    return controls


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    fi.require(not args.output.exists(),'Choose a fresh report path')
    fi.require(args.output.resolve()!=args.geometry.resolve(),'Output must not replace geometry')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();inputs={}
    report={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),
            'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,
            'blender':bpy.app.version_string,'blender_build':bpy.app.build_hash.decode(),
            'status':'failed','source_sha256':None,'human_approval_reference':None,'guard_m':GUARD,
            'schema':'finite-seat-finish-v1','scope':'68 explicit finite groups only: 54 current-source seat groups and 14 unchanged header/latch groups. Other contacts, full motion, individual source self validity, LODs, export, runtime, appearance and human gates remain separate.'}
    try:
        payload=fi.strict_json(gzip.decompress(args.geometry.read_bytes()))
        fi.require(isinstance(payload,dict) and isinstance(payload.get('meshes'),dict),'Actual extracted geometry required')
        source=Path(payload['source_path']);source_sha=payload['source_sha256']
        validation.digest(source_sha)
        fi.require(source.is_file() and fi.sha(source)==source_sha,'Actual source hash mismatch')
        report.update(source_sha256=source_sha,geometry_payload_sha256=fi.sha(args.geometry))
        dependencies=[args.geometry,source,*[Path(__file__).with_name(n) for n in validation.DEPENDENCIES]]
        inputs={str(p.resolve()):fi.sha(p) for p in dependencies}
        try: report['git_revision']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        except (OSError,subprocess.CalledProcessError): report['git_revision']=None
        rows=payload['meshes'];entries=inventory(rows)
        report['exact_named_inventory']=entries
        for name in sorted({n for e in entries for n in e['pair']}):
            fi.validate_row(name,rows[name])
        results=[];report['results']=results
        for entry in entries:
            try: result=evaluate(rows,entry)
            except (ValueError,AssertionError) as error: result={**entry,'status':'failed','failure':str(error)}
            results.append(result)
            print(json.dumps({'kind':entry['kind'],'pair':entry['pair'],'status':result['status']}),flush=True)
        controls=negative_controls(rows,entries)
        report.update(interface_count=len(results),seat_interface_count=54,header_latch_interface_count=14,
                      negative_control_count=len(controls),negative_controls=controls,
                      status='passed' if all(r['status']=='passed' for r in results) and all(r['rejected'] for r in controls) else 'failed')
    except Exception as error:
        report.update(status='failed',failure=type(error).__name__+': '+str(error))
    finally:
        unchanged=all(Path(path).is_file() and fi.sha(path)==sha for path,sha in inputs.items())
        report.update(inputs=[{'path':p,'sha256':sha} for p,sha in inputs.items()],inputs_unchanged=unchanged,
                      elapsed_seconds=time.monotonic()-started)
        if not unchanged: report.update(status='failed',failure='Input changed during finite proof')
        if report['status']=='passed':
            try: report['validated_summary']=validation.validate_report(report,report['source_sha256'])
            except ValueError as error: report.update(status='failed',failure='Report validation: '+str(error))
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'status':report['status'],'interfaces':report.get('interface_count'),'output':str(args.output)}),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None))
