"""Host provenance controls only; these fixtures are not native source evidence."""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest

from endurance_sedan.qa import front_finish_report as front
from endurance_sedan.qa.source_binding_v2 import validate_stage
from endurance_sedan.qa.gate import (FRONT40_STAGE_CONTRACTS, V2_STAGE_CONTRACTS,
                                    check_stage_inventory, source_stages)


@dataclass(frozen=True)
class File:
    path: Path
    bytes: int = 1
    sha256: str = 'a' * 64


class FrontBindingTests(unittest.TestCase):
    def setUp(self):
        self.spec = {'original_packaging': {front.SELECTOR: deepcopy(front.POLICY)}}
        before = {name: {'name': name} for name in front.NAMES}
        receivers = {name: {'name': name} for name in front.RECEIVERS}
        self.proof = {
            'schema': 'source-front-finish-construction40.v1',
            'policy': deepcopy(front.POLICY), 'source_phase': 'pre-lod',
            'before': before, 'receivers': receivers,
            'before_material_response': {name: {} for name in (*front.NAMES, *front.RECEIVERS)},
            'native': {'after': deepcopy(before)},
            'unowned_raw_unchanged': True,
            'unowned_raw_before': {name: 'b' * 64 for name in (*front.RECEIVERS, 'LOD0_Hood')},
            'contract': {'schema': 'front-compact40-input.v1', 'receivers': deepcopy(receivers),
                         'legacy_guide': {'fixture': 'host protocol only'},
                         'policy': deepcopy(front.POLICY)},
        }
        self.construction = {front.COMPANION: self.proof}
        self.files = {key: File(Path(path)) for key, path in {
            'checkpoint': 'data/pre-front40/source.blend',
            'requested': 'data/pre-front40/requested.json.gz',
            'constructor': 'tools/front_finish40/construction.py',
            'generator': 'tools/front_compact40/__init__.py',
            'encoder': 'tools/corner_encoding.py',
        }.items()}
        self.proof.update(self.files)
        self.arguments = {
            'is_pipeline': True, 'artifact': lambda row: row,
            'generation_inputs': [self.files[key] for key in ('constructor', 'generator', 'encoder')],
            'phase_outputs': [self.files[key] for key in ('checkpoint', 'requested')],
            'source_artifacts': [File(Path('data/other/source.blend'))],
            'logical_files': {key: self.files[key] for key in ('constructor', 'generator', 'encoder')},
        }

    def lock(self):
        return front.lock_optional(self.spec, self.construction, **self.arguments)

    def test_absent_revision_preserves_legacy_path(self):
        self.assertIsNone(front.lock_optional({'original_packaging': {}}, {},
                                             **self.arguments))

    def test_complete_host_binding_retains_distinct_roles(self):
        value = self.lock()
        self.assertEqual(value.checkpoint, self.files['checkpoint'])
        self.assertEqual(value.requested, self.files['requested'])
        self.assertEqual(value.policy_sha256, front.digest(front.POLICY))

    def test_unknown_null_and_changed_revision_reject(self):
        for policy in (None, {}, {**front.POLICY, 'normal_angle_degrees': 1}):
            with self.subTest(policy=policy):
                self.spec['original_packaging'][front.SELECTOR] = policy
                with self.assertRaisesRegex(ValueError, 'Unknown/null'):
                    self.lock()

    def test_v1_cannot_select_current_revision(self):
        self.arguments['is_pipeline'] = False
        with self.assertRaisesRegex(ValueError, 'requires source binding v2'):
            self.lock()

    def test_undeclared_or_missing_companion_rejects(self):
        self.spec['original_packaging'].clear()
        with self.assertRaisesRegex(ValueError, 'Undeclared'):
            self.lock()
        self.spec['original_packaging'][front.SELECTOR] = front.POLICY
        self.construction.clear()
        with self.assertRaisesRegex(ValueError, 'Missing declared'):
            self.lock()

    def test_wrong_phase_policy_and_schema_reject(self):
        for key, value, diagnostic in (
            ('source_phase', 'pre-front', 'phase'),
            ('schema', 'source-front-finish-construction39.v1', 'witness'),
            ('policy', {}, 'policy differs'),
        ):
            with self.subTest(key=key):
                held = self.proof[key]
                self.proof[key] = value
                with self.assertRaisesRegex(ValueError, diagnostic):
                    self.lock()
                self.proof[key] = held

    def test_missing_extra_or_swapped_input_role_rejects(self):
        for domain in ('before', 'receivers', 'before_material_response'):
            original = deepcopy(self.proof[domain])
            for action in ('omit', 'extra', 'swap'):
                with self.subTest(domain=domain, action=action):
                    value = deepcopy(original)
                    if action in ('omit', 'swap'):
                        value.pop(next(iter(value)))
                    if action in ('extra', 'swap'):
                        value['LOD0_Unowned'] = {}
                    self.proof[domain] = value
                    with self.assertRaisesRegex(ValueError, 'input domain'):
                        self.lock()
            self.proof[domain] = original

    def test_native_output_requires_all_three_panels(self):
        self.proof['native']['after'].pop(front.NAMES[-1])
        with self.assertRaisesRegex(ValueError, 'three-panel native witness'):
            self.lock()

    def test_owned_and_unowned_partitions_cannot_overlap_or_omit_receiver(self):
        for action in ('overlap', 'receiver'):
            original = deepcopy(self.proof['unowned_raw_before'])
            if action == 'overlap':
                self.proof['unowned_raw_before'][front.NAMES[0]] = 'b' * 64
            else:
                self.proof['unowned_raw_before'].pop(front.RECEIVERS[0])
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'ownership partition'):
                self.lock()
            self.proof['unowned_raw_before'] = original

    def test_mismatched_or_missing_derivation_inputs_reject(self):
        original = deepcopy(self.proof['contract'])
        changes = (
            ('schema', 'front-compact39-input.v1'),
            ('receivers', {}), ('legacy_guide', {}), ('policy', {}), ('extra', {}),
        )
        for key, value in changes:
            with self.subTest(key=key):
                self.proof['contract'] = {**deepcopy(original), key: value}
                with self.assertRaisesRegex(ValueError, 'derivation inputs'):
                    self.lock()
        self.proof['contract'] = original

    def test_each_phase_output_and_helper_must_be_bound(self):
        for collection in ('phase_outputs', 'generation_inputs'):
            original = list(self.arguments[collection])
            for missing in original:
                with self.subTest(collection=collection, missing=missing.path):
                    self.arguments[collection] = [row for row in original if row != missing]
                    with self.assertRaisesRegex(ValueError, 'missing from actual fresh outputs|unlocked actual'):
                        self.lock()
            self.arguments[collection] = original

    def test_wrong_logical_helper_is_not_authorized_by_membership(self):
        other = File(Path('tools/private/constructor.py'))
        self.arguments['generation_inputs'].append(other)
        self.proof['constructor'] = other
        with self.assertRaisesRegex(ValueError, 'Wrong or unlocked actual'):
            self.lock()

    def test_aliasing_distinct_artifacts_rejects(self):
        self.proof['requested'] = self.proof['checkpoint']
        with self.assertRaisesRegex(ValueError, 'Aliased'):
            self.lock()

    def test_aliasing_another_source_role_rejects(self):
        self.arguments['source_artifacts'].append(self.files['checkpoint'])
        with self.assertRaisesRegex(ValueError, 'aliases another source'):
            self.lock()

    def test_earlier_pre_front_checkpoint_cannot_replace_completed_legacy(self):
        old = File(Path('data/pre-front/source.blend'))
        self.proof['checkpoint'] = old
        self.arguments['phase_outputs'].append(old)
        with self.assertRaisesRegex(ValueError, 'completed legacy front checkpoint'):
            self.lock()

    def test_request_must_belong_to_its_checkpoint_directory(self):
        other = File(Path('data/other/requested.json.gz'))
        self.proof['requested'] = other
        self.arguments['phase_outputs'].append(other)
        with self.assertRaisesRegex(ValueError, 'pre-encoding current front request'):
            self.lock()


