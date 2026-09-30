"""Read the actual saved source and pre-cover checkpoint; never construct or save."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import valance_cover_report as report
from gate import load_source_binding, sha
import finish_interfaces
import geometry
import exact_triangles
from surface_minimum import Distances
from valance_cover_verify39 import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'source-binding', 'construction-root', 'geometry', 'run-binding', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-binding-sha256', required=True)
    parser.add_argument('--expected-run-binding-sha256', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    require = report.require
    require(not args.output.exists() and not args.output.with_suffix('.payload.json.gz').exists(),
            'Retain previous source-stage outputs')
    require(sha(args.source_binding) == args.expected_binding_sha256 and
            sha(args.run_binding) == args.expected_run_binding_sha256, 'Caller-held source/stage binding changed')
    lock = load_source_binding(args.source_binding, args.source, args.construction_root,
                               args.output.parent / 'unused-cover-preflight')
    require(lock.pipeline is not None and lock.pipeline.valance_cover is not None, 'Cover revision not selected')
    held = report.read_document(args.run_binding)
    require(held == report.capture_run_binding(args, lock, tool_directory=Path(__file__).resolve().parent),
            'Actual source-stage invocation differs from independent caller')
    require(bpy.app.version == (5, 1, 2) and bpy.app.build_hash.decode() == 'ec6e62d40fa9', 'Wrong native engine')
    sys.path.insert(1, str(lock.root / 'tools/vehicles'))
    from endurance_sedan import source_generation as records, reserve_correspondence26 as native_fields
    from endurance_sedan import main_fields_cell26
    from endurance_sedan.valance_cover39 import base
    from endurance_sedan.finishing34.front_sheet import field_support

    def plain(value):
        return json.loads(json.dumps(value, allow_nan=False))

    def capture(name):
        return plain(native_fields.evaluated(bpy.data.objects[name]))

    construction = report.read_document(lock.pipeline.construction.path)
    companion = construction[report.COMPANION]
    requested = report.read_document(lock.pipeline.valance_cover.requested.path)
    references = {key: construction['current_surface34'][key] for key in ('original_valance', 'valance_plan')}
    references['prelate_rear34'] = construction['prelate_rear34']
    providers = SimpleNamespace(exact=main_fields_cell26, fi=finish_interfaces, geometry=geometry,
        Distances=Distances, field=field_support, intersection=exact_triangles.intersection, prepare_base=base.prepare)
    started = time.monotonic()
    bpy.ops.wm.open_mainfile(filepath=str(lock.pipeline.valance_cover.checkpoint.path), load_ui=False, use_scripts=False)
    bpy.context.view_layer.update()
    require(bpy.context.scene.get('valance_cover_phase') == 'pre-construction-checkpoint', 'Wrong native checkpoint phase')
    require(all(name not in bpy.data.objects for name in report.NAMES[1:]), 'Pre-cover checkpoint already contains mounts')
    actual_before = {name: capture(name) for name in (report.NAMES[0], report.RECEIVER)}
    require(actual_before == companion['before'], 'Actual saved pre-cover fields differ from construction boundary')
    protected = companion['unowned_raw_before']
    require(set(protected) == {o.name for o in bpy.data.objects if o.type == 'MESH' and o.name != report.NAMES[0]},
            'Incomplete actual pre-cover raw context inventory')
    # Hidden source-only glyphs may reopen with an unevaluated identity world
    # matrix. Observe their native transform by evaluating them visibly, then
    # restore the visibility drivers. No geometry field or hash guard is relaxed.
    hidden = []
    for name in protected:
        obj = bpy.data.objects[name]
        if obj.get('source_preview_only') is True and (obj.hide_viewport or obj.hide_get()):
            drivers = [(c, c.mute) for c in obj.animation_data.drivers
                       if c.data_path == 'hide_viewport'] if obj.animation_data else []
            hidden.append((obj, obj.hide_viewport, obj.hide_get(), drivers, plain(native_fields.raw(obj))))
    try:
        for obj, _, _, drivers, _ in hidden:
            for curve, _ in drivers:
                curve.mute = True
            obj.hide_viewport = False
            obj.hide_set(False)
            obj.update_tag(refresh={'OBJECT'})
        bpy.context.view_layer.update()
        for obj, _, _, _, before_raw in hidden:
            after_raw = plain(native_fields.raw(obj))
            require(all(after_raw[key] == value for key, value in before_raw.items() if key != 'matrix'),
                    'Preview visibility evaluation changed a stored geometry field: ' + obj.name)
        require(all(report.digest(plain(native_fields.raw(bpy.data.objects[n]))) == value for n, value in protected.items()),
                'Actual pre-cover raw context differs from its recorded construction boundary')
    finally:
        for obj, hide_viewport, hide_get, drivers, _ in hidden:
            obj.hide_viewport = hide_viewport
            obj.hide_set(hide_get)
            for curve, muted in drivers:
                curve.mute = muted
        bpy.context.view_layer.update()
        require(all(obj.hide_viewport == hide_viewport and obj.hide_get() == hide_get and
                    all(c.mute == muted for c, muted in drivers)
                    for obj, hide_viewport, hide_get, drivers, _ in hidden),
                'Preview visibility was not restored after native observation')
    print('SEDAN_PRECOVER_VISIBILITY_RESTORED ' + json.dumps([obj.name for obj, *_ in hidden]), flush=True)
    bpy.ops.wm.open_mainfile(filepath=str(lock.source.path), load_ui=False, use_scripts=True)
    require(bpy.context.scene.get('valance_cover_phase') == 'constructed', 'Final source lacks constructed cover phase')
    controls = bpy.data.objects['RigControls']
    for key in controls.keys():
        if isinstance(controls[key], (float, int)) and not key.startswith('source_sim_'):
            controls[key] = 0.0
    controls.update_tag(refresh={'OBJECT'})
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    actual_fields = {name: capture(name) for name in (*report.NAMES, report.RECEIVER)}
    extraction = report.read_document(args.geometry)
    require(extraction['source_sha256'] == lock.source.sha256, 'Extraction belongs to a different saved source')
    rows = report.source_rows(extraction)
    # Re-observe every current global physical mesh, including names not owned by
    # this feature. The numerical verifier cannot discover an omitted caller row.
    actual_names = {o.name for o in bpy.data.objects if o.type in ('MESH', 'FONT')
                   and o.name.startswith('LOD0_') and o.get('source_preview_only') is not True}
    require(set(rows) == actual_names, 'Global extraction omitted a current source component')
    for name in sorted(actual_names):
        actual = capture(name)
        require(all(actual[k] == rows[name][k] for k in ('name', 'vertices', 'triangles')) and
                actual['materials'] == rows[name]['material_names'], 'Current source/extraction disagreement: ' + name)
    proof = verify(rows, actual_fields, requested, companion, references=references, providers=providers)
    require(proof['status'] == 'passed', 'Actual current cover verification failed')
    imported = {}
    locked_files = {Path(r['path']).resolve(): r['sha256'] for r in held['source_inputs'] + held['tools']}
    for module in sys.modules.values():
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.suffix == '.py' and (path.is_relative_to(lock.root / 'tools/vehicles') or
                                    path.is_relative_to(Path(__file__).resolve().parent)):
            require(path in locked_files and sha(path) == locked_files[path], 'Unbound actual source-stage import: ' + str(path))
            imported[str(path)] = report.file_row(path)
    payload = {'input_binding': held, 'actual_pre_cover_verified': True, 'actual_pre_cover': actual_before,
               'pre_cover_protected_raw_meshes': len(protected), 'current_field_names': sorted(actual_fields),
               'actual_global_meshes_observed': sorted(actual_names),
               'actual_imports': [imported[p] for p in sorted(imported)], 'proof': proof}
    lock.verify()
    require(held == report.capture_run_binding(args, lock, tool_directory=Path(__file__).resolve().parent),
            'Source-stage inputs changed during execution')
    payload_path = args.output.with_suffix('.payload.json.gz')
    records.write(payload_path, payload)
    result = {'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
        'status': 'passed', 'source_sha256': lock.source.sha256, 'source_binding_sha256': lock.binding.sha256,
        'geometry_sha256': sha(args.geometry), 'run_binding': report.file_row(args.run_binding),
        'payload': report.file_row(payload_path), 'source_saved': False, 'exported': False,
        'native': {'version': bpy.app.version_string, 'build': bpy.app.build_hash.decode()},
        'all_locked_inputs_unchanged': True, 'seconds': time.monotonic() - started,
        'human_approval_reference': None}
    report.validate_report(result, payload, lock=lock, held=held, invocation_path=args.run_binding,
                           payload_path=payload_path, extraction=extraction)
    records.write(args.output, result)
    print('SEDAN_VALANCE_COVER ' + json.dumps({'status': 'passed', 'source_saved': False,
          'global_meshes': len(rows), 'rest_pairs': len(proof['rest']['pairs'])}), flush=True)


if __name__ == '__main__':
    main()
