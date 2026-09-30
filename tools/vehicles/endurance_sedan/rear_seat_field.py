"""Stable rear-seat ordering and explicitly authored surface fields.

Rear foam uses a deliberately authored continuous corner field supported by
current original patches. Carrier seats use opposed evaluated carrier fields.
Generated join faces require complete current-patch support. Historical whole
interpolation preservation is not claimed; native encoding limits are unchanged.
No source/report payload or indexed historical face determines construction.
"""
import math
from types import SimpleNamespace
import bpy
from mathutils import Vector, geometry as native_geometry
from contextlib import contextmanager
from . import seat_ordering


def _operations(recipe, encode):
    original_boolean, original_triangulate = recipe._boolean, recipe._triangulate
    original_reference, original_finish = recipe._reference, recipe._finish
    ordering = seat_ordering.operations(recipe, encode)
    reorder_records = ordering['records']
    ordered_triangulate, ordered_reference = ordering['triangulate'], ordering['reference']
    sn = recipe.surface_normals
    domains = []

    def rear_foam(obj):
        return obj.name in ('STAGED_LOD0_RearLBackInsert', 'STAGED_LOD0_RearRBackInsert')

    def boolean(first, second, operation, scan):
        recipe._triangulate = ordered_triangulate if rear_foam(first) else original_triangulate
        try:
            return original_boolean(first, second, operation, scan)
        finally:
            recipe._triangulate = original_triangulate

    def reference(obj):
        if any(obj.name.startswith('STAGED_LOD0_'+seat+part) for seat in ('RearL','RearR') for part in recipe.FOAM_PARTS):
            return ordered_reference(obj)
        return original_reference(obj)


    def opposed(obj):
        graph = bpy.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), preserve_all_data_layers=True, depsgraph=graph)
        try:
            name,vertices,triangles,normals = original_reference(SimpleNamespace(name=obj.name, data=mesh))
        finally:
            bpy.data.meshes.remove(mesh)
        return ('OPPOSED_'+name,vertices,[tuple(reversed(t)) for t in triangles],
                [[-v for v in reversed(row)] for row in normals])

    def finish(obj, references, encoder, scan):
        if not rear_foam(obj):
            return original_finish(obj,references,encoder,scan)
        prefix = 'RearL' if 'RearL' in obj.name else 'RearR'
        original_geometry = sorted(tuple(sorted(tuple(obj.data.vertices[i].co) for i in t.vertices))
                                   for t in obj.data.loop_triangles)
        ordered_triangulate(obj)
        mesh = obj.data
        mesh.calc_loop_triangles()
        assert original_geometry == sorted(tuple(sorted(tuple(mesh.vertices[i].co) for i in t.vertices))
                                           for t in mesh.loop_triangles)
        refs = list(references) + [opposed(bpy.data.objects['LOD0_'+prefix+p]) for p in ('BackShell','CushionFrame')]
        patches = [sn._patch(r) for r in refs]
        targets = [None] * len(mesh.loops)
        proof_rows = []
        for face in mesh.polygons:
            if len(face.vertices) != 3:
                raise ValueError('Actual triangle normal ownership is required')
            triangle = [tuple(mesh.vertices[i].co) for i in face.vertices]
            selected = None
            for index,patch in enumerate(patches):
                proof = complete_support(triangle,patch,True,sn)
                if proof is not None:
                    selected = index,proof
                    break
            if selected is None:
                options = []
                for index,patch in enumerate(patches):
                    proof = complete_support(triangle,patch,False,sn)
                    if proof is not None:
                        options.append((proof['maximum_plane_deviation_m'], index, proof))
                if not options:
                    raise ValueError('Generated join lacks complete current-surface support: '+str(triangle))
                _,index,proof = min(options,key=lambda row:(row[0],row[1]))
                selected = index,proof
            index,proof = selected
            patch = patches[index]
            corner_distances = []
            for loop in face.loop_indices:
                point = mesh.vertices[mesh.loops[loop].vertex_index].co
                candidates = []
                for source_index in proof['reference_triangles']:
                    points,normal,planes,normals = patch[source_index]
                    vectors = [Vector(p) for p in points]
                    hit = native_geometry.closest_point_on_tri(point,*vectors)
                    distance = math.dist(tuple(point),tuple(hit))
                    if distance > 2e-6:
                        continue
                    value = native_geometry.barycentric_transform(hit,*vectors,*normals)
                    if not all(math.isfinite(x) for x in value) or value.length < .5:
                        raise ValueError('Invalid original reference field')
                    candidates.append((distance,source_index,value.normalized()))
                if not candidates:
                    raise ValueError('Owned join corner lacks a nearby supported original field')
                distance,_,value = min(candidates,key=lambda row:(row[0],row[1]))
                targets[loop] = tuple(value)
                corner_distances.append(distance)
            proof_rows.append({'triangle':face.index,'vertices':list(face.vertices),'owner':refs[index][0],
                               **proof,'maximum_corner_reference_distance_m':max(corner_distances)})
        if any(v is None for v in targets):
            raise ValueError('Unassigned rear foam normal')
        encoding = encoder(mesh,targets)
        if not encoding['passed'] or encoding['maximum_native_decoded_degrees']>.025:
            raise ValueError('Requested-to-native rear-join field guard failed')
        quality = recipe._check(obj,scan)
        domain = {'seat':prefix,'faces':proof_rows,'fully_classified_faces':len(proof_rows),
            'generated_join_faces':sum(r['orientation_class']=='new_generated_join_field' for r in proof_rows),
            'field_scope':'Authored rear exterior, opposed carrier-seat and bounded generated-join corner fields on complete current geometric support; no historical whole-interpolation preservation or native Boolean fallback.',
            'encoding':encoding,'quality':quality}
        domains.append(domain)
        return {'ownership':domain,'encoding':encoding,'quality':quality}

    return {'_boolean': boolean, '_reference': reference, '_finish': finish}, {
        'ordering_records': reorder_records, 'domain_records': domains}


