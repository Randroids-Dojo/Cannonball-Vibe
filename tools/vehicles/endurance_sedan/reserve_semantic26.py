"""Reports-only strict semantic correspondence for the two Boolean-cut cases.

No coordinate rounding, geometry replacement, scene access, or tolerance stacking.
The caller binds explicit reference rows, modifier states, source and tool hashes.
"""
import math

NORMAL_DEGREES = .025
NORMAL_LENGTH_ERROR = 1e-6
EVALUATED_UV = 1e-5


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def norm(a):
    return math.sqrt(dot(a, a))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def finite_vector(v, length):
    require(len(v) == length and all(isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(x) for x in v), 'Invalid finite vector')


def normal_pair(a, b):
    for v in (a, b):
        finite_vector(v, 3)
        require(abs(norm(v)-1) <= NORMAL_LENGTH_ERROR, 'Invalid unit normal')
    angle = math.degrees(math.atan2(norm(cross(a, b)), dot(a, b)))
    require(angle <= NORMAL_DEGREES, 'Normal angle exceeds existing guard')
    return angle


def cycle(values):
    return min(tuple(values[i:]+values[:i]) for i in range(len(values)))


def vertices(row):
    values = row['vertices']
    require(bool(values), 'Empty vertex domain')
    for v in values:
        finite_vector(v, 3)
    points = [tuple(v) for v in values]
    require(len(set(points)) == len(points), 'Ambiguous duplicate vertex correspondence')
    ordered = sorted(points)
    index = {p:i for i,p in enumerate(ordered)}
    return ordered, [index[p] for p in points]


def face_ids(face, remap):
    require(len(face) >= 3 and all(type(i) is int and 0 <= i < len(remap) for i in face), 'Invalid face index')
    require(len(set(face)) == len(face), 'Repeated face vertex')
    return [remap[i] for i in face]


def raw_domain(row):
    points, remap = vertices(row)
    edges = []
    for e, sharp in row['edges']:
        require(len(e) == 2 and len(set(e)) == 2 and all(type(i) is int and 0 <= i < len(remap) for i in e), 'Invalid edge')
        require(type(sharp) is bool, 'Invalid sharp flag')
        edges.append((tuple(sorted(remap[i] for i in e)), sharp))
    require(len(set(e[0] for e in edges)) == len(edges), 'Duplicate edge')
    faces = {}; cursor = 0
    for f, material, smooth in row['polygons']:
        ids = face_ids(f, remap)
        require(type(material) is int and 0 <= material < len(row['materials']) and type(smooth) is bool, 'Invalid face flags')
        key = cycle(ids)
        require(key not in faces, 'Ambiguous duplicate polygon correspondence')
        corners = {}
        for vertex in ids:
            require(cursor < len(row['normals']), 'Missing raw corner')
            corners[vertex] = {'normal':row['normals'][cursor], 'uvs':{k:v[cursor] for k,v in row['uvs'].items()}}
            cursor += 1
        faces[key] = (material, smooth, corners)
    require(cursor == len(row['normals']) and all(len(v) == cursor for v in row['uvs'].values()), 'Unused or missing raw loop data')
    return points, sorted(edges), faces


def compare_raw(reference, actual):
    for field in ('matrix', 'parent', 'materials'):
        require(reference[field] == actual[field], 'Changed raw '+field)
    require(reference['uvs'].keys() == actual['uvs'].keys(), 'Changed raw UV channel domain')
    ap, ae, af = raw_domain(reference); bp, be, bf = raw_domain(actual)
    require(ap == bp, 'Changed exact raw coordinates')
    require(ae == be, 'Changed exact edge graph or sharp flags')
    require(af.keys() == bf.keys(), 'Changed oriented polygon domain')
    maximum = 0.0
    for key, (mat, smooth, corners) in af.items():
        bm, bs, other = bf[key]
        require((mat, smooth) == (bm, bs), 'Changed polygon material or smooth flag')
        for vertex, fields in corners.items():
            maximum = max(maximum, normal_pair(fields['normal'], other[vertex]['normal']))
            for channel, uv in fields['uvs'].items():
                finite_vector(uv, 2); finite_vector(other[vertex]['uvs'][channel], 2)
                require(uv == other[vertex]['uvs'][channel], 'Changed exact raw UV')
    return {'vertices':len(ap), 'edges':len(ae), 'oriented_polygons':len(af),
            'positions_edges_winding_flags_raw_uv_exact':True, 'maximum_normal_angle_degrees':maximum}


