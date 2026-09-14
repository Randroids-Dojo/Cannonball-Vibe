"""Consume the actual constructor's finite face ownership, never archived tags."""
import re


def triangle_domains(obj, plan, original_reference, *, fingerprint, digest):
    """Validate current face/loop identity and return complete finite roles.

    The caller supplies the plan prepared from its original ribbon capture by
    finishing34.valance_fields at this same construction. This adapter proves
    binding and inventory; its finite ownership predicates remain that module's.
    """
    if obj.name != 'LOD0_RearLowerValance' or obj.type != 'MESH' or obj.modifiers:
        raise ValueError('Expected the current native valance before cover construction')
    if [list(row) for row in obj.matrix_world] != [[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]:
        raise ValueError('Current valance coordinate frame changed')
    if not isinstance(plan,dict) or plan.get('schema') != 'new-original-ribbon-corner-field.v1' or plan.get('object') != obj.name:
        raise ValueError('Wrong actual finite field plan')
    mesh=obj.data;mesh.calc_loop_triangles()
    if fingerprint(mesh) != plan.get('physical_sha256'):
        raise ValueError('Current physical fields differ from the face-ownership capture')
    if digest(original_reference) != plan.get('reference_sha256'):
        raise ValueError('Wrong actual original ribbon reference')
    if digest(plan.get('targets')) != plan.get('targets_sha256'):
        raise ValueError('Captured requested field changed')
    rows=plan.get('domains')
    if not isinstance(rows,list) or len(rows)!=len(mesh.polygons) or plan.get('triangles')!=len(mesh.loop_triangles):
        raise ValueError('Incomplete current face domain inventory')
    actual={face.index:[] for face in mesh.polygons}
    for tri in mesh.loop_triangles:actual[tri.polygon_index].append(tri.index)
    roles=[None]*len(mesh.loop_triangles);seen=set()
    for row in rows:
        face=row.get('face');loops=row.get('loops');triangles=row.get('complete_triangles');role=row.get('domain')
        if type(face) is not int or face not in actual or face in seen:
            raise ValueError('Duplicate or invalid current face owner')
        if not isinstance(role,str) or not (role in ('front','back','top','bottom','left','right') or re.fullmatch(r'passage_(-1|1)_[0-7]',role)):
            raise ValueError('Undeclared finite current face role')
        if not isinstance(loops,list) or any(type(i) is not int for i in loops) or loops!=list(mesh.polygons[face].loop_indices):
            raise ValueError('Current complete face loops differ')
        if not isinstance(triangles,list) or any(type(i) is not int for i in triangles) or triangles!=actual[face]:
            raise ValueError('Current complete face triangulation differs')
        seen.add(face)
        for tri in triangles:
            if roles[tri] is not None:raise ValueError('Multiply owned current triangle')
            roles[tri]=role
    if len(seen)!=len(mesh.polygons) or any(role is None for role in roles):
        raise ValueError('Unowned actual current triangle')
    return roles
