"""Host protocol counterexamples, not native upper-source acceptance."""
from copy import deepcopy
from pathlib import Path
import unittest

from endurance_sedan.qa import upper_finish_report as upper
from endurance_sedan.distance_lod import upper_groups40
from test_front_finish40_binding import File


class UpperBindingTests(unittest.TestCase):
    def test_selected_lower_groups_require_actual_distinct_members(self):
        self.assertEqual(upper.LOWER_POLICY['selective_groups'], [list(key) for key in upper_groups40.SELECTIVE_GROUPS])
        for key, names in upper_groups40.MEMBERS.items():
            upper_groups40.validate_group(key, names)
            for malformed in (names[:-1], (*names, names[0]), (*names[:-1], 'LOD0_Unrelated')):
                with self.subTest(key=key, names=malformed), self.assertRaisesRegex(ValueError, 'members'):
                    upper_groups40.validate_group(key, malformed)
            for malformed in ((1, key[1], key[2]), (2, 'Door_RL', key[2]), (2, key[1], 'Material_Trim')):
                with self.subTest(key=malformed), self.assertRaisesRegex(ValueError, 'Unknown'):
                    upper_groups40.validate_group(malformed, names)

    def setUp(self):
        self.spec = {'original_packaging': {upper.SELECTOR: deepcopy(upper.POLICY)}}
        self.proof = {'schema': upper.CONSTRUCTION_SCHEMA, 'policy': deepcopy(upper.POLICY),
            'source_phase': 'pre-lod', 'before': {name: {} for name in upper.INPUTS},
            'before_frames': {name: {} for name in upper.INPUTS},
            'before_material_response': {name: {} for name in upper.INPUTS},
            'native': {'after': {name: {} for name in upper.NAMES}},
            'base_native': {'after': {name: {} for name in upper.NAMES}},
            'unowned_raw_before': {name: 'a' * 64 for name in upper.RETAINED},
            'unowned_raw_unchanged': True}
        self.construction = {upper.COMPANION: self.proof}
        self.files = {key: File(Path(path)) for key, path in {
            'checkpoint': 'data/pre-upper40/source.blend', 'requested': 'data/pre-upper40/requested.json.gz',
            'base_requested': 'data/pre-upper40/base-requested.json.gz',
            'native_intermediate': 'data/pre-upper40/native-intermediate.json.gz',
            'constructor': 'tools/upper_finish40/construction.py', 'generator': 'tools/upper_sections40/__init__.py',
            'encoder': 'tools/corner_encoding.py', 'design': 'tools/upper_sections40/sections.json',
            **{role: 'tools/upper_sections40/native_sections/' + filename for role, filename in (
                ('native_generator', '__init__.py'), ('roof_generator', 'roof.py'),
                ('roof_design', 'roof_sections.json'), ('frame_generator', 'frames.py'),
                ('frame_design', 'frame_sections.json'))}}.items()}
        self.proof.update(self.files)
        self.arguments = {'is_pipeline': True, 'artifact': lambda row: row,
            'generation_inputs': [self.files[key] for key in upper.HELPER_ROLES],
            'phase_outputs': [self.files[key] for key in upper.PHASE_NAMES],
            'source_artifacts': [File(Path('data/current.blend'))],
            'logical_files': {key: self.files[key] for key in upper.HELPER_ROLES}}

    def lock(self):
        return upper.lock_optional(self.spec, self.construction, **self.arguments)

    def test_complete_current_roles_and_retained_windshield(self):
        self.assertEqual((len(upper.INPUTS), len(upper.NAMES)), (31, 28))
        self.assertNotIn('LOD0_Windshield', upper.NAMES)
        self.assertEqual(self.lock().design, self.files['design'])

    def test_absent_revision_preserves_original_path(self):
        self.assertIsNone(upper.lock_optional({'original_packaging': {}}, {}, **self.arguments))

    def test_unknown_and_null_revision_reject(self):
        for value in (None, {}, {**upper.POLICY, 'normal_angle_degrees': 1}):
            self.spec['original_packaging'][upper.SELECTOR] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Unknown/null'):
                self.lock()

    def test_v1_rejects_current_upper(self):
        self.arguments['is_pipeline'] = False
        with self.assertRaisesRegex(ValueError, 'binding v2'):
            self.lock()

    def test_undeclared_or_missing_companion_reject(self):
        self.spec['original_packaging'].clear()
        with self.assertRaisesRegex(ValueError, 'Undeclared'):
            self.lock()
        self.spec['original_packaging'][upper.SELECTOR] = upper.POLICY
        self.construction.clear()
        with self.assertRaisesRegex(ValueError, 'Missing declared'):
            self.lock()

    def test_every_input_role_and_frame_is_required(self):
        for key in ('before', 'before_frames', 'before_material_response'):
            original = deepcopy(self.proof[key])
            for name in upper.INPUTS:
                self.proof[key] = {k: v for k, v in original.items() if k != name}
                with self.subTest(key=key, role=name), self.assertRaisesRegex(ValueError, 'input domain'):
                    self.lock()
            self.proof[key] = original

    def test_windshield_cannot_enter_owned_domain(self):
        self.proof['native']['after']['LOD0_Windshield'] = {}
        with self.assertRaisesRegex(ValueError, 'output domain'):
            self.lock()

    def test_complete_intermediate_native_roles_are_required(self):
        original = deepcopy(self.proof['base_native'])
        for name in upper.NAMES:
            self.proof['base_native'] = deepcopy(original)
            del self.proof['base_native']['after'][name]
            with self.subTest(role=name), self.assertRaisesRegex(ValueError, 'intermediate domain'):
                self.lock()
        self.proof['base_native'] = deepcopy(original)
        self.proof['base_native']['after']['LOD0_Unrelated'] = {}
        with self.assertRaisesRegex(ValueError, 'intermediate domain'):
            self.lock()

    def test_base_request_and_intermediate_cannot_alias_or_substitute(self):
        for role in ('base_requested', 'native_intermediate'):
            original = self.proof[role]
            self.proof[role] = self.proof['requested']
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'Aliased'):
                self.lock()
            self.proof[role] = File(Path('data/pre-upper40/other.json.gz'))
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'stage artifact'):
                self.lock()
            self.proof[role] = original

    def test_all_native_design_and_helper_roles_are_required(self):
        for role in ('native_generator', 'roof_generator', 'roof_design', 'frame_generator', 'frame_design'):
            original = self.proof[role]
            del self.proof[role]
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'Missing upper'):
                self.lock()
            self.proof[role] = original
        self.assertEqual(set(self.lock().artifacts), set(self.files.values()))

    def test_retained_pane_cannot_be_omitted(self):
        self.proof['unowned_raw_before'].pop('LOD0_Windshield')
        with self.assertRaisesRegex(ValueError, 'ownership partition'):
            self.lock()

    def test_phase_artifacts_and_design_must_be_bound(self):
        for key in ('phase_outputs', 'generation_inputs'):
            original = self.arguments[key]
            for missing in original:
                self.arguments[key] = [row for row in original if row != missing]
                with self.subTest(role=missing.path), self.assertRaisesRegex(ValueError, 'missing from|unlocked actual'):
                    self.lock()
            self.arguments[key] = original

    def test_historical_or_aliased_checkpoint_rejects(self):
        self.proof['checkpoint'] = File(Path('data/pre-front/source.blend'))
        with self.assertRaisesRegex(ValueError, 'pre-upper checkpoint'):
            self.lock()
        self.proof['checkpoint'] = self.files['checkpoint']
        self.proof['requested'] = self.files['checkpoint']
        with self.assertRaisesRegex(ValueError, 'Aliased'):
            self.lock()

    def test_included_unrelated_design_is_not_the_logical_source(self):
        other = File(Path('tools/private/sections.json'))
        self.arguments['generation_inputs'].append(other)
        self.proof['design'] = other
        with self.assertRaisesRegex(ValueError, 'Wrong or unlocked'):
            self.lock()


if __name__ == '__main__':
    unittest.main()
