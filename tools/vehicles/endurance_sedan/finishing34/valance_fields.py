"""Finite curved-ribbon and manufactured-cap fields; no scene or file IO."""
import math
from mathutils import Vector

SEMANTIC = 'LOD0_RearLowerValance'
GUARD = 1e-6


def unit(n):
    length = math.hypot(*n)
    if not math.isfinite(length) or length <= 0:
        raise ValueError('Singular native surface')
    return tuple(v/length for v in n)


def normal(points):
    a, b, c = (Vector(v) for v in points)
    return unit((b-a).cross(c-a))


def bounds(points):
    return [min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]


def capture_original(obj):
    if obj.type != 'MESH' or obj.modifiers or any(obj.matrix_world[i][j] != (1. if i == j else 0.) for i in range(4) for j in range(4)):
        raise ValueError('Expected original native ground-frame ribbon')
    mesh = obj.data
    mesh.calc_loop_triangles()
    vertices = [tuple(v.co) for v in mesh.vertices]
    if len(vertices) != 100 or len(mesh.polygons) != 98 or len(mesh.loop_triangles) != 196:
        raise ValueError('Original24-section ribbon construction changed')
    expected = []
    for i in range(25):
        x = -.82+1.64*i/24
        front = -2.54+.105*(abs(x)/.83)**3
        expected.extend([(x,front+.065,.2375),(x,front,.2375),(x,front,.3385),(x,front+.065,.3385)])
    if any(math.dist(a,b)>2e-7 for a,b in zip(vertices,expected)):
        raise ValueError('Actual ribbon dimensions/profile differ')
    rows = []
    for t in mesh.loop_triangles:
        ps = [vertices[i] for i in t.vertices]
        n = normal(ps)
        if abs(n[2]) > .999999:
            domain = 'top' if n[2] > 0 else 'bottom'
        elif abs(n[0]) > .999999:
            domain = 'right' if n[0] > 0 else 'left'
        elif abs(n[1]) > .80 and abs(n[2]) < 1e-5:
            domain = 'front' if n[1] < 0 else 'back'
        else:
            raise ValueError('Unclassified original ribbon triangle')
        rows.append({'triangle': t.index, 'points': ps, 'normal': n, 'domain': domain})
    return {'schema': 'actual-original-rear-ribbon-domains.v1', 'semantic': SEMANTIC,
            'coordinate_space': 'actual-native-source-ground-frame-meters', 'vertices': vertices, 'triangles': rows}


def passage_domains():
    # Same finite, eight-corner actual cutter used by late_first_fit.build.
    hx, hz, ch = .091, .046, .008
    ring = [(-hx+ch,-hz),(hx-ch,-hz),(hx,-hz+ch),(hx,hz-ch),(hx-ch,hz),(-hx+ch,hz),(-hx,hz-ch),(-hx,-hz+ch)]
    rows = []
    for side in (-1,1):
        vs = [(side*.647+x,y,.312+z) for y in (-2.560,-2.268) for x,z in ring]
        for i in range(8):
            j = (i+1)%8
            for tri in ((i,j,j+8),(i,j+8,i+8)):
                ps = [vs[k] for k in tri]
                rows.append({'triangle': len(rows), 'points': ps, 'normal': normal(ps), 'domain': 'passage_'+str(side)+'_'+str(i)})
    return rows


