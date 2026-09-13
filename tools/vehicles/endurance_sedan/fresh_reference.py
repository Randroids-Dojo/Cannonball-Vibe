"""Rebuild the current original field in a new native scene, without a bake."""
from pathlib import Path
import hashlib
import importlib
import importlib.util
import json
import sys

import bpy


def rebuild_reference(profile, helper, construction_inputs):
    by_role = {row['role']: row for row in construction_inputs
               if row['role'] != 'constructor_component'}
    spec_path = Path(by_role['specification']['path']).resolve(strict=True)
    constructor = Path(by_role['constructor']['path']).resolve(strict=True)
    package = constructor.parent / 'endurance_sedan'
    expected = json.loads(spec_path.read_text(encoding='utf-8'))
    if json.loads(bpy.context.scene['specification']) != expected:
        raise ValueError('Actual saved specification differs from current construction input')
    if Path(helper.__file__).resolve(strict=True) != Path(by_role['normal_module']['path']).resolve(strict=True):
        raise ValueError('Reference helper differs from the actual locked normal module')
    # Current construction binds this exact profile through its hashed normal
    # module. It does not contain the superseded surface_field_revision26 key.
    helper.validate_profile(profile)
    for row in construction_inputs:
        path = Path(row['path'])
        if path.stat().st_size != row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Fresh construction input changed')
    # A private package prevents accidental reuse of modules from another checkout.
    package_name = '_sedan_fresh_' + hashlib.sha256(str(package).encode()).hexdigest()[:20]
    if package_name in sys.modules:
        raise ValueError('Fresh builder invoked twice in one native interpreter')
    spec = importlib.util.spec_from_file_location(package_name, package / '__init__.py',
                                                submodule_search_locations=[str(package)])
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = loaded
    spec.loader.exec_module(loaded)
    model = importlib.import_module(package_name + '.model')
    fender = importlib.import_module(package_name + '.fender_field')
    fascia = importlib.import_module(package_name + '.fascia_surface')
    materials = importlib.import_module(package_name + '.materials')
    fascia.validate(expected['original_packaging']['fascia_revision21'])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1
    bpy.context.scene['specification'] = json.dumps(expected, sort_keys=True)
    collection = bpy.data.collections.new('Private_FreshShoulderQA')
    bpy.context.scene.collection.children.link(collection)
    parent = bpy.data.objects.new('Visual_LOD0', None)
    collection.objects.link(parent)
    mats = materials.build()
    result = {}

    class Captured(Exception):
        pass

    def capture(body):
        result.update(helper.capture(body, profile,
            authored_corner_targets=model.BODY_FRONT_PREFIX_FIELD['targets']))
        raise Captured()

    original = fender.capture
    fender.capture = capture
    model.CURVED_PROFILES = True
    try:
        model.lower_body(collection, parent, mats, capture_provenance=False)
    except Captured:
        pass
    finally:
        fender.capture = original
    if not result:
        raise ValueError('Current native constructor never reached its original field boundary')
    for row in construction_inputs:
        path = Path(row['path'])
        if path.stat().st_size != row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Fresh construction input changed during native replay')
    return json.loads(json.dumps(result, allow_nan=False))
