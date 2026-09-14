"""Bind a continuous boundary certificate to initial closed-solid separation.

The opening and wiper tools prove surface separation throughout their declared
domains. This independent step rules out a solid starting wholly inside another
solid, in both directions, using the exact same geometry bytes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiper_initial import components, parity


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_pair(meshes, names, cache):
    an, bn = names
    for name in names:
        if name not in cache:
            cache[name] = components(meshes[name])
    a, b = cache[an], cache[bn]
    gap = float(np.linalg.norm(np.maximum(0, np.maximum(a['low'] - b['high'], b['low'] - a['high']))))
    row = {'pair': list(names), 'rest_aabb_gap_m': gap, 'checks': []}
    if a['nonmanifold_edges'] or b['nonmanifold_edges']:
        row.update(status='unresolved_nonclosed_mesh',
                   nonmanifold_edges=[a['nonmanifold_edges'], b['nonmanifold_edges']])
        return row
    if gap > 0:
        row['status'] = 'outside_by_disjoint_rest_aabbs'
        return row
    for origin, target, origin_name, target_name in ((a, b, an, bn), (b, a, bn, an)):
        for index in origin['representatives']:
            point = origin['vertices'][index]
            check = ({'status': 'outside_target_aabb'}
                     if np.any(point < target['low']) or np.any(point > target['high'])
                     else parity(point, target))
            row['checks'].append({'source_mesh': origin_name, 'target_mesh': target_name,
                                  'representative_vertex': index, 'point_source_m': point.tolist(), **check})
    row['status'] = ('outside_by_components_and_parity'
                     if all(r['status'] in ('outside', 'outside_target_aabb') for r in row['checks'])
                     else 'failed_or_unresolved_containment')
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--certificate', type=Path, required=True)
    parser.add_argument('--kind', choices=('openings', 'wipers'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Choose a fresh output file')
    start = time.perf_counter()
    geometry = json.loads(gzip.decompress(args.geometry.read_bytes()))
    certificate = json.loads(args.certificate.read_text(encoding='utf8'))
    geometry_hash = sha(args.geometry)
    assert certificate['status'] == 'passed', 'A failed surface certificate cannot prove solid separation'
    assert certificate['source_sha256'] == geometry['source_sha256'], 'Source identity mismatch'
    assert any(row['sha256'] == geometry_hash for row in certificate['inputs']), 'Surface certificate used different geometry bytes'
    if args.kind == 'openings':
        near = certificate['remaining_pairs']
        broad = certificate['entire_domain_aabb_certificates']
        assert len(broad) == certificate['entire_domain_aabb_certified_pairs']
        assert all(row['status'] == 'continuous-bound-certified' and row['witness'] is None
                   and row['unresolved'] is None for row in near)
    else:
        near = certificate['near_pair_reports']
        broad = certificate['whole_domain_aabb_certificates']
    pairs = [tuple(sorted(row['pair'])) for row in near + broad]
    assert pairs and len(pairs) == len(set(pairs)), 'Empty or duplicate surface-certificate inventory'
    meshes = geometry['meshes']
    assert all(name in meshes for pair in pairs for name in pair), 'Certificate names absent geometry'
    cache = {}
    rows = [check_pair(meshes, row['pair'], cache) for row in near]
    failures = [row for row in rows if row['status'].startswith(('failed', 'unresolved'))]
    dependencies = [args.geometry, args.certificate, Path(__file__), Path(__file__).with_name('wiper_initial.py'),
                    Path(__file__).with_name('wiper_interassembly.py')]
    result = {
        'task_id': 'P1-018', 'milestone': 'M5', 'utc': datetime.now(timezone.utc).isoformat(),
        'source_sha256': geometry['source_sha256'], 'geometry_sha256': geometry_hash,
        'kind': args.kind, 'status': 'failed' if failures else 'passed',
        'inputs': [{'path': str(path.resolve()), 'sha256': sha(path)} for path in dependencies],
        'surface_certificate_pair_inventory': len(pairs), 'near_pairs_checked': len(rows),
        'whole_domain_aabb_pairs_already_exclude_containment': len(broad),
        'three_ray_representatives_checked': sum('rays' in check for row in rows for check in row['checks']),
        'rows': rows, 'failures': failures, 'elapsed_seconds': time.perf_counter() - start,
        'method': 'The hash-bound continuous certificate excludes boundary crossing. At rest, disjoint AABBs exclude containment; otherwise every connected closed component has a representative vertex checked outside the other object by its AABB or three unambiguous agreeing odd-even ray parities. Both directions are checked.',
        'limits': 'Only the exact pair inventory and motion domains in the supplied passing surface certificate. Same-rigid construction interfaces, other controls, runtime and human acceptance remain separate.',
        'human_approval_reference': None,
    }
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({key: result[key] for key in ('status', 'near_pairs_checked', 'three_ray_representatives_checked', 'elapsed_seconds')}), flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
