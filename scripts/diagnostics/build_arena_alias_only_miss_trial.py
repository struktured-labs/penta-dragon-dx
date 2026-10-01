"""#27 experiment: use the mapper resolver only for raw scene $0B misses."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'd901357a105036469b8debbff138fb63e87afb3a0cfbe5a24eeaafa91353910a'


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact completion-safe parent required')
    result = bytearray(parent)
    detector = parent[0x36f90:0x37000]
    if detector[:15] != bytes.fromhex('FA80D8 210DDF BE C8 3E14 CDBE09 F1 C8'):
        raise ValueError('detector prefix changed')
    if detector[-4:] != bytes(4):
        raise ValueError('detector padding unavailable')
    # A is still the raw scene after the failed cache comparison. Only $0B
    # needs FFB7 disambiguation; non-alias misses retain A/HL for CALL7CFC.
    # Its entry preserves AF but does not consume incoming flags.
    result[0x36f90:0x37000] = detector[:8] + bytes.fromhex('FE0B 2007') + detector[8:-4]
    # Move the bank20 mapper return rendezvous by the same four bytes.
    shim = 20 * 0x4000 + 0x6f9a - 0x4000
    if parent[shim:shim+10] != bytes.fromhex('CDBE09 C3E06D') + b'\xff'*4:
        raise ValueError('mapper rendezvous preimage changed')
    result[shim:shim+10] = b'\xff'*4 + bytes.fromhex('CDBE09 C3E06D')
    ret = 20 * 0x4000 + 0x6dfc - 0x4000
    if parent[ret:ret+3] != bytes.fromhex('C39A6F'):
        raise ValueError('resolver return changed')
    result[ret:ret+3] = bytes.fromhex('C39E6F')
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository tmp output required')
    rom = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=27, experimental=True, release_qualified=False,
        parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='normal cache misses skip alias mapper; hot cache-hit prefix unchanged',
        qualification='not tested; no promotion')
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
