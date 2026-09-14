"""Current-input cover construction: base. Source provenance is in the private port manifest."""

from . import cover as cover36, base_mesh as mesh16, mounts as mounts54, sheet as sheet53

def prepare(current,reference,triangle_domains,exact,point_triangle):
    cover=sheet53.prepare(cover36.prepare(mesh16.prepare(current,reference,triangle_domains,exact),reference,exact,point_triangle),point_triangle)
    return {cover['name']:cover,**mounts54.prepare(cover,current,triangle_domains,exact)}
