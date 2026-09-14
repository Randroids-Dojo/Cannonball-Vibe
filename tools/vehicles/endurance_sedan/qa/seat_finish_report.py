"""Standard-library host validation for the explicit 68-group finish report."""
import math
import re
import finish_report as old

GUARD=1e-6
DEPENDENCIES=('seat_finish_interfaces.py','seat_finish_report.py','seat_finite_geometry.py',
              'finish_interfaces.py','finish_report.py','precision.py','exact_triangles.py',
              'self_geometry.py','geometry.py','wiper_initial.py','wiper_interassembly.py','wipers.py')
require=old.require
number=old.number
count=old.count
digest=old.digest
nonempty=old.nonempty


def expected_inventory(names):
    names=set(names);entries=[]
    def add(kind,*members):
        pairs=[[members[0],n] for n in members[1:]]
        entries.append({'kind':kind,'pair':list(members),'certified_binary_pairs':pairs})
    for side in ('L','R'):
        add('header_butt','LOD0_PillarA_'+side,'LOD0_RoofSideRail_'+side)
    for suffix in ('FL','FR','RL','RR'):
        add('latch_flange','LOD0_DoorLatch_'+suffix,'LOD0_Door_'+suffix)
        screws=sorted(n for n in names if n.startswith('LOD0_LatchFastener_'+suffix))
        require(len(screws)==2,'Exactly two fitted latch screws per door')
        for name in screws:
            require(re.fullmatch('LOD0_LatchFastener_'+suffix+r'0\.(?:775|814)',name) is not None,
                    'Unexpected latch screw semantic name')
            add('latch_screw',name,'LOD0_DoorLatch_'+suffix)
    for seat in ('FrontL','FrontR','RearL','RearR'):
        base='LOD0_'+seat;front=seat.startswith('Front');foam=base+'JoinedUpholstery'
        for side in (-1,1):
            for target in ('BackShell','Headrest'):
                add('seat_socket',base+'HeadrestPost'+str(side),base+target)
        for target in ('BackShell','CushionFrame'):
            add('seat_rigid',foam,base+target)
        if front:
            add('seat_pouch',base+'MapPocket',base+'BackShell')
            add('seat_switch',base+'SeatSwitchMount',base+'SeatSwitch',base+'CushionFrame')
        for index in range(1 if front else 0,5):
            add('seat_cushion_stitch',base+'CushionSeam'+str(index),foam)
        for side in (-1,1):
            add('seat_front_welt' if front else 'seat_rear_welt',base+'BackPiping'+str(side),foam)
    require(len(entries)==68,'Internal declared inventory error')
    return entries


def control_id(entry,index):
    return entry['kind']+'|'+'|'.join(entry['pair'])+'|'+str(index)


def expected_controls(entries):
    result=[];seen=set()
    for entry in entries:
        kind=entry['kind']
        if kind in ('header_butt','latch_flange','latch_screw'):
            if kind in seen: continue
            seen.add(kind);n=2
        else:
            n=2 if kind=='seat_rear_welt' else 1
        result.extend(control_id(entry,i) for i in range(n))
    result.append('sewn_upholstery_intersecting_second_pad_layer')
    require(len(result)==65,'Internal negative inventory error')
    return result


def vector(value,n=3):
    require(isinstance(value,list) and len(value)==n,'Finite vector required')
    return [number(v) for v in value]


def interval(value):
    v=vector(value,2);require(v[0]<=v[1],'Ordered interval required');return v


def ray_parity(value,inside):
    require(isinstance(value,dict),'Native parity record missing')
    hits=value.get('ray_hit_counts')
    require(isinstance(hits,list) and len(hits)==3,'Exactly three rays required')
    require(all(count(h)%2==int(inside) for h in hits),'Contradictory native ray parity')
    require(value.get('inside_all_three_rays') is inside,'Contradictory native inside flag')
    require(number(value.get('surface_distance_m'))>GUARD,'Boundary-ambiguous parity point')
    vector(value.get('nearest_surface_source_m'))


