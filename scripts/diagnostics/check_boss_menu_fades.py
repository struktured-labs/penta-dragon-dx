"""Issue #27: rendered endpoint checks for a two-toggle boss-menu replay.

Requires complete frame PNGs and matching mGBA PNG states. This checks black
and white concealment, not intermediate fade fidelity, timing or arena art.
The first frame of each register endpoint is transitional and reported rather
than accepted as a settled endpoint. Missing either endpoint is a failure.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from verify_pickup_class_palettes import serialized_state


def white_return_cadence(observations, start_frame=240):
    """Check the native four-frame intermediate holds after the second Select.

    Reports every run, including initial/terminal censored E4 runs. This does
    not claim identical entry phase, total transition duration, or audio.
    """
    runs = []
    for row in observations:
        if row['frame'] < start_frame:
            continue
        if runs and runs[-1]['bgp'] == row['bgp']:
            runs[-1]['last'] = row['frame']
            runs[-1]['count'] += 1
        else:
            runs.append(dict(bgp=row['bgp'], first=row['frame'],
                             last=row['frame'], count=1))
    expected = [0xE4, 0x90, 0x40, 0, 0x40, 0x90, 0xE4]
    failures = []
    if [r['bgp'] for r in runs] != expected:
        failures.append('white-return register sequence differs or is incomplete')
    else:
        for index in (1, 2, 4, 5):
            if runs[index]['count'] != 4:
                failures.append(dict(reason='intermediate hold must last four frames',
                                     run=runs[index]))
    return dict(status='FAIL' if failures else 'PASS', failures=failures,
                runs=runs, start_frame=start_frame,
                scope='white-return intermediate BGP hold cadence only')


def endpoint_failures(observations):
    previous = None
    settled = {0: [], 255: []}
    boundary = []
    failures = []
    for row in observations:
        value = row['bgp']
        if value in settled:
            if value != previous:
                boundary.append(row['frame'])
            else:
                settled[value].append(row['frame'])
                expected = [255, 255, 255] if value == 0 else [0, 0, 0]
                if row['colors'] != [expected]:
                    failures.append(dict(frame=row['frame'], bgp=value,
                                         reason='endpoint exposes nonuniform or wrong-color picture'))
        previous = value
    for value, frames in settled.items():
        if not frames:
            failures.append(dict(bgp=value, reason='missing settled endpoint'))
    return dict(status='FAIL' if failures else 'PASS', failures=failures,
                settled_frames=settled, endpoint_boundary_frames=boundary)


def return_map_generation(state, previous=None):
    """#46: distinguish the displayed complete pose from the next source build.

    Only the terminal E4 frame may retain the immediately preceding, verified
    90-frame pose. Intermediate reveals still require the live source exactly.
    This is frame-boundary transition readiness, not later publication latency.
    """
    def selected(raw):
        base = 0x2000 if raw[0x340] & 8 else 0x1C00
        return bytes(raw[base+r*32+c] for r in range(24) for c in range(24))
    source = state[0x45A0:0x47E0]
    visible = selected(state)
    mismatches = [dict(row=i//24, column=i%24, expected=expected, actual=actual)
                  for i, (expected, actual) in enumerate(zip(source, visible))
                  if expected != actual]
    generation = 'current_source' if not mismatches else None
    if (mismatches and previous is not None and state[0x347] == 0xE4
            and previous[0x347] == 0x90):
        completed = previous[0x45A0:0x47E0]
        if selected(previous) == completed and visible == completed:
            generation = 'previous_completed_source'
    return mismatches, generation


def return_map_readiness(directory, frames=600, start_frame=240):
    """Require the generated 24x24 map before and throughout return reveal.

    Checks the LCDC-selected VRAM0 tilemap against native C1A0 through the first
    E4 frame, which may retain the immediately preceding complete pose while
    the next source generation starts. Reports all live-source differences.
    Does not cover CHR, attributes, OAM, scanlines or later publication latency.
    """
    saw_white = False
    observations = []
    failures = []
    complete = False
    previous = None
    for frame in range(start_frame, frames + 1):
        path = directory / f'frame-{frame:04d}.ss0'
        state = serialized_state(path)
        if state[0x347] == 0:
            saw_white = True
            previous = state
            continue
        if not saw_white:
            continue
        base = 0x2000 if state[0x340] & 8 else 0x1C00
        mismatches, generation = return_map_generation(state, previous)
        observations.append(dict(frame=frame, bgp=state[0x347],
                                 tilemap='9C00' if base == 0x2000 else '9800',
                                 mismatches=mismatches,
                                 accepted_generation=generation,
                                 reference_frame=frame-1 if generation == 'previous_completed_source' else frame,
                                 state_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        if generation is None:
            failures.append(dict(frame=frame, mismatch_count=len(mismatches)))
        previous = state
        if state[0x347] == 0xE4:
            complete = True
            break
    if not complete:
        failures.append(dict(reason='missing complete white-to-E4 reveal'))
    return dict(status='FAIL' if failures else 'PASS', failures=failures,
                observations=observations,
                scope='complete 24x24 source generation versus selected tilemap during return reveal; not later publication latency')


SHALAMAR_PALETTE_POLICY = bytes([0, 0] + [4]*253 + [0])


def scene_observation(frame, state):
    """#47 retain raw and canonical identities; validate DX graphics separately."""
    return dict(frame=frame, scene=state[0x5C80], canonical_scene=state[0x3B7],
                cgb=bool(state[8] & 0x80),
                shalamar_palette_valid=state[0x4A00:0x4B00] == SHALAMAR_PALETTE_POLICY)


