"""Derive the original native normal charts and manufactured lid returns."""
from collections import defaultdict
import numpy as np

def mesh(actual, original=True):
    if not original:
        raise ValueError('Lid classification requires original native source fields')
    xyz = np.asarray(actual['vertices'], dtype=float)[np.asarray(actual['triangles'], dtype=int)]
    normal = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
    areas = np.linalg.norm(normal, axis=1)
    if not np.all(areas > 0) or not np.isfinite(xyz).all():
        raise ValueError('Invalid native lid source geometry')
    normal /= areas[:, None]
    loops = np.asarray(actual['triangle_loops'], dtype=int)
    normals = np.asarray(actual['normals'], dtype=float)[loops]
    if set(actual['uvs']) != {'SurfaceMeters'}:
        raise ValueError('Lid requires original SurfaceMeters field')
    uv = np.asarray(actual['uvs']['SurfaceMeters'], dtype=float)[loops]
    if normals.shape != xyz.shape or uv.shape != (*xyz.shape[:2], 2):
        raise ValueError('Incomplete native lid corner fields')
    return {'xyz': xyz, 'normal': normal, 'normals': normals, 'uv': uv, 'area': areas / 2}

def angle(a, b):
    return float(np.degrees(np.arctan2(np.linalg.norm(np.cross(a, b)), np.dot(a, b))))


def constraints(actual, seam_degrees=.025, collar_degrees=10.):
    data = mesh(actual, True)
    normals = data['normals']/np.linalg.norm(data['normals'], axis=2)[..., None]
    triangles = actual['triangles']
    edges = defaultdict(list)
    for face, tri in enumerate(triangles):
        for a, b in zip(tri, tri[1:]+tri[:1]):
            edges[tuple(sorted((a, b)))].append(face)
    all_edges, seams = [], []
    adjacency = [set() for _ in triangles]
    for edge, faces in sorted(edges.items()):
        assert len(faces) == 2
        first, second = faces
        error = [angle(normals[first, triangles[first].index(v)], normals[second, triangles[second].index(v)]) for v in edge]
        entry = {'vertices': list(edge), 'faces': faces, 'endpoint_degrees': error, 'maximum_degrees': max(error)}
        all_edges.append(entry)
        if max(error) > seam_degrees:
            seams.append(entry)
        else:
            adjacency[first].add(second)
            adjacency[second].add(first)
    labels = [-1]*len(triangles)
    components = []
    for face in range(len(triangles)):
        if labels[face] != -1:
            continue
        todo, component = [face], []
        labels[face] = len(components)
        while todo:
            at = todo.pop()
            component.append(at)
            for other in sorted(adjacency[at]):
                if labels[other] == -1:
                    labels[other] = len(components)
                    todo.append(other)
        components.append(sorted(component))
    departure = [max(angle(n, g) for n in ns) for ns, g in zip(normals, data['normal'], strict=True)]
    collar = [face for face, degrees in enumerate(departure) if degrees > collar_degrees]
    protected = {v for entry in seams for v in entry['vertices']}
    protected.update(v for face in collar for v in triangles[face])
    vertices = np.asarray(actual['vertices'])
    for axis in range(3):
        for value in (vertices[:, axis].min(), vertices[:, axis].max()):
            protected.update(int(i) for i in np.flatnonzero(vertices[:, axis] == value))
    complete = [face for face, tri in enumerate(triangles) if set(tri) <= protected]
    return {'seam_degrees': seam_degrees, 'collar_degrees': collar_degrees,
            'seam_edges': seams, 'all_edges': all_edges, 'face_departure_degrees': departure,
            'collar_faces': collar, 'protected_vertices': sorted(protected),
            'protected_complete_faces': complete, 'face_charts': labels, 'charts': components,
            'maximum_actual_seam_degrees': max(x['maximum_degrees'] for x in all_edges)}

