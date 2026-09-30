"""Current-input cover construction: api. Source provenance is in the private port manifest."""

from . import candidate_geometry as cover_candidate385

from . import inner_fields as inner_field428

def prepare(current, body, reference, triangle_domains, finite_field_domains,
            *, exact, point_triangle, complete_angle):
    plans, layout, base = cover_candidate385.prepare(
        current, body, reference, triangle_domains, exact, point_triangle)
    name = current['name']
    plans[name] = inner_field428.prepare(
        plans[name], base, finite_field_domains, point_triangle, complete_angle)
    return plans, layout, base
