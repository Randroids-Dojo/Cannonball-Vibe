"""Host source-role counterexamples; actual native construction is separate."""
from copy import deepcopy
from pathlib import Path
import unittest

from endurance_sedan.qa import tire_finish_report as tire
from test_front_finish40_binding import File


class CurrentTireBindingTests(unittest.TestCase):
    def setUp(self):
        self.spec = {'original_packaging': {tire.SELECTOR: deepcopy(tire.POLICY)}}
        before = {name: {'name': name, 'mesh': {'source': name, 'version': 38}} for name in tire.NAMES}
        after = {name: {'name': name, 'mesh': {'source': name, 'version': 40}} for name in tire.NAMES}
        legacy = {'tires': {name: {'after_native': before[name]} for name in tire.NAMES}}
        self.proof = {'schema': tire.SCHEMA, 'policy': deepcopy(tire.POLICY), 'source_phase': 'pre-lod',
            'legacy_construction_sha256': tire.digest(legacy), 'before': deepcopy(before), 'after': deepcopy(after),
            'tires': {name: {'name': name, 'policy': deepcopy(tire.POLICY), 'historical52_control_exact': True,
                             'before': deepcopy(before[name]['mesh']), 'after': deepcopy(after[name]['mesh'])} for name in tire.NAMES}}
        self.construction = {'tire_grooves38': legacy, tire.COMPANION: self.proof}
        self.checkpoint = File(Path('data/pre-tire40/source.blend'))
        self.helpers = {key: File(Path('tools/vehicles/endurance_sedan') / name) for key, name in tire.HELPERS.items()}
        self.proof.update(checkpoint=self.checkpoint, **self.helpers)
        self.arguments = {'artifact': lambda row: row, 'generation_inputs': list(self.helpers.values()),
            'phase_outputs': [self.checkpoint], 'source_artifacts': [File(Path('data/final.blend'))],
            'logical_files': dict(self.helpers)}

    def lock(self):
        return tire.lock_optional(self.spec, self.construction, **self.arguments)

    def test_complete_selected_stage(self):
        self.assertEqual(len(self.lock().artifacts), 9)
        self.assertEqual(self.lock().checkpoint, self.checkpoint)

    def test_absent_selector_preserves_original_path(self):
        self.assertIsNone(tire.lock_optional({'original_packaging': {}}, {}, **self.arguments))

    def test_unknown_null_or_loosened_policy_rejects(self):
        for policy in (None, {}, {**tire.POLICY, 'current_stations': 40}, {**tire.POLICY, 'form_error_m': .1}):
            self.spec['original_packaging'][tire.SELECTOR] = policy
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, 'Unknown/null'):
                self.lock()

    def test_missing_or_undeclared_companion_rejects(self):
        self.spec['original_packaging'].clear()
        with self.assertRaisesRegex(ValueError, 'Undeclared'):
            self.lock()
        self.spec['original_packaging'][tire.SELECTOR] = tire.POLICY
        self.construction.pop(tire.COMPANION)
        with self.assertRaisesRegex(ValueError, 'Missing declared'):
            self.lock()

    def test_each_of_four_members_is_required_in_each_domain(self):
        for key in ('before', 'after', 'tires'):
            original = self.proof[key]
            for name in tire.NAMES:
                self.proof[key] = {n: v for n, v in original.items() if n != name}
                with self.subTest(key=key, name=name), self.assertRaisesRegex(ValueError, 'Incomplete current tire'):
                    self.lock()
            self.proof[key] = original

    def test_coherently_rehashed_historical_substitution_rejects(self):
        self.construction['tire_grooves38']['tires'][tire.NAMES[0]]['after_native']['mesh']['version'] = 999
        self.proof['legacy_construction_sha256'] = tire.digest(self.construction['tire_grooves38'])
        with self.assertRaisesRegex(ValueError, 'not the actual historical'):
            self.lock()

    def test_complete_witness_must_match_actual_mesh(self):
        self.proof['tires'][tire.NAMES[0]]['after']['version'] = 999
        with self.assertRaisesRegex(ValueError, 'native/witness'):
            self.lock()

    def test_checkpoint_cannot_be_omitted_or_alias_a_source(self):
        self.arguments['phase_outputs'].clear()
        with self.assertRaisesRegex(ValueError, 'missing or aliases'):
            self.lock()
        self.arguments['phase_outputs'].append(self.checkpoint)
        self.arguments['source_artifacts'].append(self.checkpoint)
        with self.assertRaisesRegex(ValueError, 'missing or aliases'):
            self.lock()

    def test_every_actual_helper_role_is_locked(self):
        for key in tire.HELPERS:
            original = self.proof[key]
            self.proof[key] = File(Path('tools/substituted.py'))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Missing or substituted'):
                self.lock()
            self.proof[key] = original


if __name__ == '__main__':
    unittest.main()
