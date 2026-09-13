"""No-IO observer for the current FrontBumper field chain.

The caller owns construction. This module never changes the scene or normal
targets: run() supplies a forwarding encoder to the existing stage function.
An intermediate packet is not a saved-source certificate. The independent
checker must derive each stage's targets and bind the actual final source.
"""
import hashlib
import json
import math


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def angle(a, b):
    cross = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    return math.degrees(math.atan2(math.hypot(*cross), sum(x*y for x, y in zip(a, b))))


def valid(n):
    return type(n) in (list, tuple) and len(n) == 3 and all(type(x) in (int, float) and math.isfinite(x) for x in n) and abs(math.hypot(*n)-1) <= 1e-6


def snapshot(obj, fields, material_fields):
    """Snapshot plain values before any later native allocation invalidates RNA."""
    if obj.type != 'MESH' or obj.modifiers:
        raise ValueError('Field observer requires actual native mesh without modifiers')
    mesh = obj.data
    mesh.calc_loop_triangles()
    normal_codes = mesh.attributes.get('custom_normal')
    if normal_codes is not None and (normal_codes.domain != 'CORNER' or normal_codes.data_type != 'INT16_2D'):
        raise ValueError('Unexpected native normal storage')
    return plain({
        'object': obj.name,
        'coordinate_frame': [list(r) for r in obj.matrix_world],
        'physical': fields(mesh),
        'material_response': material_fields(mesh),
        'normals': [list(n.vector) for n in mesh.corner_normals],
        'normal_codes': [list(n.value) for n in normal_codes.data] if normal_codes else None,
        'sharp': [e.use_edge_sharp for e in mesh.edges],
        'loops': [[li.vertex_index, li.edge_index] for li in mesh.loops],
        'faces': [{'loops': list(p.loop_indices), 'normal': list(p.normal)} for p in mesh.polygons],
        'triangles': [{'face': t.polygon_index, 'vertices': list(t.vertices), 'loops': list(t.loops)} for t in mesh.loop_triangles],
    })


def require_encoded(before, targets, after):
    if len(targets) != len(after['loops']) or len(after['normals']) != len(targets) or not targets:
        raise ValueError('Incomplete native target inventory')
    if not all(valid(n) for n in targets + after['normals']):
        raise ValueError('Nonfinite, zero or nonunit target/native normal')
    for key in ('object', 'coordinate_frame', 'physical', 'material_response', 'loops', 'faces', 'triangles'):
        if before[key] != after[key]:
            raise ValueError('Encoder changed physical/native layout: ' + key)
    errors = [angle(a, b) for a, b in zip(targets, after['normals'])]
    if max(errors) > .025:
        raise ValueError('Native encoding exceeds unchanged .025-degree target guard')
    if not after['normal_codes'] or len(after['normal_codes']) != len(targets):
        raise ValueError('Missing final native codes')
    return {'corners': len(targets), 'maximum_target_encoding_degrees': max(errors),
            'maximum_native_unit_error': max(abs(math.hypot(*n)-1) for n in after['normals']),
            'geometry_uv_material_native_layout_exact': True}


class Recorder:
    """One actual bumper, sequential explicit stages, forwarding-only encoder.

    Example:
        recorder = Recorder(bumper, fields, material_fields, encode)
        p = recorder.run('bend', lambda enc: front_bend.apply(bumper, row, enc))
        p = recorder.run('planar', lambda enc: front_planar.apply(bumper, enc))
        p = recorder.run('lamp', lambda enc: front_lamp.apply(bumper, row, enc))
        p = recorder.run('rear_planar', lambda enc: front_rear_planar.apply(bumper, enc))
        slats, p = recorder.run('inlet', lambda enc: front_inlet.apply(bumper, geo, enc))
    A tuple inlet result needs proof_selector=lambda value: value[1].
    """
    ORDER = ('bend', 'planar', 'lamp', 'rear_planar', 'inlet')

    def __init__(self, obj, fields, material_fields, encode):
        self.obj = obj
        self.fields = fields
        self.material_fields = material_fields
        self.real_encode = encode
        self.stages = []
        self.initial = self.state()
        if self.initial['object'] != 'LOD0_FrontBumper' or not all(valid(n) for n in self.initial['normals']):
            raise ValueError('Wrong or invalid bumper input')

    def state(self):
        return snapshot(self.obj, self.fields, self.material_fields)

    def run(self, name, call, *, proof_selector=lambda value: value):
        if len(self.stages) >= len(self.ORDER) or name != self.ORDER[len(self.stages)]:
            raise ValueError('Missing, duplicate or reordered field stage')
        before = self.state()
        expected = self.stages[-1]['after'] if self.stages else self.initial
        if before != expected:
            raise ValueError('Uncaptured field/layout change between stages')
        events = []

        def observed(mesh, targets):
            if mesh != self.obj.data:
                raise ValueError('Encoder target is not the actual current bumper mesh')
            targets = plain([list(n) for n in targets])
            entry = self.state()
            result = self.real_encode(mesh, targets)
            after = self.state()
            metrics = require_encoded(entry, targets, after)
            events.append({'before': entry, 'targets': targets, 'after': after,
                           'native_result': plain(result), 'measured': metrics})
            return result

        result = call(observed)
        after = self.state()
        proof=plain(proof_selector(result))
        expected_events=2 if name=='bend' or (name=='inlet' and proof['generated_rear_fan']['repairs']) else 1
        if len(events) != expected_events:
            raise ValueError('Unexpected native encoding count in ' + name)
        if after != events[-1]['after']:
            raise ValueError('Stage changed bumper after its final encoding capture')
        self.stages.append({'stage': name, 'before': before, 'encodings': events,
                            'proof': proof, 'after': after})
        return result

    def packet(self):
        if tuple(s['stage'] for s in self.stages) != self.ORDER:
            raise ValueError('Incomplete front field chain')
        core = {'schema': 'front-form-field-construction.v2', 'object': self.obj.name,
                'initial': self.initial, 'stages': self.stages, 'final': self.state(),
                'normal_encoding_guard_degrees': .025, 'normal_unit_guard': 1e-6,
                'capture_kind': 'actual-in-process-observation',
                'final_source_binding': None, 'source_saved': False, 'human_approval_reference': None}
        if core['final'] != self.stages[-1]['after']:
            raise ValueError('Final field changed after inlet')
        return {'core': core, 'sha256': digest(core)}
