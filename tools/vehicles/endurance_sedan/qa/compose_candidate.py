"""Compose hash-bound unsaved QA replacements; never produce a shipping asset."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--replacement', type=Path, required=True)
    p.add_argument('--expected-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--record', type=Path, required=True)
    args = p.parse_args()
    assert not args.output.exists() and not args.record.exists()
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha(args.replacement) == args.expected_sha256
    base = json.loads(gzip.decompress(args.base.read_bytes()))
    replacement = json.loads(gzip.decompress(args.replacement.read_bytes()))
    assert base['source_sha256'] == replacement['source_sha256']
    names = sorted(replacement['meshes'])
    assert names and all(name in base['meshes'] for name in names)
    for name in names:
        assert base['meshes'][name]['ancestors'] == replacement['meshes'][name]['ancestors']
        assert base['meshes'][name]['rest_world_matrix'] == replacement['meshes'][name]['rest_world_matrix']
        base['meshes'][name] = replacement['meshes'][name]
    provenance = {'utc': datetime.now(timezone.utc).isoformat(), 'replacement_names': names,
                  'inputs': [{'path': str(path.resolve()), 'sha256': sha(path)} for path in (args.base, args.replacement, Path(__file__))],
                  'source_is_baseline_only': True, 'source_save_or_shipping_export': False}
    base.setdefault('qa_replacement_chain', []).append(provenance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(base, separators=(',', ':')).encode(), mtime=0))
    args.record.write_text(json.dumps({'task_id': 'P1-018', 'milestone': 'M5', **provenance,
                                      'output': str(args.output.resolve()), 'output_sha256': sha(args.output),
                                      'human_approval_reference': None}, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'replacement_names': names, 'output_sha256': sha(args.output)}))


if __name__ == '__main__':
    main()
