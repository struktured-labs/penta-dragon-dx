#!/usr/bin/env python3
"""#54: restore the native bank-1 stage-record table and its native loader.

Stage init ``00:0C29 -> 01:7B91`` copies the 29-byte record at
``01:7BB3 + 29*FFBA`` to HRAM ``$FF9B-$FFB7``. Two DX helpers had been placed
in "asserted-zero caves" that are really record bytes 19..27 (HRAM
``$FFAE-$FFB6``) of records 7 and 8:

* ``01:7C91`` Ted bank-16 trampoline tail ``3E 10 21 00 40 E5 C3 61 00``
  (entered only by ``JP $7C91`` at ``01:6FEC``);
* ``01:7CAE`` death final-publication return ``C5 D5 CD 5C 43 D1 C1 AF C9``
  (entered only by ``JP $7CAE`` at fixed ``00:0035``).

The interim #63 stage (``clean-stage-headers``) left both helpers in place and
rewrote the native loader to fetch records 7/8 from a bank-63 mirror through a
far stub written over record-7 bytes 0..17. That made HRAM correct, but the
bank-1 table stayed corrupt and records 7/8 took 4104 loader cycles in the
live probe instead of the cartridge's 3304.

This final stage removes the collision instead of routing around it:

1. Both nine-byte helpers move, byte-for-byte, into fixed bank 0 at
   ``$00D0``/``$00D9``. ``$00CF-$00FF`` is the unreferenced stock fill between
   the last executable byte of ``$00C8``'s routine (``RET`` at ``$00CE``) and
   the cartridge entry point ``$0100``; no stock or DX control transfer or
   pointer names it (``tests/test_native_stage_records.py`` checks this; an
   attract-run read/execute watch on the parent finds no access). Neither
   helper depends on its own bank, and
   both are entered with bank 1 mapped exactly as before.
2. The two ``JP nn`` operands are retargeted. ``JP nn`` costs 16 T-cycles for
   every target, so both paths are cycle-identical to the parent.
3. ``01:7B91-01:7CB7`` (native loader, index helper and all nine records) is
   restored to the exact cartridge bytes, which reinstates native loader
   timing for every record (records 0..6 were already padded to it).
4. The retired bank-63 mirror, index, loader and wrapper bytes go back to the
   erased ``$FF`` state; nothing else references them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_clean_stage_headers as interim  # noqa: E402

PARENT = '126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941'
ORIGINAL = '2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30'

NATIVE_START, NATIVE_END = 0x7B91, 0x7CB8      # loader, index helper, 9 records
TABLE, RECORD, RECORDS = 0x7BB3, 29, 9
TED_TAIL_OLD, DEATH_RETURN_OLD = 0x7C91, 0x7CAE
TED_TAIL = bytes.fromhex('3E10210040E5C36100')      # LD A,10; LD HL,4000; PUSH HL; JP 0061
DEATH_RETURN = bytes.fromhex('C5D5CD5C43D1C1AFC9')  # PUSH BC/DE; CALL 435C; POP; XOR A; RET
TED_JUMP, DEATH_JUMP = 0x6FEC, 0x0035               # bank1 / fixed JP nn sites
FILL_START, FILL_END = 0x00CF, 0x0100               # unreferenced stock fill
TED_TAIL_NEW, DEATH_RETURN_NEW = 0x00D0, 0x00D9


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jp(address: int) -> bytes:
    return bytes((0xC3, address & 0xFF, address >> 8))


def interim_bank63(original: bytes) -> list[tuple[int, bytes]]:
    """Exact bank-63 bytes written by the retired #63 stage (file offsets)."""
    table = original[TABLE:NATIVE_END]
    index = original[0x7BA1:0x7BB3].replace(bytes.fromhex('11B37B'), bytes.fromhex('110048'))
    loader = interim.LOADER.replace(bytes.fromhex('CDA17B'), bytes.fromhex('CDA049'))
    wrapper = bytes.fromhex('F1CD0042F511B3331911B8FF3E01C3817C')
    return [(interim.offset(interim.CLEAN_TABLE), table),
            (interim.offset(interim.CLEAN_INDEX), index),
            (interim.offset(0x4200), loader),
            (interim.offset(0x4000), wrapper),
            (interim.offset(0x7C81), bytes.fromhex('CD6100C30040'))]


def expected_parent_native_region(original: bytes) -> bytes:
    region = bytearray(original[NATIVE_START:NATIVE_END])
    def put(address, payload):
        region[address - NATIVE_START:address - NATIVE_START + len(payload)] = payload
    put(0x7B91, interim.COMMON)
    put(0x7C7E, interim.FAR_STUB)
    put(0x7C88, interim.PHASE_PAD)
    put(TED_TAIL_OLD, TED_TAIL)
    put(DEATH_RETURN_OLD, DEATH_RETURN)
    return bytes(region)


