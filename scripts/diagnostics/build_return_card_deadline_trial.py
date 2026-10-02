"""Issue #45 experiment: acquire CRAM window inside a four-tick interval."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'f938ae85785b4bc30133dad1c39e5f45ee0bcbea249d94f160132970ce22be29'


# Re-pin (docs/audit/release-lock-20261001-repin.md): the release-lock chain
# defers #14 and #34. Parent 2992a8a2... yields byte-identical
# changes (same offsets, preimages and values) as on the original f938ae85...
REPINNED_PARENT = '2992a8a2dbef89d5070afd97c498c1db0ab1d8f6cc46f65cd0ecd4f6937415ed'


def payload():
    # Preserve the original private entry stack and include backup in interval1.
    code = bytearray.fromhex('E1 F1 E5 D5 C5 AF E0 D4 CD 0A 57')
    for shade, target in ((0xe4, 0x5ac0), (0x90, 0x5998), (0x40, 0x5878), (0, 0x5760)):
        code.extend(bytes.fromhex('F0 D4 FE 02 38 FA'))
        code.extend(bytes((0xcd, target & 255, target >> 8)))
        # Keep native BGP/departure deadline separate from safe CRAM upload.
        code.extend(bytes.fromhex('F0 D4 FE 04 38 FA'))
        code.extend(bytes((0x3e, shade, 0xe0, 0x47)))
        code.extend(bytes.fromhex('AF E0 D4'))
    code.extend(bytes.fromhex('C1 D1 E1 C3 9A 09'))
    return bytes(code)


def build(parent):
    if hashlib.sha256(parent).hexdigest() not in (PARENT, REPINNED_PARENT):
        raise ValueError('exact trial10 parent required')
    site, cave = 0x516ae, 0x51c20
    code = payload()
    if parent[site:site+5] != bytes.fromhex('E1 F1 E5 D5 C5'):
        raise ValueError('private entry mismatch')
    if parent[cave:cave+len(code)] != b'\xff' * len(code):
        raise ValueError('occupied cave')
    result = bytearray(parent)
    result[site:site+3] = bytes.fromhex('C3 20 5C')
    result[cave:cave+len(code)] = code
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom = build(a.parent.read_bytes())
    a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=45, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
