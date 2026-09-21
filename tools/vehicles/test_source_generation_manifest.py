"""Small host command-protocol fixtures; these are not Blender source evidence."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import source_generation_manifest as bridge


class CommandOutputContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.base = 'data/assets/vehicles/sources/endurance-sedan-generation/pre-lod/'
        self.source = self.file(bridge.SOURCE)
        self.pre_lod = self.file(self.base + 'source.blend')
        self.construction = self.file('data/assets/vehicles/sources/endurance-sedan.construction.json.gz')
        self.file(self.base + 'source.construction.json.gz')
        self.historical = {key: self.file(self.base + name) for key, name in (
            ('source', 'shoulder/source.blend'), ('construction_packet', 'shoulder/source.shoulder.json.gz'),
            ('shoulder_profile', 'shoulder/source.shoulder-profile.json'))}
        self.lower = self.file('data/assets/vehicles/sources/endurance-sedan.lower.json.gz')
        self.report = self.file('data/assets/vehicles/sources/endurance-sedan-generation/native-finalization.json')
        self.generation = {'source_outputs': [dict(row, role=role) for role, row in (
            ('pre_front_source', self.file(self.base + 'pre-front/source.blend')),
            ('lower_bundle', self.lower), ('native_finalization', self.report))]}
        self.portable = {'roles': {'source': self.source, 'construction': self.construction}}
        for name in ('pre-grooves/source.blend', 'pre-detail/source.blend',
                     'pre-cover/source.blend', 'pre-cover/requested.json.gz',
                     'pre-front40/source.blend', 'pre-front40/requested.json.gz',
                     'pre-upper40/source.blend', 'pre-upper40/requested.json.gz'):
            self.file(self.base + name)
        self.packaging({})

    def file(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'host protocol fixture, not a native asset\n')
        return bridge.file_row(path, self.root)

    def packaging(self, value):
        path = self.root / bridge.SPECIFICATION
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'original_packaging': value}), encoding='utf-8')

    def contracts(self):
        return bridge.phase_output_contract(
            self.root, self.generation, self.historical, self.portable, self.pre_lod)

    def command(self, contract, windows=False):
        rows, destinations = contract
        recorded = 'C:/recorded/project' if windows else '/recorded/project'
        argv = ['blender', '--']
        for option, row in destinations.items():
            path = recorded + '/' + row['path']
            argv += [option, path.replace('/', '\\') if windows else path]
        return {'outputs': deepcopy(rows), 'argv': argv}, recorded

    def test_both_phases_accept_portable_windows_and_posix_history(self):
        for contract in self.contracts():
            for windows in (False, True):
                command, root = self.command(contract, windows)
                bridge.validate_phase_command(command, *contract, root)

    def test_complete_unique_output_identity_is_required(self):
        for contract in self.contracts():
            for kind in ('empty', 'missing', 'duplicate', 'extra', 'hash', 'bytes'):
                with self.subTest(phase=len(contract[0]), mutation=kind):
                    command, root = self.command(contract)
                    rows = command['outputs']
                    if kind == 'empty':
                        rows.clear()
                    elif kind == 'missing':
                        rows.pop()
                    elif kind == 'duplicate':
                        rows.append(deepcopy(rows[0]))
                    elif kind == 'extra':
                        rows.append({**rows[0], 'path': 'data/unrelated.blend'})
                    elif kind == 'hash':
                        rows[0]['sha256'] = '0' * 64
                    else:
                        rows[0]['bytes'] += 1
                    with self.assertRaisesRegex(ValueError, 'output roles or complete inventory'):
                        bridge.validate_phase_command(command, *contract, root)

    def test_every_output_argument_is_bound_to_its_role(self):
        for contract in self.contracts():
            for option in contract[1]:
                for windows in (False, True):
                    with self.subTest(option=option, windows=windows):
                        command, root = self.command(contract, windows)
                        command['argv'][command['argv'].index(option) + 1] += '.unrelated'
                        with self.assertRaisesRegex(ValueError, 'destination differs'):
                            bridge.validate_phase_command(command, *contract, root)

    def test_duplicate_output_argument_is_rejected(self):
        contract = self.contracts()[1]
        command, root = self.command(contract)
        command['argv'] += ['--output', root + '/' + self.source['path']]
        with self.assertRaisesRegex(ValueError, 'Missing/duplicate native argument'):
            bridge.validate_phase_command(command, *contract, root)

    def test_packaging_selected_checkpoints_cannot_be_omitted(self):
        for key, names in (
            ('tire_groove_revision38', ['pre-grooves/source.blend']),
            ('repeated_detail_revision38', ['pre-detail/source.blend']),
            ('valance_cover_revision39', ['pre-cover/source.blend', 'pre-cover/requested.json.gz']),
            ('front_finish_revision40', ['pre-front40/source.blend', 'pre-front40/requested.json.gz']),
            ('upper_finish_revision40', ['pre-upper40/source.blend', 'pre-upper40/requested.json.gz']),
        ):
            self.packaging({key: {}})
            contract = self.contracts()[0]
            expected = [self.base + name for name in names]
            self.assertEqual([row['path'] for row in contract[0][6:]], expected)
            for path in expected:
                with self.subTest(path=path):
                    command, root = self.command(contract)
                    command['outputs'] = [row for row in command['outputs'] if row['path'] != path]
                    with self.assertRaisesRegex(ValueError, 'output roles or complete inventory'):
                        bridge.validate_phase_command(command, *contract, root)

    def test_fresh_and_final_construction_companions_must_match(self):
        (self.root / (self.base + 'source.construction.json.gz')).write_bytes(b'different')
        with self.assertRaisesRegex(ValueError, 'Fresh construction output differs'):
            self.contracts()


if __name__ == '__main__':
    unittest.main()