def evaluated_domain(row):
    points, remap = vertices(row)
    require(len(row['triangles']) == len(row['triangle_loops']) == len(row['triangle_materials']), 'Invalid triangle metadata')
    triangles = {}; used_vertices = set(); used_loops = set()
    for f, loops, material in zip(row['triangles'], row['triangle_loops'], row['triangle_materials']):
        require(len(f) == len(loops) == 3, 'Nontriangle evaluated domain')
        ids = face_ids(f, remap); key = cycle(ids)
        require(key not in triangles, 'Ambiguous duplicate triangle correspondence')
        require(type(material) is int and 0 <= material < len(row['materials']), 'Invalid triangle material')
        corners = {}
        for vertex, loop in zip(ids, loops):
            require(type(loop) is int and 0 <= loop < len(row['normals']), 'Invalid evaluated loop index')
            corners[vertex] = {'normal':row['normals'][loop], 'uvs':{k:v[loop] for k,v in row['uvs'].items()}}
            used_loops.add(loop); used_vertices.add(vertex)
        triangles[key] = (material, corners)
    require(used_vertices == set(range(len(points))) and used_loops == set(range(len(row['normals']))), 'Unused evaluated data')
    require(all(len(v) == len(row['normals']) for v in row['uvs'].values()), 'Invalid evaluated UV domain')
    return points, triangles


def minimum_triangle_norm(a, b, c):
    # Minimum |sum(w_i*n_i)| over every barycentric weight, including edges.
    candidates = [norm(a), norm(b), norm(c)]
    for x, y in ((a,b),(b,c),(c,a)):
        delta = sub(y,x); denominator = dot(delta,delta)
        t = min(1.0,max(0.0,-dot(x,delta)/denominator)) if denominator else 0.0
        candidates.append(norm(tuple(x[i]+t*delta[i] for i in range(3))))
    u, v = sub(b,a), sub(c,a)
    uu, uv, vv = dot(u,u), dot(u,v), dot(v,v)
    determinant = uu*vv-uv*uv
    if determinant > 1e-28:
        au, av = dot(a,u), dot(a,v)
        s = (-au*vv+av*uv)/determinant
        t = (-av*uu+au*uv)/determinant
        if s >= 0 and t >= 0 and s+t <= 1:
            candidates.append(norm(tuple(a[i]+s*u[i]+t*v[i] for i in range(3))))
    return max(0.0,min(candidates)-1e-12)


def compare_evaluated(reference, actual):
    require(reference['materials'] == actual['materials'], 'Changed evaluated materials')
    require(reference['uvs'].keys() == actual['uvs'].keys(), 'Changed evaluated UV channels')
    ap, af = evaluated_domain(reference); bp, bf = evaluated_domain(actual)
    require(ap == bp, 'Changed exact evaluated coordinates')
    require(af.keys() == bf.keys(), 'Changed oriented evaluated triangles')
    max_angle = max_uv = max_field = 0.0
    min_norm = 1.0
    for key, (material, corners) in af.items():
        bm, other = bf[key]
        require(material == bm, 'Changed evaluated face material')
        original_normals=[]; delta=0.0
        for vertex in key:
            fields=corners[vertex]; current=other[vertex]
            max_angle=max(max_angle,normal_pair(fields['normal'],current['normal']))
            original_normals.append(fields['normal'])
            delta=max(delta,norm(sub(fields['normal'],current['normal'])))
            for channel, uv in fields['uvs'].items():
                uv2=current['uvs'][channel]
                finite_vector(uv,2);finite_vector(uv2,2)
                difference=max(abs(uv[i]-uv2[i]) for i in (0,1))
                require(difference <= EVALUATED_UV, 'Evaluated UV exceeds existing guard')
                max_uv=max(max_uv,difference)
        lower=minimum_triangle_norm(*original_normals)
        require(lower > delta+1e-12, 'Unresolved normal interpolation domain')
        field=math.degrees(math.asin(min(1.0,(delta+1e-12)/lower)))
        require(field <= NORMAL_DEGREES, 'Complete normal interpolation exceeds existing guard')
        min_norm=min(min_norm,lower);max_field=max(max_field,field)
    return {'vertices':len(ap),'triangles':len(af),'exact_complete_triangle_surface':True,
            'maximum_corner_normal_degrees':max_angle, 'maximum_evaluated_uv_component':max_uv,
            'minimum_original_interpolated_vector_length_lower':min_norm,
            'maximum_complete_interpolated_normal_angle_bound_degrees':max_field,
            'interpolation_method':'Same exact oriented triangles; corner perturbation delta over minimum norm of reference normal triangle. Convex UV interpolation bounded by maximum corner difference.'}