def cover(value):
    old.cover(value)


def route_spans(value):
    spans=nonempty(value)
    require([q.get('segment') for q in spans]==list(range(len(spans))),'Complete ordered original route required')
    for row in spans:
        require(number(row.get('length_m'))>0,'Positive route span required')
        for key in ('contact_projection_intervals','uncovered_intervals'):
            require(isinstance(row.get(key),list),'Actual route interval inventory missing')
            for item in row[key]:
                a,b=interval(item);require(0<=a<=b<=1,'Invalid original route interval')
        # The route proof merges actual contact projections with the unchanged
        # spatial 1 um guard divided by this actual segment length.
        merged=[];guard=GUARD/row['length_m']
        for low,high in sorted(row['contact_projection_intervals']):
            if merged and low<=merged[-1][1]+guard:
                merged[-1][1]=max(high,merged[-1][1])
            else: merged.append([low,high])
        gaps=[];end=0.
        for low,high in merged:
            if low>end+guard: gaps.append([end,low])
            end=max(end,high)
        if end<1-guard: gaps.append([end,1.])
        require(merged==row['contact_projection_intervals'] and gaps==row['uncovered_intervals'],
                'Contact projections and uncovered route intervals disagree')
    return spans


def complete_interval_union(values,low,high):
    values=sorted(interval(v) for v in values)
    require(bool(values),'Missing complete-domain cells')
    cursor=low
    for a,b in values:
        require(a<=cursor+1e-12 and a>=low-1e-12 and b<=high+1e-12,'Uncovered or out-of-domain interval')
        cursor=max(cursor,b)
    require(cursor>=high-1e-12,'Incomplete terminal interval')


def whole_welt(value,limit):
    require(isinstance(value,dict) and value.get('status')=='passed_complete_welt_solid_bound','Failed complete welt solid')
    n=count(value.get('segments'));require(n>0,'No original welt segments')
    cells=nonempty(value.get('accepted_cells'));require(value.get('unresolved')==[],'Unresolved whole-solid domain')
    require(count(value.get('cells'))>=len(cells),'Invalid whole-solid cell accounting')
    for cell in cells:
        require(count(cell.get('segment'))<n,'Invalid solid segment')
        interval(cell.get('axial_interval_m'));count(cell.get('depth'));count(cell.get('foam_triangle'))
        require(count(cell.get('boundary_vertex_count'))>=4,'Missing complete slab boundary')
        require(0<=number(cell.get('complete_solid_convex_distance_upper_bound_m'))<=limit-1e-9,
                'Whole solid exceeds authored limit')
    require({q['segment'] for q in cells}==set(range(n)),'Missing whole-solid segment')
    domains=nonempty(value.get('segment_domains_m'))
    require([q.get('segment') for q in domains]==list(range(n)),'Missing actual whole-solid segment domains')
    for domain in domains:
        low,high=interval(domain.get('axial_interval_m'))
        complete_interval_union([q['axial_interval_m'] for q in cells if q['segment']==domain['segment']],low,high)
    maximum=max(q['complete_solid_convex_distance_upper_bound_m'] for q in cells)
    require(number(value.get('maximum_whole_solid_distance_m'))==maximum,'Contradictory maximum welt distance')


