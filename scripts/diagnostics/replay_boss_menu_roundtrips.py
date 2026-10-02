"""Capture three local boss-menu round trips through the single-flight runner.

Requires an exact-ROM PNG savestate, not a retargeted cross-ROM state. The
1080-frame capture is a bounded gameplay sample, not an audio/hardware gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import zlib

from generate_stream_boss_states import run_until_marker
from runtime_tools import emulator_runtime_snapshot
from verify_pickup_class_palettes import serialized_state

ROOT = Path(__file__).resolve().parents[2]


def binding(path):
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def native_capture_failures(native, requested_frames=1080):
    """#43 complete files do not imply a valid restored capture boundary."""
    failures = []
    if native.get('restored_replay_epoch', {}).get('status') != 'PASS':
        failures.append('native capture includes an invalid restore epoch')
    if native.get('metadata', {}).get('frames') != requested_frames:
        failures.append('native capture frame count differs from requested1080')
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('state', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-tap', type=Path)
    parser.add_argument('--av-output', type=Path)
    parser.add_argument('--trace-apu', action='store_true',
                        help='read-only FF10–FF3F write trace during frames240–320')
    parser.add_argument('--trace-map', action='store_true',
                        help='read-only second-return map/source publication trace')
    parser.add_argument('--trace-input', action='store_true',
                        help='read-only joypad latch trace during frames700–860')
    parser.add_argument('--trace-latch', action='store_true',
                        help='observe physical bank7 DF81/DF82 writes throughout replay')
    parser.add_argument('--third-entry-frame', type=int, default=720,
                        help='phase probe: move only third entry, retaining six-frame hold')
    parser.add_argument('--third-entry-hold', type=int, default=6,
                        help='additional short-pulse probe, third entry only (1..6 frames)')
    args = parser.parse_args()
    if not 700 <= args.third_entry_frame <= 800:
        parser.error('third entry must be within observed active-combat window700–800')
    if not 1 <= args.third_entry_hold <= 6:
        parser.error('third entry hold must be 1..6 frames')
    output = args.output.resolve()
    if output.exists() or (ROOT / 'tmp').resolve() not in output.parents:
        parser.error('fresh repository-local tmp output required')
    if bool(args.native_tap) != bool(args.av_output):
        parser.error('--native-tap and --av-output must be supplied together')
    if args.av_output:
        args.av_output = args.av_output.resolve()
        if args.av_output.exists() or not any(base in args.av_output.parents for base in
                (Path('/mnt/data/tmp'), (ROOT / 'tmp').resolve())):
            parser.error('fresh large-scratch or repo-local AV output required')
    state = serialized_state(args.state)
    expected_scene = state[0x5C80]
    if not 0x0C <= expected_scene <= 0x14:
        parser.error('input state must be in a main boss arena')
    if int.from_bytes(state[4:8], 'little') != zlib.crc32(args.rom.read_bytes()):
        parser.error('savestate ROM CRC does not match; generate a fresh exact-ROM entry')
    probe = Path(__file__).with_name('probe_boss_menu_roundtrips.lua')
    receipt = dict(rom=binding(args.rom), state=binding(args.state),
                   probe=binding(probe), runner=binding(Path(__file__)),
                   runtime=emulator_runtime_snapshot(), requested_frames=1080,
                   select_presses=[120, 240, 420, 540, args.third_entry_frame, 840], held_frames=6,
                   third_entry_hold=args.third_entry_hold,
                   audio_captured=False, completed=False, trace_apu=args.trace_apu,
                   trace_map=args.trace_map, trace_input=args.trace_input,
                   trace_latch=args.trace_latch)
    if args.native_tap:
        receipt['native_tap'] = binding(args.native_tap)
        receipt['av_output'] = str(args.av_output)
        # Qt overrideMute(false) treats any nonnegative fastForwardMute as
        # muted during fast-forward, even0. Use its inherit sentinel -1 and
        # explicitly pin unmuted levels instead of inheriting GUI preferences.
        receipt['audio_options'] = ['mute=0', 'volume=256', 'fastForwardMute=-1',
                                    'fastForwardVolume=256', 'muteOnFocusLost=0',
                                    'muteOnMinimize=0']
    output.mkdir()
    (output / 'launch.json').write_text(json.dumps(receipt, indent=2) + '\n')
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', SDL_AUDIODRIVER='dummy',
               BOSS_MENU_OUT=str(output), BOSS_MENU_STATE=str(args.state.resolve()),
               BOSS_MENU_THIRD_ENTRY=str(args.third_entry_frame),
               BOSS_MENU_THIRD_HOLD=str(args.third_entry_hold))
    if args.trace_apu:
        env['BOSS_MENU_APU_TRACE'] = '1'
    if args.trace_map:
        env['BOSS_MENU_MAP_TRACE'] = '1'
    if args.trace_input:
        env['BOSS_MENU_INPUT_TRACE'] = '1'
    if args.trace_latch:
        env['BOSS_MENU_LATCH_TRACE'] = '1'
    if args.native_tap:
        args.av_output.mkdir()
        env.update(LD_PRELOAD=str(args.native_tap.resolve()),
                   PENTA_NATIVE_AV_PREFIX=str(args.av_output / 'native'),
                   ENTRY_NATIVE_START_GATE=str(output / 'initialized'),
                   BOSS_MENU_PRELOADED='1')
    started = time.monotonic()
    audio_options = [item for option in receipt.get('audio_options', [])
                     for item in ('-C', option)]
    run_until_marker([str(ROOT / 'scripts/mgba-qt-singleflight'), '--fastforward',
                      *audio_options,
                      *(['-t', str(args.state.resolve())] if args.native_tap else []),
                      '-C', f'savegamePath={output}', '-C', f'savestatePath={output}',
                      str(args.rom.resolve()), '--script', str(probe)],
                     env, output, output / 'done', 45)
    receipt.update(completed=True, replay_wall_seconds=time.monotonic()-started)
    if args.native_tap:
        from finalize_native_av_capture import finalize
        receipt['native_capture'] = finalize(args.av_output)
        receipt['audio_captured'] = True
    with (output / 'completion.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
    print((output / 'done').read_text())
    from check_boss_menu_fades import inspect_roundtrips
    started = time.monotonic()
    result = inspect_roundtrips(output, expected_scene, args.third_entry_frame)
    if args.native_tap:
        native = receipt['native_capture']
        capture_failures = native_capture_failures(native)
        result['native_capture_failures'] = capture_failures
        if capture_failures:
            result['status'] = 'FAIL'
            result['failures'].extend(capture_failures)
    result['checker'] = binding(Path(__file__).with_name('check_boss_menu_fades.py'))
    result['verification_wall_seconds'] = time.monotonic()-started
    with (output / 'verification.json').open('x') as stream:
        json.dump(result, stream, indent=2)
    print('Three-cycle verification:', result['status'])
    raise SystemExit(result['status'] != 'PASS')


if __name__ == '__main__':
    main()
