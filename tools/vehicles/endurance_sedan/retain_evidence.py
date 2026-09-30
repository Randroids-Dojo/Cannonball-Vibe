"""Package an explicit checksummed evidence inventory twice without changing inputs."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import zipfile
import zlib


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeat-output', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    paths = [path.resolve() for path in (args.manifest,args.output,args.repeat_output,args.index)]
    manifest, output, repeat, index = paths
    for path in paths:
        if not path.is_relative_to(root):
            parser.error('Evidence inputs and outputs must stay inside the repository')
    if len(set(paths)) != len(paths) or any(path.exists() for path in (output,repeat,index)):
        parser.error('Use distinct new output paths; existing evidence is preserved')
    raw_manifest = manifest.read_bytes()
    lock = json.loads(raw_manifest)
    if lock['task_id'] != 'P1-018' or not lock['entries']:
        parser.error('A nonempty explicit P1-018 inventory is required')
    entries = sorted(lock['entries'], key=lambda row: row['path'])
    names = [row['path'] for row in entries]
    if len(set(names)) != len(names):
        parser.error('Duplicate evidence paths')
    inputs = []
    for row in entries:
        name = PurePosixPath(row['path'])
        if (name.is_absolute() or '..' in name.parts or '\\' in row['path']
                or ':' in row['path'] or name.as_posix() != row['path']
                or row['path'] == 'manifest.json'):
            parser.error('Unsafe or noncanonical evidence path: ' + row['path'])
        path = (root / name).resolve()
        if not path.is_relative_to(root) or path in paths or not path.is_file():
            parser.error('Evidence input missing, outside repository, or aliases an output: ' + row['path'])
        if not re.fullmatch('[a-f0-9]{64}',row['sha256']):
            parser.error('Missing exact SHA-256: ' + row['path'])
        if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            parser.error('Evidence input differs from its lock: ' + row['path'])
        inputs.append((row,path))
    for path in (output,repeat,index):
        path.parent.mkdir(parents=True,exist_ok=True)
    report = {'task_id':'P1-018','milestone':'M5','status':'running','started_utc':utc(),
              'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
              'platform':platform.platform(),'python':platform.python_version(),
              'zlib_runtime':zlib.ZLIB_RUNTIME_VERSION,'tool_sha256':sha(Path(__file__)),
              'input_manifest':{'path':manifest.relative_to(root).as_posix(),'sha256':sha(manifest)},
              'entries':entries,'archives':[],'human_approval_reference':None,
              'limits':'Evidence retention and byte identity only; individual reports retain their own scope, failures and approval status.'}

    def info(name):
        member = zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
        member.create_system = 3
        member.external_attr = 0o100644 << 16
        member.compress_type = zipfile.ZIP_DEFLATED
        return member

    try:
        for path in (output,repeat):
            with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
                archive.writestr(info('manifest.json'),raw_manifest)
                for row,source in inputs:
                    with source.open('rb') as stream, archive.open(info(row['path']),'w') as target:
                        shutil.copyfileobj(stream,target,1024*1024)
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError('Archive CRC verification failed: ' + str(path))
                if archive.namelist() != ['manifest.json',*names]:
                    raise RuntimeError('Archive contains a missing, extra or reordered input')
                for row,_ in inputs:
                    with archive.open(row['path']) as stream:
                        if hashlib.file_digest(stream,'sha256').hexdigest() != row['sha256']:
                            raise RuntimeError('Archived evidence differs from its input lock: ' + row['path'])
            report['archives'].append({'path':path.relative_to(root).as_posix(),
                                       'sha256':sha(path),'bytes':path.stat().st_size,
                                       'crc_and_member_sha256_verified':True})
        if report['archives'][0]['sha256'] != report['archives'][1]['sha256']:
            raise RuntimeError('Repeated evidence archive bytes differ')
        if manifest.read_bytes() != raw_manifest or any(sha(path) != row['sha256'] for row,path in inputs):
            raise RuntimeError('A locked evidence input changed during retention')
        report['byte_reproducible'] = True
        report['status'] = 'passed'
    except BaseException as error:
        report['status'] = 'failed'
        report['failure'] = str(error)
        raise
    finally:
        report['finished_utc'] = utc()
        index.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':'passed','entries':len(entries),
                      'output':str(output),'sha256':report['archives'][0]['sha256']}))


if __name__ == '__main__':
    main()
