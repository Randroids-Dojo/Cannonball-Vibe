"""Source-ready combined actual-sheet API; no IO or report dependencies.

Caller captures actual pre-voids original via sheet_reference.capture_original,
and supplies its actual front field recorder packet. Prepare all objects before
any apply. The native encoder is injected explicitly by the caller.
"""
import json
from . import sheet_reference as sheet
from . import front_carrier
from . import normal_application
from . import finite_arch, finite_bevel


def prepare(objects, original_reference, front_packet, *, ownership, projection, transport, bend_field, optical_field,
            return_references, return_profile):
    if set(objects) != set(sheet.SEMANTICS):
        raise ValueError('Missing/extra actual front sheet semantic')
    if set(return_references) != set(sheet.SEMANTICS[:2]):
        raise ValueError('Missing independent actual fender return references')
    reference = sheet.original_patch(original_reference, ownership, projection)
    plans = []
    for name in sheet.SEMANTICS:
        obj = objects[name]
        actual = sheet.native_state(obj)
        if name != 'LOD0_FrontBumper':
            result = sheet.prepare_sheet(actual, reference)
            transition = finite_arch.prepare(obj, return_references[name], projection, result)
            selected = set(result['selected_faces']) | set(transition['bevel_faces']) | set(transition['return_faces'])
            plan = normal_application.prepare(obj, transition['targets'], sorted(selected),
                                              {'original_sheet': result, 'finite_arch': transition})
        else:
            initial = sheet.state_from_capture(front_packet['core']['initial'])
            original = sheet.prepare_sheet(initial, reference)
            transition = finite_bevel.prepare(initial, original, projection, return_profile)
            carrier = front_carrier.prepare(front_packet, transition, ownership, projection, transport, bend_field, optical_field)
            final = sheet.state_from_capture(carrier['state'])
            for key in ('object', 'points', 'triangles', 'face_loops'):
                if actual[key] != final[key] and json.dumps(actual[key]) != json.dumps(final[key]):
                    raise ValueError('Actual delivered-source geometry differs from current construction carrier: '+key)
            targets = list(actual['normals'])
            faces = set()
            for ti in carrier['selected_triangles']:
                tri = actual['triangles'][ti]
                faces.add(tri['face'])
                for li in tri['loops']:
                    targets[li] = carrier['targets'][li]
            plan = normal_application.prepare(obj, targets, sorted(faces), carrier)
        plans.append(plan)
    return plans


def apply(objects, plans, encode):
    if set(objects) != set(sheet.SEMANTICS) or [p['object'] for p in plans] != list(sheet.SEMANTICS):
        raise ValueError('Incomplete combined original-sheet proposal')
    # Each application remains transactional; no source is saved. The caller
    # must reject the entire unsaved construction if any later guard fails.
    return [normal_application.apply(objects[plan['object']], plan, encode) for plan in plans]