def prepare(obj, reference, ownership, native, projection):
    if obj.name != SEMANTIC or obj.modifiers or obj.type != 'MESH':
        raise ValueError('Expected final actual native valance')
    if reference['schema'] != 'actual-original-rear-ribbon-domains.v1' or reference['semantic'] != obj.name:
        raise ValueError('Wrong actual ribbon capture')
    if any(obj.matrix_world[i][j] != (1. if i == j else 0.) for i in range(4) for j in range(4)):
        raise ValueError('Changed valance coordinate frame')
    groups = {}
    for row in reference['triangles']+passage_domains():
        groups.setdefault(row['domain'], []).append(row)
    patches = {domain: [ownership._patch((None,[Vector(p) for p in r['points']],[(0,1,2)],[[Vector(r['normal'])]*3]))[0] for r in rows] for domain,rows in groups.items()}
    mesh = obj.data
    mesh.calc_loop_triangles()
    before = [tuple(n.vector) for n in mesh.corner_normals]
    if not all(native.valid_normal(n) for n in before):
        raise ValueError('Invalid actual input field')
    facetris = {}
    for tri in mesh.loop_triangles:
        facetris.setdefault(tri.polygon_index, []).append(tri)
    targets = list(before)
    domains = []
    failures = []
    convex_certificates = []
    def covered(triangle, domain, face_index):
        if ownership._covers(triangle, patches[domain]):
            return True
        candidates = []
        for r in groups[domain]:
            corners = [projection.closest(p, r['points']) for p in triangle]
            distance = max(d for d, weights in corners)
            if distance <= GUARD-1e-12 and all(min(w) >= 0 and abs(sum(w)-1) <= 1e-12 for d,w in corners):
                candidates.append((distance, r['triangle'], corners))
        if not candidates:
            return False
        distance, ref_index, corners = min(candidates)
        convex_certificates.append({'face':face_index,'domain':domain,'triangle':triangle,'reference_triangle':ref_index,'complete_convex_distance_bound_m':distance,'corners':corners})
        return True
    for face in mesh.polygons:
        tris = [[tuple(mesh.vertices[i].co) for i in t.vertices] for t in facetris[face.index]]
        accepted = []
        for domain, patch in patches.items():
            if all(covered(tri, domain, face.index) for tri in tris):
                ns = [r['normal'] for r in groups[domain]]
                if any(abs(sum(float(face.normal[i])*n[i] for i in range(3))) >= .99985 for n in ns):
                    accepted.append(domain)
        original = [d for d in accepted if not d.startswith('passage_')]
        if len(original) == 1:
            domain = original[0]
        elif not original and len(accepted) == 1:
            domain = accepted[0]
        else:
            failures.append({'face': face.index, 'accepted': accepted, 'triangles': tris, 'normal': tuple(face.normal)})
            continue
        for li in face.loop_indices:
            x = mesh.vertices[mesh.loops[li].vertex_index].co.x
            slope = 3*.105*x*abs(x)/.83**3
            if domain == 'front':
                target = unit((slope,-1,0))
            elif domain == 'back':
                target = unit((-slope,1,0))
            elif domain in ('top','bottom','left','right'):
                target = {'top':(0,0,1),'bottom':(0,0,-1),'left':(-1,0,0),'right':(1,0,0)}[domain]
            else:
                target = unit(face.normal)
            targets[li] = target
        domains.append({'face': face.index, 'domain': domain, 'loops': list(face.loop_indices), 'complete_triangles': [t.index for t in facetris[face.index]]})
    if failures:
        raise ValueError('Unowned/ambiguous actual valance faces: '+str(failures))
    if len(domains) != len(mesh.polygons) or not all(native.valid_normal(n) for n in targets):
        raise ValueError('Incomplete actual domain field')
    return {'schema': 'new-original-ribbon-corner-field.v1', 'object': obj.name,
            'physical_sha256': native.fingerprint(mesh), 'reference_sha256': native.digest(reference),
            'before': before, 'targets': targets, 'targets_sha256': native.digest(targets),
            'domains': domains, 'complete_convex_certificates': convex_certificates, 'triangles': len(mesh.loop_triangles), 'source_saved': False}


def apply(obj, plan, encode, native):
    import bpy
    if obj.name != plan['object'] or native.fingerprint(obj.data) != plan['physical_sha256']:
        raise ValueError('Actual valance changed after preparation')
    if [tuple(n.vector) for n in obj.data.corner_normals] != plan['before'] or native.digest(plan['targets']) != plan['targets_sha256']:
        raise ValueError('Input or target fields changed')
    original = obj.data
    stage = original.copy()
    try:
        result = encode(stage, plan['targets'])
        if not result['passed']:
            raise ValueError('Native target encoding exceeded unchanged guard')
        if native.fingerprint(stage) != plan['physical_sha256']:
            raise ValueError('Protected native geometry/UV/material fields changed')
        obj.data = stage
        return {'status': 'actual_corner_fields_passed_complete_field_pending', 'object': obj.name, 'encoding': result, 'all_geometry_UV_material_fields_exact': True}
    except BaseException:
        if stage.users == 0:
            bpy.data.meshes.remove(stage)
        raise
