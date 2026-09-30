"""Current-input cover construction: candidate_geometry. Source provenance is in the private port manifest."""

from . import base as native_apply55

from . import returns as return359

from . import inner as inner379

def prepare(current,body,reference,triangle_domains,exact,point_triangle):
    if current['name']!='LOD0_RearLowerValance' or body['name']!='LOD0_RearBumper':
        raise ValueError('Wrong actual semantic assembly')
    if len(triangle_domains)!=len(current['triangles']):raise ValueError('Incomplete current construction ownership')
    plans=native_apply55.prepare(current,reference,triangle_domains,exact,point_triangle)
    base=plans[current['name']]
    layout=return359.outer_layout(base,reference,body,exact)
    plans[current['name']]=inner379.prepare(base,layout,exact)
    return plans,layout,base
