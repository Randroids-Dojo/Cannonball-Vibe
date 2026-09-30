"""Current-input cover construction: preview. Source provenance is in the private port manifest."""

import json

from . import api as cover_candidate436

from . import native as install386

def apply(obj, body, *, reference, triangle_domains, finite_field_domains,
          capture, exact, point_triangle, complete_angle, encode,
          freeze_requested, expected_plans=None):
    if obj.name != 'LOD0_RearLowerValance' or body.name != 'LOD0_RearBumper':
        raise ValueError('Expected the actual named rear assembly')
    if not callable(freeze_requested):
        raise ValueError('A caller-owned pre-encoding target freeze is required')
    current, receiver = capture(obj), capture(body)
    plans, layout, base = cover_candidate436.prepare(
        current, receiver, reference, triangle_domains, finite_field_domains,
        exact=exact, point_triangle=point_triangle, complete_angle=complete_angle)
    normalized = json.loads(json.dumps(plans, allow_nan=False))
    if expected_plans is not None and normalized != expected_plans:
        raise ValueError('Actual current prepared targets differ from frozen review')
    # Freeze the complete request before the first native encoding or mutation.
    frozen = freeze_requested(normalized)
    if frozen is None:
        raise ValueError('Caller did not acknowledge the requested-target freeze')
    result = install386.apply(obj, plans, capture=capture, encode=encode)
    if capture(body) != receiver:
        raise ValueError('Protected current receiver changed')
    return dict(plans=plans, layout=layout, base=base, native=result,
                requested_freeze=frozen, source_saved=False, exported=False,
                rendered=False, independently_visually_accepted=False)
