"""Portable selection and file-role checks for the optional current44 stage."""
from dataclasses import dataclass
if __package__:
    from ..tire_policy40 import POLICY
    from .front_finish_report import digest, require
else:
    import importlib.util
    from pathlib import Path
    from front_finish_report import digest, require
    _spec = importlib.util.spec_from_file_location('_source_tire_policy40', Path(__file__).parents[1] / 'tire_policy40.py')
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    POLICY = _module.POLICY

NAMES = tuple(POLICY['members'])
SELECTOR = 'tire_radial_revision40'
COMPANION = 'tire_radial40'
SCHEMA = 'source-tire-radial-construction40.v1'
OBSERVATION_SCHEMA = 'source-tire-radial-observation40.v1'
HELPERS = {'constructor': 'tire_finish40.py', 'generator': 'current_tire40.py',
           'grooves': 'tire_grooves38.py', 'wheels': 'wheels.py', 'geometry': 'geometry.py',
           'surface': 'tire_surface.py', 'encoder': 'corner_encoding.py', 'policy_file': 'tire_policy40.py'}


def revision_requested(specification, construction):
    packaging = specification['original_packaging']
    if SELECTOR not in packaging:
        require(COMPANION not in construction, 'Undeclared current tire companion')
        return False
    require(packaging[SELECTOR] == POLICY, 'Unknown/null current tire policy')
    require('tire_grooves38' in construction, 'Current tire requires genuine historical groove stage')
    require(COMPANION in construction, 'Missing declared current tire companion')
    proof = construction[COMPANION]
    require(proof.get('schema') == SCHEMA and proof.get('policy') == POLICY
            and proof.get('source_phase') == 'pre-lod', 'Wrong current tire construction phase/policy')
    require(proof.get('legacy_construction_sha256') == digest(construction['tire_grooves38']),
            'Current tire historical construction differs')
    for key in ('before', 'after', 'tires'):
        require(set(proof.get(key, {})) == set(NAMES), 'Incomplete current tire domain: ' + key)
    for name in NAMES:
        require(proof['tires'][name].get('policy') == POLICY
                and proof['tires'][name].get('name') == name
                and proof['tires'][name].get('historical52_control_exact') is True,
                'Missing current tire actual construction identity: ' + name)
        require(proof['before'][name] == construction['tire_grooves38']['tires'][name]['after_native'],
                'Current tire predecessor is not the actual historical result: ' + name)
        require(proof['tires'][name]['before'] == proof['before'][name]['mesh']
                and proof['tires'][name]['after'] == proof['after'][name]['mesh'],
                'Current tire complete native/witness fields differ: ' + name)
    return True


@dataclass(frozen=True)
class TireFinishLock:
    checkpoint: object
    helpers: tuple

    @property
    def artifacts(self):
        return (self.checkpoint, *self.helpers)


def lock_optional(specification, construction, *, artifact, generation_inputs,
                  phase_outputs, source_artifacts, logical_files):
    if not revision_requested(specification, construction):
        return None
    proof = construction[COMPANION]
    checkpoint = artifact(proof['checkpoint'])
    require(checkpoint.path.name == 'source.blend' and checkpoint.path.parent.name == 'pre-tire40',
            'Current tire checkpoint role/path differs')
    require(checkpoint in phase_outputs and checkpoint not in source_artifacts,
            'Current tire checkpoint missing or aliases another source role')
    helpers = tuple(artifact(proof[key]) for key in HELPERS)
    require(len({row.path for row in helpers}) == len(HELPERS)
            and checkpoint.path not in {row.path for row in helpers}, 'Aliased current tire helper roles')
    for key, row in zip(HELPERS, helpers, strict=True):
        require(row in generation_inputs and logical_files.get(key) == row,
                'Missing or substituted current tire helper: ' + key)
    return TireFinishLock(checkpoint, helpers)
