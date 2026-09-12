"""Run the locked sedan review recipe sequentially; encode completed movies immediately.

This standard-library orchestrator never edits or saves its input Blender file.
Blender's capture manifest controls frame reuse. Failed command records remain.
"""

import argparse
import datetime
import hashlib
import json
import platform
import re
import struct
import subprocess
import sys
from fractions import Fraction
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value):
    temporary = path.with_suffix('.partial.json')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def blender_diagnostics(text):
    """Reject silent render failures and retain native shutdown allocations."""
    allocation = re.compile(r'^Error: Not freed memory blocks: (\d+), total unfreed memory ([\d.]+) MB$')
    fatal = re.compile(
        r'Traceback \(most recent call last\)|PyDriver|SyntaxError:|^Error:|^ERROR:|'
        r'ERROR[^\r\n]*\bDriver\b|'
        r'EXCEPTION_ACCESS_VIOLATION|SIGSEGV|segmentation fault|fatal error|'
        r'(?:image|texture)[^\r\n]*(?:not available|not found|missing|unable to|cannot|failed)|'
        r'(?:not available|not found|missing|unable to|cannot|failed)[^\r\n]*(?:image|texture)', re.I)
    shutdown = []
    failures = []
    for line in text.splitlines():
        match = allocation.fullmatch(line.strip())
        if match:
            shutdown.append({'blocks': int(match[1]), 'reported_megabytes': float(match[2]),
                             'diagnostic': line, 'review_status': 'pending_independent_review'})
        elif fatal.search(line):
            failures.append(line)
    if failures:
        raise RuntimeError('Blender reported a render, driver or dependency failure: ' + '\n'.join(failures[:12]))
    return shutdown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    parser.add_argument('--recipe', type=Path, default=Path(__file__).with_name('capture-recipe.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', default=[], help='Run selected named cases, in recipe order')
    args = parser.parse_args()
    renderer = Path(__file__).with_name('render.py').resolve()
    overlays = renderer.with_name('review_overlays.py')
    source, recipe_path, blender, ffmpeg = [p.resolve() for p in (args.source, args.recipe, args.blender, args.ffmpeg)]
    ffprobe = ffmpeg.with_name('ffprobe.exe' if ffmpeg.suffix.lower() == '.exe' else 'ffprobe')
    recipe = json.loads(recipe_path.read_text(encoding='utf-8'))
    cases = recipe['cases']
    names = [case['name'] for case in cases]
    if len(set(names)) != len(names) or any(not re.fullmatch('[a-z0-9][a-z0-9-]*', name) for name in names):
        parser.error('Recipe case names must be unique safe labels')
    if set(args.case) - set(names):
        parser.error('Unknown selected case')
    cases = [case for case in cases if not args.case or case['name'] in args.case]
    output = args.output.resolve()
    inputs = {str(path): digest(path) for path in (source, recipe_path, renderer, overlays, renderer.with_name('geometry.py'), renderer.with_name('__init__.py'), Path(__file__).resolve(), blender, ffmpeg, ffprobe)}
    configuration = {'inputs': inputs, 'cases': [case['name'] for case in cases]}
    state_path = output / 'suite.json'
    if output.exists() and not state_path.is_file():
        parser.error('Existing output is not a recorded capture suite')
    output.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if state['configuration'] != configuration:
            parser.error('Source, recipe, tools or selected cases changed; use a new output directory')
    else:
        state = {'task_id': 'P1-018', 'milestone': 'M5', 'status': 'running', 'started_utc': utc(),
                 'git_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                 'platform': platform.platform(), 'python': platform.python_version(),
                 'configuration': configuration, 'commands': [], 'cases': {}, 'human_approval_reference': None}
    state['status'] = 'running'
    write(state_path, state)

    def run(command, name):
        log = output / (f'{len(state["commands"])+1:04d}-' + name + '.log')
        record = {'argv': [str(item) for item in command], 'cwd': str(Path.cwd()), 'started_utc': utc(), 'log': log.name}
        with log.open('wb') as stream:
            result = subprocess.run(record['argv'], stdout=stream, stderr=subprocess.STDOUT, check=False)
        record.update(finished_utc=utc(), exit_status=result.returncode, log_sha256=digest(log))
        state['commands'].append(record)
        write(state_path, state)
        if result.returncode:
            raise RuntimeError(f'{name} exited {result.returncode}: {log}')
        text = log.read_text(encoding='utf-8', errors='replace')
        if Path(command[0]) == blender:
            record['native_shutdown_allocations'] = blender_diagnostics(text)
            record['positive_blender_log_checked'] = True
            write(state_path, state)
        return text

    try:
        state['blender_version'] = run([blender, '--version'], 'blender-version').splitlines()[0]
        state['ffmpeg_version'] = run([ffmpeg, '-version'], 'ffmpeg-version').splitlines()[0]
        for case in cases:
            if (output / 'STOP').exists():
                raise RuntimeError('Suite STOP requested between cases')
            name = case['name']
            folder = output / name
            print('SEDAN_CAPTURE_CASE ' + name, flush=True)
            run([blender, '--background', source, '--python-exit-code', '1', '--python', renderer, '--',
                 '--output', folder, *recipe['common_arguments'], *case['arguments']], name + '-render')
            capture_path = folder / 'manifest.json'
            capture = json.loads(capture_path.read_text(encoding='utf-8'))
            config, frames = capture['configuration'], capture['frames']
            if capture['status'] != 'completed' or config['source_sha256'] != inputs[str(source)]:
                raise RuntimeError(f'{name}: unfinished capture or changed source')
            if len(frames) != config['frame_count']:
                raise RuntimeError(f'{name}: incomplete frames')
            for frame in frames:
                path = folder / frame['path']
                if path.parent != folder or digest(path) != frame['sha256']:
                    raise RuntimeError(f'{name}: unsafe or changed frame')
                header = path.read_bytes()[:24]
                if header[:8] != b'\x89PNG\r\n\x1a\n' or list(struct.unpack('>II', header[16:24])) != config['size']:
                    raise RuntimeError(f'{name}: invalid image header/dimensions')
            result = {'status': 'passed', 'capture_manifest': str(capture_path),
                      'capture_manifest_sha256': digest(capture_path), 'frames': len(frames)}
            if config['sequence'] != 'none':
                if [f['path'] for f in frames] != [f'{i+1:06d}.png' for i in range(len(frames))]:
                    raise RuntimeError(f'{name}: sequence is not contiguous')
                movie_record = folder / 'encoded-movie.json'
                binding = {'source_sha256': config['source_sha256'], 'configuration_sha256': capture['configuration_sha256'],
                           'frames': [{'path': f['path'], 'sha256': f['sha256']} for f in frames]}
                binding_hash = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
                if movie_record.exists():
                    encoded = json.loads(movie_record.read_text(encoding='utf-8'))
                    movie = folder / encoded['path']
                    if encoded['status'] != 'passed' or encoded['binding_sha256'] != binding_hash or movie.parent != folder or digest(movie) != encoded['sha256']:
                        raise RuntimeError(f'{name}: stale or changed encoded movie')
                else:
                    movie = folder / (f'encoded-attempt-{len(state["commands"])+1:04d}.mp4')
                    run([ffmpeg, '-v', 'error', '-n', '-framerate', config['fps'], '-i', folder / '%06d.png',
                         '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p',
                         '-movflags', '+faststart', movie], name + '-encode')
                details = json.loads(run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                                          '-show_entries', 'stream=width,height,nb_read_frames,avg_frame_rate,duration',
                                          '-of', 'json', movie], name + '-probe'))['streams'][0]
                run([ffmpeg, '-v', 'error', '-xerror', '-i', movie, '-f', 'null', '-'], name + '-decode')
                if int(details['nb_read_frames']) != len(frames) or [details['width'], details['height']] != config['size'] or Fraction(details['avg_frame_rate']) != config['fps']:
                    raise RuntimeError(f'{name}: decoded count, size or frame rate differs')
                encoded = {'status': 'passed', 'utc': utc(), 'path': movie.name, 'sha256': digest(movie),
                           'binding_sha256': binding_hash, 'source_sha256': config['source_sha256'],
                           'decoded_stream': details, 'encoder': state['ffmpeg_version'],
                           'suite_commands': str(state_path), 'human_approval_reference': None}
                write(movie_record, encoded)
                result['encoded_movie_record_sha256'] = digest(movie_record)
            state['cases'][name] = result
            write(state_path, state)
        if any(digest(path) != expected for path, expected in inputs.items()):
            raise RuntimeError('A locked input changed during capture')
        state['native_shutdown_review_required'] = any(
            row.get('native_shutdown_allocations') for row in state['commands'])
        state['status'] = 'passed'
    except BaseException as error:
        state['status'] = 'failed'
        state['failure'] = str(error)
        raise
    finally:
        state['finished_utc'] = utc()
        write(state_path, state)


if __name__ == '__main__':
    main()
