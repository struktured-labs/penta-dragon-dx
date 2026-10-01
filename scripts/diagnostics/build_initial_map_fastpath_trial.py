"""#14/#45: keep native CE=0 gate timing; guard only synthetic copy skips."""
import argparse
import hashlib
import json
from pathlib import Path
from build_return_initial_map_trial import OFFSET, OLD, PREFIX

PARENT = '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b'
NATIVE_FADE_PARENT = '916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb'


def body():
    # Preserve original CE=0 branch/return instruction sequence byte-for-byte.
    # Nonzero CE enters the appended active check. Inactive returns bank1/Z;
    # active performs the original synthetic register advance and returns NZ.
    return OLD[:5] + bytes.fromhex('C3916C') + bytes(6) + OLD[14:] + bytes.fromhex('F0C1B728F8') + OLD[5:]


def build(parent, native_fade_control=False):
    expected = NATIVE_FADE_PARENT if native_fade_control else PARENT
    if hashlib.sha256(parent).hexdigest() != expected:
        raise ValueError('exact selected parent required')
    new = body()
    old = PREFIX + OLD
    if parent[OFFSET:OFFSET+len(new)] != old + b'\xff' * (len(new)-len(old)):
        raise ValueError('initial-map gate or cave preimage changed')
    result = bytearray(parent)
    result[OFFSET:OFFSET+len(new)] = new
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--native-fade-control', action='store_true',
                   help='diagnostic916ebb parent with original fade, not a release candidate')
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    parent = a.parent.read_bytes()
    rom = build(parent, a.native_fade_control)
    a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    receipt = dict(parent_sha256=hashlib.sha256(parent).hexdigest(), native_fade_control=a.native_fade_control,
                   candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   experimental=True, release_qualified=False, issues=[14,45])
    (a.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
