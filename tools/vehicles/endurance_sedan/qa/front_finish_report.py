"""Select and bind the current three-panel front independently of legacy v36.

This host module binds actual phase files. Native guide derivation, evaluated
fields and lower-LOD correspondence are separate mandatory checks.
"""
from dataclasses import dataclass
import hashlib
import json

NAMES = ('LOD0_FrontBumper', 'LOD0_FrontFender_L', 'LOD0_FrontFender_R')
RECEIVERS = tuple('LOD0_SplitterMount_' + str(index) for index in range(4))
SELECTOR = 'front_finish_revision40'
COMPANION = 'front_finish40'
POLICY = {
    'schema': 'source-front-finish40.v1',
    'members': list(NAMES),
    'receivers': list(RECEIVERS),
    'local_collapse_plane_residual_m': .0001,
    'arch_bidirectional_contour_m': .0002,
    'retained_interface_position_m': .000001,
    'normal_angle_degrees': .025,
    'normal_unit_error': .000001,
    'uv_absolute': .00001,
    'normal_derivation': 'Complete owned panels from retained physical guide and explicit crease/fan domains',
    'legacy': 'Unchanged v36 verification on actual completed finishing34 checkpoint',
}
LOWER_POLICY = {
    'schema': 'current-guide-front-lower40.v1', 'members': list(NAMES), 'levels': [1, 2],
    'features': 'Current material/aperture boundaries, arch returns and complete shoulder/lamp carrier fans',
    'protection': 'Complete original oriented triangles, UV, material and affine normal fields',
    'normal_angle_degrees': .025,
    'unrelated_recipe': 'Unchanged cabin29 ratios, omissions, selective groups and literal budgets',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def revision_requested(specification, construction, *, is_pipeline):
    packaging = specification['original_packaging']
    require(type(packaging) is dict, 'Missing locked original packaging')
    if SELECTOR not in packaging:
        require(COMPANION not in construction, 'Undeclared current front companion')
        return False
    require(is_pipeline is True, 'Current front requires source binding v2')
    require(digest(packaging[SELECTOR]) == digest(POLICY), 'Unknown/null current front revision')
    require(COMPANION in construction, 'Missing declared current front companion')
    proof = construction[COMPANION]
    require(type(proof) is dict and proof.get('schema') == 'source-front-finish-construction40.v1',
            'Wrong current front construction witness')
    require(digest(proof.get('policy')) == digest(POLICY), 'Current front witness policy differs')
    require(proof.get('source_phase') == 'pre-lod', 'Wrong current front construction phase')
    for key, names in (('before', NAMES), ('receivers', RECEIVERS),
                       ('before_material_response', (*NAMES, *RECEIVERS))):
        require(type(proof.get(key)) is dict and set(proof[key]) == set(names),
                'Incomplete current front input domain: ' + key)
    require(type(proof.get('native')) is dict and set(proof['native'].get('after', {})) == set(NAMES),
            'Incomplete current three-panel native witness')
    require(proof.get('unowned_raw_unchanged') is True and
            type(proof.get('unowned_raw_before')) is dict and proof['unowned_raw_before'],
            'Missing protected front-context witness')
    require(not set(NAMES).intersection(proof['unowned_raw_before']) and
            set(RECEIVERS) <= set(proof['unowned_raw_before']),
            'Incorrect current front ownership partition')
    require(type(proof.get('contract')) is dict and
            set(proof['contract']) == {'schema', 'receivers', 'legacy_guide', 'policy'} and
            proof['contract']['schema'] == 'front-compact40-input.v1' and
            digest(proof['contract']['receivers']) == digest(proof['receivers']) and
            digest(proof['contract']['policy']) == digest(POLICY) and
            type(proof['contract']['legacy_guide']) is dict and proof['contract']['legacy_guide'],
            'Missing or mismatched current front derivation inputs')
    return True


@dataclass(frozen=True)
class FrontFinishLock:
    checkpoint: object
    requested: object
    constructor: object
    generator: object
    encoder: object
    policy_sha256: str


def lock_optional(specification, construction, *, is_pipeline, artifact,
                  generation_inputs, phase_outputs, source_artifacts, logical_files):
    if not revision_requested(specification, construction, is_pipeline=is_pipeline):
        return None
    proof = construction[COMPANION]
    roles = ('checkpoint', 'requested', 'constructor', 'generator', 'encoder')
    require(all(key in proof for key in roles), 'Missing current front checkpoint/request/helper')
    files = {key: artifact(proof[key]) for key in roles}
    require(len({row.path for row in files.values()}) == len(roles), 'Aliased current front files')
    checkpoint = files['checkpoint']
    requested = files['requested']
    require(checkpoint.path.name == 'source.blend' and checkpoint.path.parent.name == 'pre-front40'
            and checkpoint.bytes > 0, 'Actual completed legacy front checkpoint required')
    require(requested.path.name == 'requested.json.gz' and requested.path.parent == checkpoint.path.parent
            and requested.bytes > 0, 'Actual pre-encoding current front request required')
    for key in ('checkpoint', 'requested'):
        require(files[key] in phase_outputs, 'Current front artifact missing from actual fresh outputs: ' + key)
        require(files[key].path not in {row.path for row in source_artifacts},
                'Current front phase aliases another source artifact')
    helpers = {'constructor', 'generator', 'encoder'}
    require(set(logical_files) == helpers, 'Incomplete current front logical helper roles')
    for key in helpers:
        require(files[key] == logical_files[key] and files[key] in generation_inputs,
                'Wrong or unlocked actual current front helper: ' + key)
    return FrontFinishLock(*(files[key] for key in roles), digest(POLICY))
