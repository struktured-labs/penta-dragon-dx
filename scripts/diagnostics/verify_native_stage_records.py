#!/usr/bin/env python3
"""#54 release gate: native bank-1 stage records 7/8 and their HRAM image.

Stage init ``00:0C29 -> 01:7B91`` copies record ``FFBA`` (29 bytes at
``01:7BB3 + 29*FFBA``) to ``$FF9B-$FFB7``. Offsets 19..27 become
``$FFAE-$FFB6``: the tile-animation/scroll parameters read by the VBlank
routine ``00:086C`` and by ``01:4198``. On the cartridge they are zero for
records 7 and 8, so that animation stays off in those stages.

Checks, all against the original cartridge:

1. static: the bank-1 loader, index helper and every record (01:7B91-01:7CB7)
   are the exact cartridge bytes; the relocated helpers are installed;
2. live (real emulator, native cold start, stage index injected only at the
   native ``CALL $7B91``): for records 0..8 the loaded ``$FF9B-$FFB7`` image,
   in particular ``$FFAE-$FFB6``, the returned AF/BC/DE/HL/SP, ROM bank, DC09
   and the elapsed loader cycles equal the original cartridge;
3. negative control: the candidate with the two former helpers written back
   into records 7/8 (the played rc11/ffc29f4e layout) must fail check 2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_native_stage_records as records  # noqa: E402
from runtime_tools import emulator_runtime_snapshot, reject_known_broken_cgb_runtime  # noqa: E402

STOCK_SHA = records.ORIGINAL
HOST = Path('/home/struktured/projects/penta-dragon-dx').resolve()
GUARD = HOST / 'scripts/mgba-qt-singleflight'
BOOT = HOST / 'scripts/diagnostics/probe_stage_integrity.lua'
PROBE = Path(__file__).with_name('probe_clean_stage_headers.lua')
TARGETS = tuple(range(records.RECORDS))
ANIM = slice(19 * 2, 28 * 2)   # header hex digits for $FFAE-$FFB6
REGISTERS = ('af_after', 'bc_after', 'de_after', 'hl_after', 'sp_after', 'bank', 'dc09_after')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def corrupt_control(rom: bytes) -> bytes:
    """Replay the played defect: helper bytes as record 7/8 data."""
    result = bytearray(rom)
    result[records.TED_TAIL_OLD:records.TED_TAIL_OLD + 9] = records.TED_TAIL
    result[records.DEATH_RETURN_OLD:records.DEATH_RETURN_OLD + 9] = records.DEATH_RETURN
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF).to_bytes(2, 'big')
    return bytes(result)


def static_failures(rom: bytes, original: bytes) -> list[str]:
    failures = []
    for record in range(records.RECORDS):
        start = records.TABLE + record * records.RECORD
        if rom[start:start + records.RECORD] != original[start:start + records.RECORD]:
            diff = [f'{start + i:04X}' for i in range(records.RECORD)
                    if rom[start + i] != original[start + i]]
            failures.append(f'static: bank1 record {record} differs at {",".join(diff)}')
    if rom[records.NATIVE_START:records.TABLE] != original[records.NATIVE_START:records.TABLE]:
        failures.append('static: bank1 native loader/index helper differs from cartridge')
    return failures


def run_probe(rom_path: Path, target: int, directory: Path) -> dict:
    directory.mkdir()
    rom = directory / 'candidate.gb'
    shutil.copyfile(rom_path, rom)
    result = directory / 'result.txt'
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', SDL_AUDIODRIVER='dummy',
               HEADER_TARGET=str(target), HEADER_OUT=str(result),
               HEADER_BOOT_PROBE=str(BOOT), STAGE_OUT=str(directory / 'boot'), STAGE_TARGET='0')
    stopped = False
    with (directory / 'emulator.log').open('w') as log:
        run = subprocess.Popen([str(GUARD), '--fastforward', '--script', str(PROBE), str(rom)],
                               cwd=HOST, env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        try:
            while run.poll() is None:
                if Path(str(result) + '.done').exists():
                    stopped = True
                    run.terminate()
                    break
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired(run.args, 30)
                time.sleep(0.01)
        finally:
            if run.poll() is None:
                run.terminate()
            try:
                run.wait(timeout=3)
            except subprocess.TimeoutExpired:
                run.kill()
                run.wait()
    if not stopped or not result.exists():
        raise RuntimeError(f'{directory.name}: probe did not complete (exit {run.returncode})')
    values = dict(line.split('=', 1) for line in result.read_text().splitlines())
    values['result_sha256'] = sha(result.read_bytes())
    return values


def live_failures(values: dict, control: dict, target: int, original: bytes) -> list[str]:
    failures = []
    expected = original[records.TABLE + target * records.RECORD:
                        records.TABLE + (target + 1) * records.RECORD].hex()
    if values['header'][ANIM] != expected[ANIM]:
        failures.append(f'stage{target}: FFAE-FFB6 {values["header"][ANIM]} != original {expected[ANIM]}')
    if values['header'] != expected:
        failures.append(f'stage{target}: FF9B-FFB7 differs from original record')
    for key in REGISTERS:
        if values[key] != control[key]:
            failures.append(f'stage{target}: {key} differs from original')
    if values['cycles'] != control['cycles']:
        failures.append(f'stage{target}: loader cycles {values["cycles"]} != original {control["cycles"]}')
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--original', type=Path, default=ROOT / 'rom/Penta Dragon (J).gb')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--no-negative-control', action='store_true',
                        help='diagnostic only: skip the deliberately corrupt control')
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / 'tmp').resolve() not in out.parents:
        parser.error('fresh repository-local tmp output required')
    original = args.original.read_bytes()
    if sha(original) != STOCK_SHA:
        parser.error('original cartridge identity differs')
    candidate = args.rom.resolve().read_bytes()
    out.mkdir(parents=True)
    os.environ['LD_LIBRARY_PATH'] = str(HOST / 'tmp/mgba-cgb-latches-r454/build')
    runtime = emulator_runtime_snapshot()
    reject_known_broken_cgb_runtime(runtime)
    roles = {'original': args.original.resolve(), 'candidate': args.rom.resolve()}
    if not args.no_negative_control:
        control_path = out / 'deliberately-corrupt-records.gb'
        control_path.write_bytes(corrupt_control(candidate))
        roles['negative_control'] = control_path
    inputs = {name: dict(path=str(path), sha256=sha(path.read_bytes()))
              for name, path in [*roles.items(), ('probe', PROBE), ('boot_probe', BOOT),
                                 ('guard', GUARD), ('verifier', Path(__file__).resolve()),
                                 ('layout', Path(records.__file__).resolve())]}
    report = dict(schema='penta-native-stage-records-v1', issue=54,
                  scope='static bank-1 record table + native loader contract (HRAM FF9B-FFB7, registers, cycles)',
                  inputs=inputs, runtime=runtime,
                  static_failures=static_failures(candidate, original),
                  installed_layout_failures=records.verify_installed(candidate, original),
                  runs=[], failures=[])
    report['failures'].extend(report['static_failures'])
    report['failures'].extend(report['installed_layout_failures'])
    observed = {}
    for role, path in roles.items():
        for target in TARGETS:
            values = run_probe(path, target, out / f'{role}-{target}')
            observed[role, target] = values
            report['runs'].append(dict(role=role, target=target, values=values))
    for target in TARGETS:
        control = observed['original', target]
        expected = original[records.TABLE + target * records.RECORD:
                            records.TABLE + (target + 1) * records.RECORD].hex()
        if control['header'] != expected:
            report['failures'].append(f'original stage{target}: probe did not observe the cartridge record')
        report['failures'].extend(live_failures(observed['candidate', target], control, target, original))
    if 'negative_control' in roles:
        rejected = {target: live_failures(observed['negative_control', target],
                                          observed['original', target], target, original)
                    for target in TARGETS}
        report['negative_control_rejections'] = {str(k): v for k, v in rejected.items() if v}
        if not (rejected[7] and rejected[8]):
            report['failures'].append('deliberately corrupt records 7/8 were not rejected')
        if any(rejected[t] for t in range(7)):
            report['failures'].append('negative control changed records 0..6 unexpectedly')
    for name, path in [*roles.items(), ('probe', PROBE), ('boot_probe', BOOT), ('guard', GUARD)]:
        if sha(path.read_bytes()) != inputs[name]['sha256']:
            report['failures'].append(f'{name} changed during run')
    if emulator_runtime_snapshot() != runtime:
        report['failures'].append('runtime changed during run')
    report['passed'] = not report['failures']
    (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], failures=report['failures'],
                          negative_control=report.get('negative_control_rejections', {}).keys().__repr__())))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
