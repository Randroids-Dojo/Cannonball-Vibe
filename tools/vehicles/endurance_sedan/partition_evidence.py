"""Partition an explicit history inventory into bounded, independently verifiable archives."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--max-input-bytes', type=int, default=900_000_000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    source, output = args.manifest.resolve(), args.output.resolve()
    if not source.is_relative_to(root) or not output.is_relative_to(root) or output.exists():
        parser.error('Use an existing repository manifest and a new repository output directory')
    if args.max_input_bytes < 1_000_000:
        parser.error('Archive input limit must be at least1000000 bytes')
    original = source.read_bytes()
    lock = json.loads(original)
    if lock['task_id'] != 'P1-018' or not lock['entries']:
        parser.error('A nonempty explicit P1-018 inventory is required')
    names = [row['path'] for row in lock['entries']]
    if len(set(names)) != len(names):
        parser.error('Duplicate inventory paths')
    entries, aliases, omitted = {}, [], []
    for row in lock['entries']:
        name = PurePosixPath(row['path'])
        if (name.is_absolute() or '..' in name.parts or ':' in row['path']
                or '\\' in row['path'] or name.as_posix() != row['path']):
            parser.error('Noncanonical repository path: ' + row['path'])
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            parser.error('Missing or non-repository input: ' + row['path'])
        if (type(row['bytes']) is not int or row['bytes'] < 0
                or not re.fullmatch('[a-f0-9]{64}', row['sha256'])
                or path.stat().st_size != row['bytes'] or sha(path) != row['sha256']):
            parser.error('Changed inventory input: ' + row['path'])
        retention = row.get('retention', 'payload')
        if retention == 'payload':
            entries[row['path']] = row
        elif retention == 'alias':
            aliases.append(row)
        elif retention == 'omitted_intermediate_movie' and lock.get('deliberately_omitted_movie_policy'):
            omitted.append(row)
        else:
            parser.error('Undeclared retention policy: ' + row['path'])
    for row in aliases:
        target = entries.get(row['canonical_payload_path'])
        if target is None or (row['sha256'], row['bytes']) != (target['sha256'], target['bytes']):
            parser.error('Alias lacks an identical retained payload: ' + row['path'])
    for path, reason in ((source, 'Complete original inventory including explicit aliases, exclusions and omissions'),
                         (Path(__file__).resolve(), 'Exact deterministic partition recipe')):
        name = path.relative_to(root).as_posix()
        assert name not in names
        entries[name] = {'path': name, 'bytes': path.stat().st_size, 'sha256': sha(path), 'reason': reason}
    groups, current, size = [], [], 0
    for row in sorted(entries.values(), key=lambda item: item['path']):
        if row['bytes'] > args.max_input_bytes:
            parser.error('One input exceeds the archive limit: ' + row['path'])
        if current and size + row['bytes'] > args.max_input_bytes:
            groups.append(current)
            current, size = [], 0
        current.append(row)
        size += row['bytes']
    if current:
        groups.append(current)
    if source.read_bytes() != original:
        parser.error('Source inventory changed during verification')
    output.mkdir(parents=True)
    upstream = {'path': source.relative_to(root).as_posix(), 'sha256': sha(source), 'bytes': len(original)}
    index = {
        'task_id': 'P1-018', 'milestone': 'M5',
        'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'verified_partition_inputs; archive writing and byte comparison still required',
        'source_inventory': upstream, 'tool_sha256': sha(Path(__file__)),
        'max_input_bytes_per_part': args.max_input_bytes,
        'unique_retained_files': len(entries), 'verified_aliases': len(aliases),
        'deliberately_omitted_files': len(omitted), 'parts': [],
        'human_approval_reference': None,
    }
    for number, group in enumerate(groups, 1):
        part = output / f'part-{number:02d}.manifest.json'
        part_lock = {
            'task_id': 'P1-018', 'source_inventory': upstream, 'part': number, 'part_count': len(groups),
            'scope': lock['scope'],
            'excluded_external_inputs': 'See complete retained source inventory for its exact exclusions, aliases, omissions and individual report limitations.',
            'entries': group, 'human_approval_reference': None,
        }
        part.write_text(json.dumps(part_lock, indent=2) + '\n', encoding='utf-8', newline='\n')
        index['parts'].append({'path': part.relative_to(root).as_posix(), 'sha256': sha(part),
                               'files': len(group), 'input_bytes': sum(row['bytes'] for row in group)})
    (output / 'partition.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'status': index['status'], 'parts': len(groups),
                      'unique_files': len(entries), 'aliases': len(aliases), 'output': str(output)}))


if __name__ == '__main__':
    main()
