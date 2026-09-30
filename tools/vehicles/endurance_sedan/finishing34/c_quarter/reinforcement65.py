"""D-section58 with native-only, coordinate-preserving sliver diagonal repair.

The inherited exact selector accepts only a <=1um-altitude native vertex on
the interior of a shared edge and a strictly smaller exact crossing set. This
new concealed member owns all its geometric facet normal/UV targets.
"""
from .boundary02 import sub, dot, cross, unit
from .reinforcement64 import plan, arrays
from . import reinforcement64 as previous

def make(original, member, skin, glass, guide, seal, aperture, encode):
    from endurance_sedan import boolean_surface, geometry
    from endurance_sedan.qa.self_geometry import scan
    obj, proof = previous.make(original, member, skin, glass, guide, seal, aperture, encode)
    mesh = obj.data
    before = [tuple(v.co) for v in mesh.vertices]
    count = len(mesh.polygons)
    repair = boolean_surface.repair(obj, scan, geometry.evaluated_counts)
    mesh = obj.data
    if [tuple(v.co) for v in mesh.vertices] != before or len(mesh.polygons) != count:
        raise ValueError('Native diagonal repair changed geometry inventory')
    targets = []
    for face in mesh.polygons:
        if len(face.vertices) != 3:
            raise ValueError('Unexpected repaired nontriangle')
        ps = [list(mesh.vertices[i].co) for i in face.vertices]
        n = unit(cross(sub(ps[1], ps[0]), sub(ps[2], ps[0])))
        e = unit(sub(ps[1], ps[0]))
        v = cross(n, e)
        for loop, p in zip(face.loop_indices, ps):
            targets.append(n)
            for layer in mesh.uv_layers:
                layer.data[loop].uv = (dot(sub(p, ps[0]), e) / 0.25, dot(sub(p, ps[0]), v) / 0.25)
    proof['post_native_diagonal_repair'] = repair
    proof['ideal_targets'] = targets
    proof['encoding'] = encode(mesh, targets)
    proof['pre_native_topology'] = proof.pop('topology')
    proof['final_native_topology'] = {'vertices': [list(v.co) for v in mesh.vertices], 'triangles': [list(p.vertices) for p in mesh.polygons]}
    return (obj, proof)
