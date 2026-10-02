"""Combine measured tile DMA and bulk attribute compilation, retaining ordering."""
import hashlib
import build_tail_coordinate_wait_r433 as guard
import build_stage1_bulk_context_r426 as bulk

ROOT = guard.ROOT
BASE = ROOT / 'tmp/tail-coordinate-wait-r433/candidate.gb'
SHA = '5aee56bf413f96c4b9d86e4091a6098c43b5f2c47f943f50df57369fcef73ba3'
OUT = ROOT / 'tmp/combined-dma-compile-r434'


def build(source, *, reference=None):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r433')
    # Reuse the independently tested r426 compiler only where its exact
    # original preimages still match. No change to mapper/stack ABI or guard.
    # Accept the in-memory r424 checkpoint when replaying the full lineage.
    original = bulk.BASE.read_bytes() if reference is None else reference
    compiled = bulk.build(original)
    code = bulk.service()
    ranges = [(0x7ACBC, 0x7ACBF),
              (bulk.prior.OFFSET, bulk.prior.OFFSET + len(code))]
    allowed = {0x14D, 0x14E, 0x14F}
    for start, end in ranges:
        allowed.update(range(start, end))
        assert source[start:end] == original[start:end]
    assert all(i in allowed for i, (a, b) in enumerate(zip(original, compiled)) if a != b)
    result = bytearray(source)
    for start, end in ranges:
        result[start:end] = compiled[start:end]
    guard.update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise ValueError('immutable candidate collision')
    target.write_bytes(rom)
    print(hashlib.sha256(rom).hexdigest())