class FrontStageTests(unittest.TestCase):
    """Reject incomplete host receipts; no fixture is native acceptance."""
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        request = Path(self.directory.name) / 'requested.json'
        request.write_text(json.dumps({'parts': {name: {'triangles': [[0, 1, 2]]}
                                               for name in front.NAMES}}))
        self.lock = SimpleNamespace(source=File(Path('current.blend')),
            binding=File(Path('binding.json')),
            pipeline=SimpleNamespace(pre_front=File(Path('pre-front.blend')),
                front_finish=SimpleNamespace(requested=File(request),
                    checkpoint=File(Path('completed-legacy.blend')))))
        self.report = {'mode': 'front', 'status': 'passed', 'source_sha256': 'a' * 64,
            'source_binding_sha256': 'a' * 64, 'all_locked_inputs_unchanged': True,
            'source_saved': False, 'human_approval_reference': None,
            'pre_front_source_sha256': 'a' * 64, 'actual_pre_front_checkpoint_exact': True,
            'source_corners': 9, 'native_completed_legacy_front_observed': True,
            'completed_legacy_front_sha256': 'a' * 64, 'current_front_members': list(front.NAMES),
            'current_front_panels': {name: {'triangles': 1, 'corners': 3, 'complete_target_fields': [{}]}
                                     for name in front.NAMES},
            'payload': {'fixture_only': True}}

    def check(self):
        return validate_stage(self.report, self.lock, 'front')

    def test_selected_three_panel_receipt(self):
        self.assertEqual(self.check()['status'], 'passed')

    def test_earlier_checkpoint_is_not_completed_legacy(self):
        self.report['completed_legacy_front_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'completed legacy checkpoint'):
            self.check()

    def test_reports_only_checkpoint_claim_rejects(self):
        self.report['native_completed_legacy_front_observed'] = False
        with self.assertRaisesRegex(ValueError, 'completed legacy checkpoint'):
            self.check()

    def test_bumper_only_receipt_does_not_cover_fenders(self):
        self.report['current_front_panels'].pop(front.NAMES[1])
        with self.assertRaisesRegex(ValueError, 'all three current panels'):
            self.check()

    def test_missing_corner_field_rows_reject(self):
        self.report['current_front_panels'][front.NAMES[2]]['complete_target_fields'] = []
        with self.assertRaisesRegex(ValueError, 'field inventory differs'):
            self.check()

    def test_wrong_aggregate_count_rejects(self):
        self.report['source_corners'] = 3
        with self.assertRaisesRegex(ValueError, 'aggregate field inventory'):
            self.check()

    def test_legacy_source_cannot_claim_selected_revision(self):
        self.lock.pipeline.front_finish = None
        with self.assertRaisesRegex(ValueError, 'Legacy source stage unexpectedly'):
            self.check()

    def test_unselected_legacy_receipt_remains_supported(self):
        self.lock.pipeline.front_finish = None
        self.report['native_completed_legacy_front_observed'] = False
        for key in ('current_front_members', 'current_front_panels', 'completed_legacy_front_sha256'):
            self.report.pop(key)
        self.assertEqual(self.check()['status'], 'passed')


class FrontStageInventoryTests(unittest.TestCase):
    """The selected source cannot omit its native counterexamples."""

    def test_selected_front_adds_controls_to_every_supported_pipeline(self):
        for index, (detail, cover) in enumerate(((False, False), (True, False),
                                               (False, True), (True, True))):
            for selected in (False, True):
                with self.subTest(detail=detail, cover=cover, selected=selected):
                    lock = SimpleNamespace(pipeline=SimpleNamespace(
                        repeated_detail=object() if detail else None,
                        valance_cover=object() if cover else None,
                        front_finish=object() if selected else None))
                    stages = source_stages(lock)
                    expected = (FRONT40_STAGE_CONTRACTS if selected else V2_STAGE_CONTRACTS)[index]
                    self.assertEqual(stages, expected)
                    rows = [{'name': name, 'status': 'passed'} for name in stages]
                    check_stage_inventory(rows, stages)
                    if selected:
                        self.assertEqual(stages[stages.index('distance-fields') + 1],
                                         'current-front-controls')
                        with self.assertRaisesRegex(ValueError, 'Complete ordered'):
                            check_stage_inventory([row for row in rows
                                                   if row['name'] != 'current-front-controls'], stages)

    def test_failed_or_duplicate_current_controls_cannot_complete_inventory(self):
        stages = FRONT40_STAGE_CONTRACTS[-1]
        rows = [{'name': name, 'status': 'passed'} for name in stages]
        selected = next(row for row in rows if row['name'] == 'current-front-controls')
        selected['status'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'Every stage must pass'):
            check_stage_inventory(rows, stages)
        selected['status'] = 'passed'
        with self.assertRaisesRegex(ValueError, 'Complete ordered'):
            check_stage_inventory([*rows, selected], stages)


if __name__ == '__main__':
    unittest.main()
