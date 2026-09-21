"""Present the exact fresh05 source in a new user-visible native Blender window."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os
import bpy
from mathutils import Vector

here = Path(__file__).resolve().parent
expected = Path('C:/Dev/Cannonball-Vibe-sedan/reports/p1-018/fresh-construction26-pilot05/fresh05/source.blend')
assert Path(bpy.data.filepath).resolve() == expected.resolve()
assert hashlib.sha256(expected.read_bytes()).hexdigest() == 'db7a04ce82561985c7955adc5e54aaf7d6e568f753e636f44c16a6a658bbbb73'

def present():
    views = 0
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D': continue
            space = area.spaces.active
            space.shading.type = 'SOLID'
            space.shading.color_type = 'MATERIAL'
            space.shading.light = 'STUDIO'
            space.shading.show_shadows = True
            space.shading.show_cavity = True
            space.overlay.show_floor = False
            space.overlay.show_extras = False
            space.lens = 55
            region = space.region_3d
            region.view_location = Vector((0, 0, .75))
            region.view_distance = 8.3
            region.view_rotation = Vector((-6, 7, 2.65)).to_track_quat('Z', 'Y')
            region.view_perspective = 'PERSP'
            area.tag_redraw(); views += 1
    assert views > 0
    record = {'task_id': 'P1-018', 'utc': datetime.now(timezone.utc).isoformat(),
              'pid': os.getpid(), 'filepath': bpy.data.filepath, 'blender': bpy.app.version_string,
              'build': bpy.app.build_hash.decode(), 'scene': bpy.context.scene.name,
              'engine': bpy.context.scene.render.engine, 'visible_3d_areas': views,
              'solid_view_only': True, 'source_saved': False,
              'source_sha256': hashlib.sha256(expected.read_bytes()).hexdigest(),
              'human_visual_or_editability_approval': None}
    with (here / 'identity.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(record, f, indent=2); f.write('\n')
    return None

bpy.app.timers.register(present, first_interval=.5)
