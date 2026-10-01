"""#26 diagnostic: shorten later-dungeon scene-table initialization."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7'
BANK = 13 * 0x4000
CALL = BANK + 0x1489
CAVE = BANK + 0x2D4E
# Same A/B/HL/flags and 256 writes as6D43; four stores per iteration.
CODE = bytes.fromhex('2100c6af0640222222220520f9c9')


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('Exact fast-alias parent required')
    if parent[CALL:CALL+3] != bytes.fromhex('cd436d'):
        raise ValueError('Later-dungeon setup call differs')
    if parent[CAVE:CAVE+len(CODE)] != bytes(len(CODE)):
        raise ValueError('Scene-clear cave occupied')
    result = bytearray(parent)
    result[CALL:CALL+3] = bytes.fromhex('cd4e6d')
    result[CAVE:CAVE+len(CODE)] = CODE
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    if out.exists() or (root/'tmp').resolve() not in out.parents:
        parser.error('Fresh repository-local tmp output required')
    rom = build(args.parent.read_bytes())
    out.mkdir(parents=True)
    (out/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=26,experimental=True,release_qualified=False,
                   parent_sha256=PARENT,candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