def validate_result(row):
    require(isinstance(row,dict) and row.get('status')=='passed','Failed finite group')
    kind=row.get('kind')
    if kind in ('header_butt','latch_flange','latch_screw'):
        old.validate_result(row);return
    if kind=='seat_socket':
        require(number(row.get('actual_post_enclosing_plane_residual_m'))<=1e-12,'Post outside complete prism')
        planes=nonempty(row.get('enclosing_prism_planes'));require(len(planes)==10,'Eight radial and two cap planes required')
        for plane in planes:
            n=vector(plane.get('outward'));require(abs(math.hypot(*n)-1)<1e-12,'Nonunit post halfspace')
            number(plane.get('constant_m'))
        require(number(row.get('radial_prism_expansion_m'))==.0003 and number(row.get('contraction_m'))==5e-7,'Post prism policy changed')
        require(count(row.get('complete_carrier_triangles'))>0 and row.get('carrier_boundary_in_contracted_post')==[],
                'Carrier enters complete post prism')
        ray_parity(row.get('interior_outside_carrier_three_rays'),False)
        cover(row.get('complete_actual_endpoint_support'))
        p=row.get('actual_post_parameters');require(isinstance(p,dict),'Actual post derivation missing')
        for key in ('axis','center0','center1'): vector(p.get(key))
        require(number(p.get('length_m'))>GUARD and number(p.get('ring_planarity_m'))<=GUARD
                and number(p.get('ring_translation_error_m'))<=GUARD,'Invalid post derivation')
        require(type(row.get('endpoint')) is int and row['endpoint'] in (0,1),'Actual endpoint missing')
    elif kind=='seat_rigid':
        planes=nonempty(row.get('current_carrier_supporting_planes'));require(len(planes)>=4,'Missing current carrier envelope')
        for p in planes:
            count(p.get('actual_face'));n=vector(p.get('outward'));number(p.get('constant_m'))
            require(abs(math.hypot(*n)-1)<1e-12,'Nonunit current support plane')
        require(number(row.get('actual_carrier_complete_halfspace_containment_m'))<=GUARD,'Carrier outside actual envelope')
        require(count(row.get('complete_foam_triangles'))>0 and number(row.get('carrier_interior_guard_m'))==GUARD,
                'Rigid complete-domain policy missing')
        require(row.get('foam_boundary_inside_contracted_carrier')==[],'Foam inside rigid carrier')
        vector(row.get('carrier_interior_reference_m'));ray_parity(row.get('interior_outside_foam_three_rays'),False)
        ids=nonempty(row.get('opposed_finite_contact_triangles'))
        require(len(set(ids))==len(ids) and all(count(i)<row['complete_foam_triangles'] for i in ids),'Invalid finite cap inventory')
        require(number(row.get('finite_contact_area_m2'))>0,'No finite rigid support')
        cover(row.get('complete_actual_carrier_support'))
        require(row['complete_actual_carrier_support']['full_triangles']==len(ids),'Incomplete actual cap coverage')
    elif kind=='seat_pouch':
        require(number(row.get('minimum_pouch_outward_m'))>=-GUARD and number(row.get('maximum_backing_outward_m'))<=GUARD,
                'Pouch/backing halfspace violation')
        cover(row.get('complete_mount_support'))
        p=row.get('actual_mount_parameters');require(isinstance(p,dict),'Pouch source plane absent')
        vector(p.get('actual_rear_normal'));number(p.get('plane_constant'));count(p.get('actual_carrier_face'))
    elif kind=='seat_switch':
        low,high=interval(row.get('actual_mount_planes_m'));a,b=interval(row.get('pad_interval_m'))
        require(high>low+GUARD and a>=low-GUARD and b<=high+GUARD,'Switch pad outside finite gap')
        require(number(row.get('switch_maximum_m'))<=low+GUARD and number(row.get('frame_minimum_m'))>=high-GUARD,
                'Switch/frame opposing halfspace violation')
        require(type(row.get('original_coordinate_sign')) is int and row['original_coordinate_sign'] in (-1,1),'Coordinate sign missing')
        supports=row.get('complete_cap_support');require(isinstance(supports,list) and len(supports)==2,'Both switch caps required')
        for p in supports: cover(p)
    elif kind=='seat_cushion_stitch':
        require(number(row.get('radius_m'))==.0006 and number(row.get('declared_maximum_intrusion_m'))==.15*.0006,
                'Unchanged 15%-radius stitch policy required')
        require(count(row.get('actual_all_foam_triangles_checked'))>0,'No complete foam domain')
        fragments=nonempty(row.get('complete_local_boundary'))
        require(row.get('non_front_boundary_fragments')==[],'Hidden crossing/back-facing layer')
        for f in fragments:
            require(count(f.get('foam_triangle'))<row['actual_all_foam_triangles_checked'],'Invalid local foam owner')
            require(number(f.get('outward_axis_component'))>0,'Nonfront chart ignored')
            for point in nonempty(f.get('polygon_local_m')): vector(point)
        prism=row.get('complete_prism_bounds_m')
        require(isinstance(prism,list) and len(prism)==2,'Missing complete thread prism')
        low,high=vector(prism[0]),vector(prism[1])
        require(all(a<b for a,b in zip(low,high)),'Degenerate local thread prism')
        boundary_max=max(p[2] for f in fragments for p in f['polygon_local_m'])
        require(number(row.get('entire_top_plane_boundary_clearance_m'))==high[2]-boundary_max,
                'Contradictory complete top-plane separation')
        ray_parity(row.get('prism_top_outside_foam_three_rays'),False)
        require(number(row.get('entire_top_plane_boundary_clearance_m'))>GUARD,'Missing whole top separation')
        old.validate_result(row.get('complete_local_cloth_proof'))
    elif kind in ('seat_front_welt','seat_rear_welt'):
        rear=kind=='seat_rear_welt';limit=.004 if rear else .0016
        require(number(row.get('maximum_whole_solid_distance_allowed_m'))==limit,'Authored front/rear soft-trim policy changed')
        whole_welt(row.get('whole_solid'),limit);spans=route_spans(row.get('complete_route_spans'))
        require(row.get('receiving_foam')==row['pair'][1],'Wrong receiving foam')
        if not rear:
            require(row.get('route_complete') is True and all(q['uncovered_intervals']==[] for q in spans),
                    'Suspended front welt route')
            witness=row.get('positive_finite_overlap_witness');require(isinstance(witness,dict),'No finite front sewn attachment')
            require(number(witness.get('interior_ball_radius_m'))>0,'No finite front overlap volume')
            ray_parity(witness.get('thread_inside'),True);ray_parity(witness.get('foam_inside'),True)
        else:
            embed=row.get('embedded_gap_intervals')
            require(isinstance(embed,dict) and embed.get('status')=='passed_complete_embedded_route'
                    and embed.get('unresolved_intervals')==[],'Unresolved rear route interval')
            require(number(embed.get('finite_core_radius_m'))==.00005,'Finite rear attachment core changed')
            cells=embed.get('intervals');require(isinstance(cells,list),'Missing rear embedding intervals')
            require(count(embed.get('cells'))>=len(cells),'Invalid embedded cell accounting')
            for cell in cells:
                require(count(cell.get('segment'))<len(spans),'Invalid embedded segment')
                interval(cell.get('original_route_interval'));count(cell.get('subdivision_depth'));vector(cell.get('center_m'))
                radius=number(cell.get('complete_capsule_enclosing_radius_m'))
                lower=number(cell.get('all_actual_boundary_distance_lower_bound_m'))
                require(radius>0 and number(cell.get('finite_embedded_core_radius_m'))==.00005 and lower>radius+GUARD,
                        'Embedded ball touches/crosses actual foam boundary')
                require(number(cell.get('whole_ball_clearance_margin_m'))==lower-radius,'Contradictory rear ball margin')
                require(count(cell.get('foam_triangles_total'))==count(cell.get('whole_aabb_exclusions'))+count(cell.get('exact_point_triangle_checks')),
                        'Incomplete foam boundary distance inventory')
                ray_parity(cell.get('point_inside_three_rays'),True)
            for span in spans:
                for low,high in span['uncovered_intervals']:
                    candidates=[q['original_route_interval'] for q in cells if q['segment']==span['segment']
                                and q['original_route_interval'][0]>=low-1e-12 and q['original_route_interval'][1]<=high+1e-12]
                    complete_interval_union(candidates,low,high)
            total=sum(q['length_m'] for q in spans)
            tucked=sum(q['length_m']*sum(b-a for a,b in q['uncovered_intervals']) for q in spans)
            require(number(row.get('original_route_length_m'))==total and number(row.get('receiving_foam_embedded_route_length_m'))==tucked
                    and number(row.get('surface_contact_route_length_m'))==total-tucked,'Contradictory original route lengths')
    else:
        raise ValueError('Unknown finite result kind')