def complete_support(triangle, patch, aligned, geometry):
    sn = geometry
    normal = sn._unit(sn._cross(sn._sub(triangle[1],triangle[0]),sn._sub(triangle[2],triangle[0])))
    remaining = [triangle]
    used = []
    maximum = 0.
    for index,(points,n,planes,_) in enumerate(patch):
        if aligned and sn._dot(normal,n) < .99985:
            continue
        error = max(abs(sn._dot(sn._sub(p,points[0]),n)) for p in triangle)
        if error > 1e-6:
            continue
        before = remaining
        remaining = [piece for poly in remaining for piece in sn._subtract(poly,planes)]
        if before != remaining:
            used.append(index)
            maximum = max(maximum,error)
        if not remaining:
            return {'maximum_plane_deviation_m':maximum,'reference_triangles':used,
                    'complete_projected_coverage':True,'guard_m':1e-6,
                    'orientation_class':'aligned_original_surface' if aligned else 'new_generated_join_field'}
    return None


@contextmanager
def installed(recipe=None, encode=None):
    """Temporarily install the stable policy for explicit caller-owned construction.

    Example: with installed(seat_assemblies) as evidence: prepare each seat.
    The caller owns source loading, prepared-seat installation and source gates.
    Functions are restored on success or failure; nested installation rejects.
    """
    if recipe is None:
        from . import seat_assemblies as recipe
    if encode is None:
        from .corner_encoding import encode
    names = ('_boolean', '_triangulate', '_reference', '_finish')
    original = {name: getattr(recipe, name) for name in names}
    if not callable(encode) or any(not callable(value) for value in original.values()):
        raise ValueError('Callable seat operations and native encoder are required')
    if any(getattr(value, '_stable_seat_policy_owned', False) for value in original.values()):
        raise ValueError('Stable seat policy is already installed on this module')
    replacements, evidence = _operations(recipe, encode)
    for name, value in replacements.items():
        value._stable_seat_policy_owned = True
        setattr(recipe, name, value)
    expected = {name: replacements.get(name, original[name]) for name in names}
    try:
        yield evidence
    finally:
        changed = [name for name in names if getattr(recipe, name) is not expected[name]]
        for name, value in original.items():
            setattr(recipe, name, value)
        if changed:
            raise RuntimeError('Seat operations changed outside the installed policy: ' + ', '.join(changed))