def scene_route_failures(observations, expected_scene):
    """Keep every frame. Only proven Shalamar sound alias may retain residency.

    Canonical identity alone cannot clear the recorded dungeon-palette bug.
    On CGB require the authored C600 policy throughout this arena as well.
    Sparse legacy observations cannot qualify an alias without model/owner.
    """
    if not 0x0C <= expected_scene <= 0x14:
        raise ValueError('expected scene must identify a main boss arena')
    if not observations:
        return [dict(reason='missing scene observations')]
    failures = []
    for row in observations:
        alias = (expected_scene == 0x0C and row.get('scene') == 0x0B
                 and row.get('canonical_scene') == expected_scene
                 and isinstance(row.get('cgb'), bool))
        reason = None
        if row.get('scene') != expected_scene and not alias:
            reason = 'replay left expected arena'
        elif 'canonical_scene' in row and row['canonical_scene'] != expected_scene:
            reason = 'canonical arena changed'
        elif expected_scene == 0x0C and row.get('cgb') is True and row.get('shalamar_palette_valid') is not True:
            reason = 'Shalamar graphics palette policy missing or wrong'
        if reason:
            failures.append(dict(frame=row['frame'], scene=row.get('scene'),
                                 canonical_scene=row.get('canonical_scene'),
                                 expected_scene=expected_scene, reason=reason))
    return failures


def inspect(directory, frames, expected_scene=None):
    if frames < 1:
        raise ValueError('positive frame count required')
    observations = []
    for frame in range(1, frames + 1):
        prefix = directory / f'frame-{frame:04d}'
        state_path, png = prefix.with_suffix('.ss0'), prefix.with_suffix('.png')
        state = serialized_state(state_path)
        with Image.open(png) as image:
            if image.size != (160, 144):
                raise ValueError(f'non-native frame: {png}')
            colors = sorted(set(image.convert('RGB').getdata()))
        observations.append(dict(**scene_observation(frame,state), bgp=state[0x347],
                                 colors=[list(c) for c in colors],
                                 png_sha256=hashlib.sha256(png.read_bytes()).hexdigest(),
                                 state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest()))
    result = dict(endpoint_failures(observations), frames=frames,
                scope='boss-menu black/white endpoints only; not full fade or gameplay qualification',
                observations=observations,
                extra_state_files=sorted(p.name for p in directory.glob('frame-*.ss0')
                                         if int(p.stem.split('-')[1]) > frames))
    result['expected_scene'] = expected_scene
    result['sound_alias_frames'] = [r['frame'] for r in observations
                                   if expected_scene == 0x0C and r['scene'] == 0x0B]
    result['scene_route_failures'] = (scene_route_failures(observations, expected_scene)
                                      if expected_scene is not None else None)
    if result['scene_route_failures']:
        result['status'] = 'FAIL'
        result['failures'].extend(result['scene_route_failures'])
    return result


def inspect_roundtrips(directory, expected_scene, third_entry_frame=720):
    """#36: qualify each scheduled return, never borrow another cycle's endpoints."""
    if expected_scene is None or not 0x0C <= expected_scene <= 0x14:
        raise ValueError('expected scene must identify a main boss arena')
    if not 700 <= third_entry_frame <= 800:
        raise ValueError('third entry must be within700..800')
    result = inspect(directory, 1080, expected_scene)
    result['scope'] = ('three boss-menu cycles: arena residency, rendered endpoints, '
                       'return hold cadence and selected map; not audio/full gameplay')
    result['cycles'] = []
    for first, close, last in ((1, 240, 419),
                               (420, 540, third_entry_frame-1),
                               (third_entry_frame, 840, 1080)):
        rows = [r for r in result['observations'] if first <= r['frame'] <= last]
        checks = dict(endpoints=endpoint_failures(rows),
                      cadence=white_return_cadence(rows, close),
                      map_readiness=return_map_readiness(directory, last, close))
        failed = [name for name, check in checks.items() if check['status'] != 'PASS']
        result['cycles'].append(dict(first=first, close=close, last=last,
                                     status='FAIL' if failed else 'PASS', **checks))
        if failed:
            result['status'] = 'FAIL'
            result['failures'].append(dict(cycle=len(result['cycles']), failed_checks=failed))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--frames', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-scene', type=lambda text: int(text, 0),
                        help='require every captured frame to remain in this arena, e.g.0x10')
    parser.add_argument('--roundtrips', action='store_true',
                        help='require all three scheduled cycles, not aggregate endpoints')
    parser.add_argument('--third-entry-frame', type=int, default=720)
    args = parser.parse_args()
    if args.roundtrips and (args.frames != 1080 or args.expected_scene is None):
        parser.error('--roundtrips requires --frames1080 and --expected-scene')
    result = (inspect_roundtrips(args.directory, args.expected_scene, args.third_entry_frame)
              if args.roundtrips else inspect(args.directory, args.frames, args.expected_scene))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(result['status'], result['failures'])
    raise SystemExit(result['status'] != 'PASS')