def _validate_report(report,source_sha):
    require(isinstance(report,dict) and report.get('status')=='passed','Finish stage failed')
    require(report.get('schema')=='finite-seat-finish-v1','Wrong finite report schema')
    digest(source_sha);require(report.get('source_sha256')==source_sha,'Source hash mismatch')
    payload_hash=report.get('geometry_payload_sha256');digest(payload_hash)
    require(report.get('inputs_unchanged') is True and report.get('human_approval_reference') is None,
            'Invalid input or human-gate claim')
    require(number(report.get('guard_m'))==GUARD,'Geometry guard changed')
    require(count(report.get('interface_count'))==68 and count(report.get('seat_interface_count'))==54
            and count(report.get('header_latch_interface_count'))==14,'Finite inventory count mismatch')
    declarations=nonempty(report.get('exact_named_inventory'));results=nonempty(report.get('results'))
    names={name for e in declarations for name in e['pair']}
    expected=expected_inventory(names)
    require(declarations==expected and len(results)==68,'Incomplete/duplicate finite inventory')
    require([{k:r.get(k) for k in ('kind','pair','certified_binary_pairs')} for r in results]==declarations,
            'Result inventory differs from declared domains')
    for row in results: validate_result(row)
    controls=nonempty(report.get('negative_controls'))
    require(count(report.get('negative_control_count'))==65 and [r.get('name') for r in controls]==expected_controls(expected),
            'Missing/duplicate finite negative control')
    for row in controls:
        require(row.get('rejected') is True and isinstance(row.get('result'),dict)
                and (row['result'].get('status')=='failed' or bool(row['result'].get('failure'))),'Ineffective negative control')
    crossing=controls[-1];old.validate_result(crossing.get('baseline'));nonempty(crossing.get('exact_extra_layer_intersections'))
    require(crossing['result'].get('all_overlapping_front_charts_checked') is True,'Second-layer regression incomplete')
    require(old.bounds(crossing['result'].get('complete_surface_signed_distance_range_m'))[0]<-.15*.0006-GUARD,
            'Second-layer control did not reject measured intrusion')
    inputs=nonempty(report.get('inputs'));paths=[]
    for value in inputs:
        require(isinstance(value,dict) and isinstance(value.get('path'),str) and value['path'],'Invalid binding')
        digest(value.get('sha256'));paths.append(value['path'])
    require(len(set(paths))==len(paths),'Duplicate input binding')
    require(any(r['sha256']==source_sha and r['path'].lower().endswith('.blend') for r in inputs)
            and any(r['sha256']==payload_hash and r['path'].endswith('.json.gz') for r in inputs),'Actual source/payload binding missing')
    filenames={p.replace('\\','/').rsplit('/',1)[-1] for p in paths}
    require(set(DEPENDENCIES)<=filenames,'Missing reader dependency hashes')
    return {'interfaces':68,'seat_interfaces':54,'header_latch_interfaces':14,'certified_binary_pairs':70,
            'negative_controls':65,'unresolved':0}


def validate_report(report,source_sha):
    try: return _validate_report(report,source_sha)
    except (TypeError,KeyError,AttributeError,IndexError) as error:
        raise ValueError('Malformed source-driven finite finish report: '+str(error)) from error


def validated_binary_pairs(report,source_sha):
    """Exact downstream domains, after validation; never all member combinations."""
    validate_report(report,source_sha)
    result={}
    for index,row in enumerate(report['results']):
        for members in row['certified_binary_pairs']:
            pair=tuple(sorted(members))
            require(len(pair)==2 and pair not in result,'Duplicate binary finite domain')
            result[pair]={'group_index':index,'kind':row['kind'],'pair':list(pair),
                          'validated_group_members':row['pair']}
    require(len(result)==70,'Complete 70 binary finite domains required')
    return result
