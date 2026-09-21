"""Apply authored sections only to an observed, encoded native base assembly."""
from pathlib import Path

from ...qa.upper_finish_report import NAMES, require
from . import frames, roof

MEMBERS = tuple(sorted((*roof.NAMES, *frames.NAMES)))


def input_paths():
    directory = Path(__file__).resolve().parent
    return {
        'native_generator': directory / '__init__.py',
        'roof_generator': directory / 'roof.py',
        'roof_design': directory / 'roof_sections.json',
        'frame_generator': directory / 'frames.py',
        'frame_design': directory / 'frame_sections.json',
    }


def build(actual_rows):
    require(set(actual_rows) == set(NAMES), 'Complete actual native upper intermediate required')
    for name, row in actual_rows.items():
        require(row.get('name') == name and all(key in row for key in
                ('normals', 'triangle_loops', 'uvs', 'vertices', 'triangles', 'materials')),
                'Actual encoded upper fields required: ' + name)
    parts = roof.build({name: actual_rows[name] for name in roof.NAMES})
    parts.update(frames.build({name: actual_rows[name] for name in frames.NAMES}))
    require(set(parts) == set(MEMBERS), 'Authored native upper correction ownership differs')
    return parts
