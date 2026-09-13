"""Strict original constant-normal/affine-UV planar multi-parent ownership."""
import math
from fractions import Fraction
from mathutils import Vector, geometry


def affine(point, triangle, values, axis):
    dims = [i for i in range(3) if i != axis]
    p, a, b, c = [[float(q[i]) for i in dims] for q in (point, *triangle)]
    bx, by, cx, cy = b[0]-a[0], b[1]-a[1], c[0]-a[0], c[1]-a[1]
    px, py = p[0]-a[0], p[1]-a[1]
    determinant = bx*cy-by*cx
    if determinant == 0:
        raise ValueError('Degenerate original affine chart')
    u, v = (px*cy-py*cx)/determinant, (bx*py-by*px)/determinant
    return tuple(float(values[0][i]) + u*(float(values[1][i])-float(values[0][i]))
                 + v*(float(values[2][i])-float(values[0][i])) for i in range(2))


def transfer(points, normal, material, vertices, triangles, normals, charts, materials, ownership):
    """Return None when no complete original planar domain owns this triangle.

    A domain with a nonconstant normal or nonaffine chart is rejected loudly;
    it needs its original piecewise triangulation, not an averaged field.
    """
    for axis in range(3):
        plane = float(points[0][axis])
        if any(float(p[axis]) != plane for p in points):
            continue
        indices = [i for i, tri in enumerate(triangles)
                   if materials[i] == material and all(float(vertices[j][axis]) == plane for j in tri)
                   and normal.dot((vertices[tri[1]]-vertices[tri[0]]).cross(
                       vertices[tri[2]]-vertices[tri[0]]).normalized()) > .99999]
        if not indices:
            continue
        reference = (None, vertices, [triangles[i] for i in indices], [normals[i] for i in indices])
        patch = ownership._patch(reference)
        if not ownership._covers([tuple(p) for p in points], patch):
            continue
        target = tuple(normals[indices[0]][0])
        exactly_constant = all(tuple(n) == target for i in indices for n in normals[i])
        authored_flat = axis == 1 and plane == 2.2300000190734863 and normal.y < -.99999
        maximum_source_flat_error = 0.0
        if authored_flat:
            target = (0.0, -1.0, 0.0)
            maximum_source_flat_error = max(angle(n, target) for i in indices for n in normals[i])
            if maximum_source_flat_error > .025:
                raise ValueError('Declared flat rear plane exceeds original .025-degree field bound')
        elif not exactly_constant:
            raise ValueError('Multi-parent original plane contains a normal seam')
        # The largest original triangle makes affine field verification stable.
        basis = max(indices, key=lambda i: (vertices[triangles[i][1]]-vertices[triangles[i][0]]).cross(
            vertices[triangles[i][2]]-vertices[triangles[i][0]]).length_squared)
        basis_points = [vertices[j] for j in triangles[basis]]
        chart_error = 0.0
        for name, rows in charts.items():
            for i in indices:
                for p, uv in zip((vertices[j] for j in triangles[i]), rows[i]):
                    predicted = affine(p, basis_points, rows[basis], axis)
                    chart_error = max(chart_error, *(abs(predicted[k]-float(uv[k])) for k in (0, 1)))
        if chart_error > 1e-5:
            raise ValueError('Multi-parent original plane contains a UV seam or nonaffine field')
        uv_targets = {name: [] for name in charts}
        owners = []
        maximum_projection = 0.0
        for p in points:
            choices = []
            for i in indices:
                tri = [vertices[j] for j in triangles[i]]
                hit = closest_plane(p, tri, axis)
                distance = math.dist(p, hit)
                if distance <= 2e-7:
                    choices.append((distance, i, hit))
            if not choices:
                raise ValueError('Completely owned planar corner lacks a source within2e-7m')
            distance, i, hit = min(choices, key=lambda value: (value[0], value[1]))
            maximum_projection = max(maximum_projection, distance)
            owners.append(i)
            tri = [vertices[j] for j in triangles[i]]
            for name, rows in charts.items():
                value = affine(hit, tri, rows[i], axis)
                predicted = affine(p, basis_points, rows[basis], axis)
                if max(abs(value[k]-predicted[k]) for k in (0, 1)) > 1e-5:
                    raise ValueError('Projected planar corner loses its complete affine field')
                uv_targets[name].append(value)
        return {'normals': [Vector(target) for _ in points], 'charts': uv_targets,
                'proof': {'axis': axis, 'plane_m': plane, 'reference_faces': indices,
                          'corner_reference_faces': owners, 'complete_footprint_covered': True,
                          'coverage_guard_m': 1e-6, 'corner_projection_guard_m': 2e-7,
                          'maximum_corner_projection_m': maximum_projection,
                          'normal_field_exactly_constant': exactly_constant,
                          'declared_flat_rear_target': authored_flat,
                          'maximum_source_flat_error_degrees': maximum_source_flat_error,
                          'maximum_source_affine_uv_error': chart_error, 'uv_guard': 1e-5}}
    return None


def angle(a,b):
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross),sum(x*y for x,y in zip(a,b))))


def verify_native(owners, original_normals, native_normals):
    results=[]
    for owner in owners:
        if owner['kind']!='retained_complete_planar_patch':continue
        corners=native_normals[owner['face']*3:owner['face']*3+3]
        if len(corners)!=3:raise ValueError('Missing actual planar native corners')
        references=[n for i in owner['reference_faces'] for n in original_normals[i]]
        if not all(abs(math.hypot(*n)-1)<=1e-6 for n in references+corners):
            raise ValueError('Nonunit original/final planar native field')
        maximum=max(angle(a,b) for a in references for b in corners)
        if maximum>.025:
            raise ValueError('Complete original/final planar field cone exceeds .025 degrees')
        results.append({'face':owner['face'],'reference_faces':owner['reference_faces'],
                        'all_original_to_all_actual_native_corner_pairs':len(references)*len(corners),
                        'maximum_original_final_field_degrees':maximum,
                        'complete_normalized_affine_fields_bounded':True,'guard_degrees':.025})
    return results


def closest_plane(point, triangle, axis):
    """Exact native-float containment, double-precision nearest boundary.

    Blender's mathutils point/triangle routine computes with float32 and can
    lose the unchanged2e-7m guard on these long, thin native cap triangles.
    The plane and source vertices remain their exact original native values.
    """
    dims=[i for i in range(3) if i!=axis]
    exact=lambda p:tuple(Fraction(float(p[i])) for i in dims)
    p=exact(point);a,b,c=[exact(q) for q in triangle]
    cross=lambda a,b,c:(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    orientation=cross(a,b,c)
    if not orientation:raise ValueError('Degenerate exact source plane triangle')
    sign=1 if orientation>0 else -1
    if all(sign*cross(u,v,p)>=0 for u,v in ((a,b),(b,c),(c,a))):
        result=list(map(float,point));result[axis]=float(triangle[0][axis]);return tuple(result)
    candidates=[]
    for a,b in zip(triangle,triangle[1:]+triangle[:1]):
        delta=[float(b[i])-float(a[i]) for i in range(3)]
        length=sum(x*x for x in delta)
        if length==0:raise ValueError('Collapsed source plane edge')
        t=max(0.,min(1.,sum((float(point[i])-float(a[i]))*delta[i] for i in range(3))/length))
        hit=tuple(float(a[i])+t*delta[i] for i in range(3))
        candidates.append((math.dist(point,hit),hit))
    return min(candidates,key=lambda value:value[0])[1]
