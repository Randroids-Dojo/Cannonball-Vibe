"""Host-only selection and file binding for the authored current upper assembly."""
from dataclasses import dataclass

if __package__:
    from .front_finish_report import digest, require
else:
    from front_finish_report import digest, require

NAMES = tuple(sorted((
    'LOD0_Backlight', 'LOD0_BacklightSeal', 'LOD0_Roof', 'LOD0_WindshieldSeal',
    *(f'LOD0_{part}_{side}' for part in ('DoorFrame', 'DoorGlassSeal', 'DoorGlass')
      for side in ('FL', 'FR', 'RL', 'RR')),
    *(f'LOD0_Door_{side}' for side in ('RL', 'RR')),
    *(f'LOD0_{part}_{side}' for part in ('PillarA', 'PillarC', 'RoofSideRail') for side in ('L', 'R')),
    *(f'LOD0_StampedPillar_{side}' for side in ('BL', 'BR', 'CL', 'CR')),
)))
RETAINED = ('LOD0_DoorApertureSeal_RL', 'LOD0_DoorApertureSeal_RR', 'LOD0_Windshield')
INPUTS = tuple(sorted((*NAMES, *RETAINED)))
SELECTOR = 'upper_finish_revision40'
COMPANION = 'upper_finish40'
CONSTRUCTION_SCHEMA = 'source-upper-construction40.v2'
OBSERVATION_SCHEMA = 'source-upper-observation40.v2'
PHASE_NAMES = {'checkpoint': 'source.blend', 'base_requested': 'base-requested.json.gz',
               'native_intermediate': 'native-intermediate.json.gz', 'requested': 'requested.json.gz'}
HELPER_ROLES = ('constructor', 'generator', 'encoder', 'design', 'native_generator',
                'roof_generator', 'roof_design', 'frame_generator', 'frame_design')
FILE_ROLES = (*PHASE_NAMES, *HELPER_ROLES)
POLICY = {
    'schema': 'source-upper-sections40.v2', 'members': list(NAMES), 'inputs': list(INPUTS),
    'retained': list(RETAINED), 'normal_angle_degrees': .025,
    'normal_unit_error': .000001, 'uv_absolute': .00001,
    'geometry': 'Explicit current-input sections with original retained boundary references',
    'source': 'Versioned editable upper_sections40 designs; no historical scene or report input',
    'native_intermediate': 'Regenerate and encode all28 base parts before observing inputs to six authored native sections',
    'windshield': 'Original planar raw mesh, flat native field and live Solidify retained',
    'frames': 'Original objects, parents, transforms, drivers and rest pose retained',
}
LOWER_POLICY = {
    'schema': 'current-upper-lower40.v1', 'formed_pane': 'LOD0_Backlight', 'levels': [1, 2],
    'formed_pane_policy': 'Complete literal current shell, UV, material and affine normal fields',
    'windshield': 'Unchanged source37 planar construction and lower adapter',
    'selective_groups': [[2, 'Door_FL', 'Material_Paint'], [2, 'Door_FR', 'Material_Paint'],
                         [2, 'Door_RL', 'Material_Rubber']],
    'initial_component_frame': 'Exact evaluated original object frame before component simplification; unchanged final rigid-parent batch',
    'unrelated_recipe': 'Unchanged cabin29 ratios, omissions, all other selective groups and literal budgets',
}


def revision_requested(specification, construction, *, is_pipeline):
    packaging = specification['original_packaging']
    require(type(packaging) is dict, 'Missing locked upper packaging')
    if SELECTOR not in packaging:
        require(COMPANION not in construction, 'Undeclared current upper companion')
        return False
    require(is_pipeline is True, 'Current upper requires source binding v2')
    require(digest(packaging[SELECTOR]) == digest(POLICY), 'Unknown/null current upper revision')
    require(COMPANION in construction, 'Missing declared current upper companion')
    proof = construction[COMPANION]
    require(type(proof) is dict and proof.get('schema') == CONSTRUCTION_SCHEMA
            and proof.get('policy') == POLICY and proof.get('source_phase') == 'pre-lod',
            'Wrong current upper construction policy or phase')
    for key in ('before', 'before_material_response', 'before_frames'):
        require(type(proof.get(key)) is dict and set(proof[key]) == set(INPUTS),
                'Incomplete actual upper input domain: ' + key)
    require(type(proof.get('native')) is dict and set(proof['native'].get('after', {})) == set(NAMES),
            'Incomplete current upper native output domain')
    require(type(proof.get('base_native')) is dict and set(proof['base_native'].get('after', {})) == set(NAMES),
            'Incomplete actual native intermediate domain')
    require(proof.get('unowned_raw_unchanged') is True and
            type(proof.get('unowned_raw_before')) is dict and
            set(RETAINED) <= set(proof['unowned_raw_before']) and
            not set(NAMES).intersection(proof['unowned_raw_before']),
            'Incorrect current upper ownership partition')
    return True


@dataclass(frozen=True)
class UpperFinishLock:
    checkpoint: object
    base_requested: object
    native_intermediate: object
    requested: object
    constructor: object
    generator: object
    encoder: object
    design: object
    native_generator: object
    roof_generator: object
    roof_design: object
    frame_generator: object
    frame_design: object
    policy_sha256: str

    @property
    def artifacts(self):
        return tuple(getattr(self, role) for role in FILE_ROLES)


def lock_optional(specification, construction, *, is_pipeline, artifact,
                  generation_inputs, phase_outputs, source_artifacts, logical_files):
    if not revision_requested(specification, construction, is_pipeline=is_pipeline):
        return None
    proof = construction[COMPANION]
    roles = FILE_ROLES
    require(all(key in proof for key in roles), 'Missing upper checkpoint/request/helper/design')
    files = {key: artifact(proof[key]) for key in roles}
    require(len({row.path for row in files.values()}) == len(roles), 'Aliased current upper files')
    checkpoint, requested = files['checkpoint'], files['requested']
    require(checkpoint.path.name == 'source.blend' and checkpoint.path.parent.name == 'pre-upper40'
            and checkpoint.bytes > 0, 'Actual pre-upper checkpoint required')
    for key, filename in PHASE_NAMES.items():
        require(files[key].path.name == filename and files[key].path.parent == checkpoint.path.parent
                and files[key].bytes > 0, 'Actual upper stage artifact required: ' + key)
        require(files[key] in phase_outputs, 'Upper phase missing from fresh outputs: ' + key)
        require(files[key].path not in {row.path for row in source_artifacts},
                'Upper phase aliases another source artifact')
    helpers = set(HELPER_ROLES)
    require(set(logical_files) == helpers, 'Incomplete upper logical helper roles')
    for key in helpers:
        require(files[key] == logical_files[key] and files[key] in generation_inputs,
                'Wrong or unlocked actual upper helper: ' + key)
    return UpperFinishLock(*(files[key] for key in roles), digest(POLICY))
