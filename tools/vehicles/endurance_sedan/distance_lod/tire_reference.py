"""Pure source-derived tire meridian; no bake, scene or image API."""
import ast
import hashlib
import json
from pathlib import Path

def require(value, message):
    if not value:
        raise ValueError(message)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def profile_from_constructor(path, spec):
    """Execute only the bound original pure profile statements, never build()."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    build = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build')
    first = next(i for i, n in enumerate(build.body) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'profile' for t in n.targets))
    last = next(i for i, n in enumerate(build.body) if isinstance(n, ast.For)
                and isinstance(n.target, ast.Name) and n.target.id == 'suffix')
    body = ast.Module(body=build.body[first:last], type_ignores=[])
    require(all(n.id in {'profile', 'offset', 'half', 'radius'} for n in ast.walk(body)
                if isinstance(n, ast.Name)), 'Unexpected executable profile dependency')
    variables = {'half': spec['geometry']['tire_width_m'] / 2,
                 'radius': spec['geometry']['wheel_radius_m']}
    require(variables == {'half': .1275, 'radius': .3433}, 'Wrong tire dimensions')
    require(spec['original_packaging']['wheel_tessellation_revision29']['tire_segments'] == 52,
            'Wrong radial station count')
    exec(compile(body, '<locked original tire profile>', 'exec'), {'__builtins__': {}}, variables)
    profile = variables['profile']
    require(len(profile) == 28, 'Incomplete tire meridian')
    return profile, digest(ast.dump(body, include_attributes=False))
