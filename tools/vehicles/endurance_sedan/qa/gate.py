"""Strict report and process acceptance shared by the source QA front door."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

STAGES = ('extraction', 'source-controls', 'source-lights', 'opening-drivers', 'motion-drivers',
          'optical-seats', 'static-interfaces', 'openings', 'opening-containment',
          'tires', 'wiper-glass', 'wiper-interassembly', 'wiper-containment',
          'negative-controls')
DIAGNOSTIC = re.compile(
    r'Traceback \(most recent call last\)|(?:Error in )?PyDriver|SyntaxError:|ERROR[^\r\n]*\bDriver\b|'
    r'(?:image|texture)[^\r\n]*(?:not available|not found|missing|unable to|cannot|failed)|'
    r'(?:not available|not found|missing|unable to|cannot|failed)[^\r\n]*(?:image|texture)|'
    r'EXCEPTION_ACCESS_VIOLATION|SIGSEGV|segmentation fault|fatal error', re.I)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def json_read(path):
    def invalid(value):
        raise ValueError('Nonfinite JSON number: ' + value)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON property: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid, object_pairs_hook=unique)


def positive_process(exit_status, text):
    if exit_status != 0:
        raise ValueError('Native command exit status is not zero: ' + str(exit_status))
    findings = [line for line in text.splitlines() if DIAGNOSTIC.search(line)]
    if findings:
        raise ValueError('Positive Blender command reported forbidden diagnostics: ' + '\n'.join(findings[:12]))


def mesh_defects(rows):
    fields = ('degenerate_loop_triangles', 'nonmanifold_edges', 'duplicate_loop_triangles',
              'triangulated_nonmanifold_edges')
    return [{'name': row['name'], **{key: row[key] for key in fields}}
            for row in rows if any(row[key] != 0 for key in fields) or row['triangles'] <= 0
            or row['minimum_triangle_area_m2'] is None
            or not math.isfinite(row['minimum_triangle_area_m2'])
            or row['minimum_triangle_area_m2'] <= 1e-12]


def inventory(report, payload, source_sha):
    if report['source_sha256'] != source_sha or report['geometry_payload_sha256'] != sha(payload):
        raise ValueError('Native geometry inventory is not bound to the exact supplied source/payload')
    if (report['blender_version'], report['blender_build']) != ('5.1.2', 'ec6e62d40fa9'):
        raise ValueError('Geometry did not use pinned Blender5.1.2/ec6e62d40fa9')
    if report['surface_preview_only'] is not False or report['scene_stage'] != 'production':
        raise ValueError('Full source QA requires the production source with all declared LODs')
    rows = report['mesh_inventory']
    names = [row['name'] for row in rows]
    if not names or len(set(names)) != len(names):
        raise ValueError('Empty or duplicate evaluated mesh inventory')
    defects = mesh_defects(rows)
    if defects:
        raise ValueError('Actual evaluated source mesh defects, including editable preview meshes: ' + json.dumps(defects[:16]))
    shipping = [row for row in rows if row['source_preview_only'] is not True]
    counts = {str(lod): sum(row['triangles'] for row in shipping if row['name'].startswith(f'LOD{lod}_')) for lod in range(3)}
    if counts != report['shipping_lod_triangles'] or any(value <= 0 for value in counts.values()):
        raise ValueError('All three declared LOD inventories must be present and exact')
    total = sum(row['triangles'] for row in shipping)
    collision = sum(row['triangles'] for row in shipping if row['name'].startswith('Collision'))
    materials = sorted({name for row in shipping for name in row['material_names'] if name})
    if total != report['shipping_triangle_total'] or collision != report['shipping_collision_triangles'] or materials != report['shipping_materials']:
        raise ValueError('Source budget totals do not match actual evaluated rows')
    if counts['0'] > 150000 or total > 200000 or not 0 < collision <= 128 or len(materials) > 32:
        raise ValueError('Provisional Q044 content ceiling exceeded')
    if report['opening_sample_steps'] != 100 or report['pose_count'] != 645:
        raise ValueError('Native645-pose inventory incomplete')
    return {'status': 'passed', 'lod_triangles': counts, 'all_shipping_triangles': total,
            'collision_triangles': collision, 'materials': len(materials),
            'all_source_meshes': len(rows), 'native_sampled_poses': 645,
            'limits': 'Content ceilings are provisional Q044; this is not an allocation ratification or motion proof.'}


def stage_report(name, report, source_sha):
    if report.get('status') != 'passed' or report.get('source_sha256') != source_sha:
        raise ValueError(name + ' is failed, incomplete, or bound to a different source')
    if report.get('human_approval_reference') is not None:
        raise ValueError('Automated QA must not introduce a human approval reference')
    if name == 'source-controls' and len(report['states']) != 109:
        raise ValueError('Source display/threshold/control inventory must contain109 states')
    if name == 'source-lights' and (len(report['states']) != 12 or len(report['preview_beams']) != 4 or len(report['actual_emitter_bindings']) != 9):
        raise ValueError('Source light preview inventory incomplete')
    if name == 'opening-drivers' and len(report['opening_groups']) != 6:
        raise ValueError('Six actual opening driver groups are required')
    if name == 'static-interfaces' and (report['named_interface_count'] != 152
                                       or len(report['finite_interface_negative_controls']) != 3):
        raise ValueError('Revision17 requires152 finite named joints and3 original fitted interface controls')
    if name == 'static-interfaces':
        restraint = report['restraint_checks']
        if (restraint['status'] != 'passed' or len(restraint['cloth_self_contact']) != 6
                or len(restraint['convex_guide_containment']) != 2 or len(restraint['negative_controls']) != 5
                or any(row['status'] != 'passed' for field in ('cloth_self_contact', 'convex_guide_containment', 'negative_controls') for row in restraint[field])):
            raise ValueError('Complete restraint self-contact, convex guides and rejection controls are required')
    if name == 'openings' and (report['mode'] != 'all' or report['groups_filter'] or report['components_filter']):
        raise ValueError('Final opening certificate cannot contain diagnostic filters')
    if name == 'negative-controls' and report.get('expected_controls') != report.get('completed_controls'):
        raise ValueError('Negative control inventory incomplete')
    return {'status': 'passed'}


def completed_inventory(rows):
    if tuple(row['name'] for row in rows) != STAGES or any(row['status'] != 'passed' for row in rows):
        raise ValueError('The full ordered source QA stage inventory did not pass')
