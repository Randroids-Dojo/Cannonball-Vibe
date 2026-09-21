"""Selected current tire construction, following the genuine historical52 stage.

The caller supplies a disposable construction collection and an actual original
tire. This module returns a new mesh and a complete witness; it never installs
the result into an original object, saves a scene or exports a package.
"""
import ast
import hashlib
import json
import math
from pathlib import Path

import bpy

from . import corner_encoding
from . import geometry as geo
from . import tire_grooves38 as grooves
from . import tire_surface
from .distance_lod.tire_reference import profile_from_constructor


from .tire_policy40 import POLICY


def require(value, message):
    if not value:
        raise ValueError(message)


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def construction_role(spec):
    """Derive only the existing original tire role, never a second wheel/car build."""
    path = Path(geo.__file__).resolve().parent / 'wheels.py'
    profile, profile_hash = profile_from_constructor(path, spec)
    require(profile_hash == POLICY['source_profile_ast_sha256'],
            'Unmeasured original tire meridian construction')
    require(len(profile) == POLICY['meridian_points'], 'Incomplete original meridian')
    require(spec['geometry']['wheel_radius_m'] == .3433 and
            spec['geometry']['tire_width_m'] == .255, 'Changed original tire dimensions')
    old_policy = spec['original_packaging']['wheel_tessellation_revision29']
    require(tuple(old_policy[k] for k in ('tire_segments', 'rim_barrel_segments',
                                         'friction_face_segments')) == (52, 36, 36),
            'Historical wheel policy must remain at its genuine stage')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    build = next(node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == 'build')
    loop = next(node for node in build.body
                if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and node.target.id == 'suffix')
    end = next(index for index, node in enumerate(loop.body)
               if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Attribute)
               and node.value.func.attr == 'cut_shoulders')
    role = ast.Module(body=loop.body[:end + 1], type_ignores=[])
    role_hash = hashlib.sha256(ast.dump(role, include_attributes=False).encode()).hexdigest()
    require(role_hash == POLICY['source_tire_prefix_ast_sha256'],
            'Original tire role changed; independently remeasure current construction')
    return compile(role, str(path) + '::<original tire role>', 'exec'), {
        'profile_m': plain(profile), 'profile_ast_sha256': profile_hash,
        'tire_prefix_ast_sha256': role_hash,
        'wheel_module_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _raw(collection, original, spec, code, profile, stations):
    suffix = original.name.removeprefix('LOD0_Tire_')
    suspension = bpy.data.objects.get('Suspension_' + suffix)
    require(suspension is not None, 'Missing actual suspension hardpoint')
    env = {
        'geo': geo, 'tire_surface': tire_surface, 'math': math,
        'profile': profile, 'radius': spec['geometry']['wheel_radius_m'],
        'half': spec['geometry']['tire_width_m'] / 2, 'suffix': suffix,
        'pivots': {'Wheel_' + suffix: original.parent,
                   'Suspension_' + suffix: suspension},
        'radial': {'tire_segments': stations},
        'mats': {'rubber': original.data.materials[0],
                 'trim': bpy.data.materials['Material_Trim']},
        'collection': collection,
    }
    exec(code, env)
    tire = env['tire']
    require(tire.parent == original.parent and
            tire.matrix_basis == original.matrix_basis and
            tire.matrix_parent_inverse == original.matrix_parent_inverse,
            'Original tire rigid frame changed')
    return tire


def build_mesh(collection, original, spec, mesh_name=None):
    """Return the current mesh after an exact native historical52 control.

    Required original roles are Tire_SUFFIX, its Wheel_SUFFIX parent and the
    existing Suspension_SUFFIX, plus actual rubber and Trim materials. All
    generated objects are removed; the returned unassigned mesh remains alive.
    """
    require(original.type == 'MESH' and original.name in POLICY['members'],
            'Wrong original tire role')
    require(not original.modifiers, 'Actual evaluated historical tire required')
    require(original.parent is not None and original.parent.name ==
            original.name.replace('LOD0_Tire_', 'Wheel_'), 'Wrong tire rigid parent')
    before = plain(grooves.capture_mesh(original.data))
    require(len(before['faces']) == POLICY['historical_triangles'],
            'Current tire stage requires the genuine historical groove38 output')
    code, role = construction_role(spec)
    initial_objects = set(bpy.data.objects)
    initial_meshes = set(bpy.data.meshes)
    result = None
    try:
        control = _raw(collection, original, spec, code, role['profile_m'], 52)
        raw52 = plain(grooves.capture_mesh(control.data))
        control_mesh, control_grooves = grooves.build_mesh(
            raw52, list(control.data.materials), '_CurrentTire40_Control52', corner_encoding)
        require(plain(grooves.capture_mesh(control_mesh)) == before,
                'Complete actual historical52 geometry/normal/UV/material control failed')
        current = _raw(collection, original, spec, code, role['profile_m'], 44)
        raw44 = plain(grooves.capture_mesh(current.data))
        result, sections = grooves.build_mesh(
            raw44, list(current.data.materials),
            mesh_name or original.name + '_Current44', corner_encoding,
            source_stations=44)
        after = plain(grooves.capture_mesh(result))
        require(len(after['faces']) == POLICY['current_triangles'],
                'Unmeasured current tire Boolean topology')
        require([min(v[i] for v in before['vertices']) for i in range(3)] ==
                [min(v[i] for v in after['vertices']) for i in range(3)] and
                [max(v[i] for v in before['vertices']) for i in range(3)] ==
                [max(v[i] for v in after['vertices']) for i in range(3)],
                'Current tire cardinal bounds changed')
        require(list(result.materials) == list(original.data.materials),
                'Original tire material slots changed')
        require(plain(grooves.capture_mesh(original.data)) == before,
                'Unassigned construction touched original tire')
        return result, plain({
            'policy': POLICY, 'name': original.name, 'original_role': role,
            'before': before, 'after': after,
            'historical52_control_exact': True,
            'historical52_sections': control_grooves,
            'current44_sections': sections,
            'triangle_saving': len(before['faces']) - len(after['faces']),
            'source_saved': False, 'exported': False,
        })
    except Exception:
        if result is not None and result.users == 0:
            bpy.data.meshes.remove(result)
        result = None
        raise
    finally:
        for obj in list(bpy.data.objects):
            if obj not in initial_objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            if mesh not in initial_meshes and mesh != result and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