def build(parent: bytes, original: bytes) -> bytes:
    if sha(parent) != PARENT:
        raise ValueError('exact title-glyph-retry parent required')
    if sha(original) != ORIGINAL:
        raise ValueError('exact original cartridge required')
    if parent[NATIVE_START:NATIVE_END] != expected_parent_native_region(original):
        raise ValueError('bank-1 stage-record region preimage differs')
    if parent[TED_JUMP:TED_JUMP + 3] != jp(TED_TAIL_OLD):
        raise ValueError('Ted trampoline jump preimage differs')
    if parent[DEATH_JUMP:DEATH_JUMP + 3] != jp(DEATH_RETURN_OLD):
        raise ValueError('death publication jump preimage differs')
    if parent[FILL_START:FILL_END] != original[FILL_START:FILL_END]:
        raise ValueError('bank-0 stock fill is no longer stock')
    result = bytearray(parent)
    for start, payload in interim_bank63(original):
        if parent[start:start + len(payload)] != payload:
            raise ValueError(f'retired bank-63 bytes differ at {start:05X}')
        result[start:start + len(payload)] = b'\xff' * len(payload)
    result[TED_TAIL_NEW:TED_TAIL_NEW + len(TED_TAIL)] = TED_TAIL
    result[DEATH_RETURN_NEW:DEATH_RETURN_NEW + len(DEATH_RETURN)] = DEATH_RETURN
    result[TED_JUMP:TED_JUMP + 3] = jp(TED_TAIL_NEW)
    result[DEATH_JUMP:DEATH_JUMP + 3] = jp(DEATH_RETURN_NEW)
    result[NATIVE_START:NATIVE_END] = original[NATIVE_START:NATIVE_END]
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF).to_bytes(2, 'big')
    return bytes(result)


def changed_spans(original: bytes) -> list[tuple[int, int]]:
    """Every file span this stage may change, excluding the global checksum."""
    spans = [(DEATH_JUMP + 1, DEATH_JUMP + 3),
             (TED_TAIL_NEW, DEATH_RETURN_NEW + len(DEATH_RETURN)),
             (TED_JUMP + 1, TED_JUMP + 3),
             (NATIVE_START, NATIVE_END)]
    spans.extend((start, start + len(payload)) for start, payload in interim_bank63(original))
    return sorted(spans)


def reconstruct_parent(rom: bytes, original: bytes) -> bytes:
    """Invert this stage exactly; callers must never execute the result."""
    parent = bytearray(rom)
    for start, payload in interim_bank63(original):
        if rom[start:start + len(payload)] != b'\xff' * len(payload):
            raise ValueError('retired bank-63 span is not erased')
        parent[start:start + len(payload)] = payload
    parent[NATIVE_START:NATIVE_END] = expected_parent_native_region(original)
    parent[TED_TAIL_NEW:DEATH_RETURN_NEW + len(DEATH_RETURN)] = \
        original[TED_TAIL_NEW:DEATH_RETURN_NEW + len(DEATH_RETURN)]
    parent[TED_JUMP:TED_JUMP + 3] = jp(TED_TAIL_OLD)
    parent[DEATH_JUMP:DEATH_JUMP + 3] = jp(DEATH_RETURN_OLD)
    parent[0x14E:0x150] = ((sum(parent[:0x14E]) + sum(parent[0x150:])) & 0xFFFF).to_bytes(2, 'big')
    parent = bytes(parent)
    if sha(parent) != PARENT or build(parent, original) != rom:
        raise ValueError('native stage-record reconstruction failed')
    return parent


def verify_installed(rom: bytes, original: bytes) -> list[str]:
    """Static contract for any image carrying this stage."""
    failures = []
    if rom[NATIVE_START:NATIVE_END] != original[NATIVE_START:NATIVE_END]:
        for record in range(RECORDS):
            a = TABLE + record * RECORD
            if rom[a:a + RECORD] != original[a:a + RECORD]:
                failures.append(f'bank1 stage record {record} differs from cartridge')
        if rom[NATIVE_START:TABLE] != original[NATIVE_START:TABLE]:
            failures.append('bank1 native stage loader differs from cartridge')
    if rom[TED_TAIL_NEW:TED_TAIL_NEW + 9] != TED_TAIL or rom[TED_JUMP:TED_JUMP + 3] != jp(TED_TAIL_NEW):
        failures.append('relocated Ted trampoline tail missing')
    if rom[DEATH_RETURN_NEW:DEATH_RETURN_NEW + 9] != DEATH_RETURN or rom[DEATH_JUMP:DEATH_JUMP + 3] != jp(DEATH_RETURN_NEW):
        failures.append('relocated death publication return missing')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--original', type=Path, default=ROOT / 'rom/Penta Dragon (J).gb')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or (ROOT / 'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    original = args.original.read_bytes()
    result = build(args.parent.read_bytes(), original)
    args.output.mkdir(parents=True)
    (args.output / 'candidate.gb').write_bytes(result)
    receipt = dict(issue=54, parent_sha256=PARENT, original_sha256=ORIGINAL,
                   candidate_sha256=sha(result),
                   builder_sha256=sha(Path(__file__).read_bytes()),
                   static_failures=verify_installed(result, original))
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
