"""#54: experimental native stage-header loader using a clean bank-63 copy.

Do not erase the live Ted/death helpers which overlap native bank-1 data.
Keep unaffected records0..6 in bank1 with native measured call timing (#62).
Only records7/8 use the clean expansion-bank copy. The fixed bank-switch
helper maintains FF99/DC09. Preserve the native final registers in both paths.
This is an experimental build, not emulator or hardware qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'ffc29f4e29f2c2f9995f132c08676624ad92a206b822b3afdf835be3ad072feb'
ROOT = Path(__file__).resolve().parents[2]
BANK = 63
LOADER = bytes.fromhex('CDA17B119BFF061D7E1223130520F9C9')
COMMON = bytes.fromhex(
    'FE07D27E7C 5F87836F7BCB37879521B37BD7B7 '
    '119BFF061D 2A12130520FA CD887C C9'
)
FAR_STUB = bytes.fromhex('F53E3FCD6100F1C90000')
PHASE_PAD = bytes.fromhex('C5060E0520FDC1C9')
CLEAN_TABLE = 0x4800
CLEAN_INDEX = 0x49A0


def sha(data):
    return hashlib.sha256(data).hexdigest()


def offset(address):
    return BANK * 0x4000 + address - 0x4000


def build(parent, original):
    if sha(parent) != PARENT:
        raise ValueError('exact played parent required')
    if parent[BANK*0x4000:] != bytes([255])*0x4000:
        raise ValueError('bank 63 must be entirely unused expansion space')
    if parent[0x7B91:0x7BA1] != LOADER or original[0x7B91:0x7BA1] != LOADER:
        raise ValueError('native loader changed')
    if parent[0x7BA1:0x7BB3] != original[0x7BA1:0x7BB3]:
        raise ValueError('native stage-index helper changed')
    if parent[0x61:0x67] != bytes.fromhex('EA09DCC3BE09') or parent[0x9BE:0x9C4] != bytes.fromhex('E099EA0021C9'):
        raise ValueError('fixed bank-switch ABI changed')
    # All stage records except the two live injected helpers must match stock.
    for i in range(0x7BB3, 0x7CB8):
        if not (0x7C91 <= i < 0x7C9A or 0x7CAE <= i < 0x7CB7):
            if parent[i] != original[i]:
                raise ValueError(f'unexpected stage-header difference at {i:04x}')
    result = bytearray(parent)
    # Index0..6: 8-bit29*n is exact; RST10 adds it to the native table.
    # OR A restores the native carry=0 before the byte-copy loop. The counted
    # padding preserves native elapsed cycles, rather than retiming demo input.
    assert len(COMMON) == 34
    result[0x7B91:0x7BB3] = COMMON
    # These are abandoned portions of records7/8, outside both live helpers.
    result[0x7C7E:0x7C88] = FAR_STUB
    result[0x7C88:0x7C90] = PHASE_PAD
    table = original[0x7BB3:0x7CB8]
    result[offset(CLEAN_TABLE):offset(CLEAN_TABLE)+len(table)] = table
    index = original[0x7BA1:0x7BB3].replace(
        bytes.fromhex('11B37B'), bytes.fromhex('110048'))
    result[offset(CLEAN_INDEX):offset(CLEAN_INDEX)+len(index)] = index
    result[offset(0x4200):offset(0x4210)] = LOADER.replace(
        bytes.fromhex('CDA17B'), bytes.fromhex('CDA049'))
    # Rebase returned HL to the original table address and restore DE/AF.
    # Switch-back CALL at63:7C81 returns to1:7C84 (POP AF; RET).
    wrapper = bytes.fromhex('F1CD0042F511B3331911B8FF3E01C3817C')
    result[offset(0x4000):offset(0x4000)+len(wrapper)] = wrapper
    result[offset(0x7C81):offset(0x7C87)] = bytes.fromhex('CD6100C30040')
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or (ROOT/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('use a fresh directory under this worktree tmp/')
    parent, original = args.parent.read_bytes(), args.original.read_bytes()
    result = build(parent, original)
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt = dict(issue=54, experimental=True, qualified=False,
                   parent_sha256=sha(parent), original_sha256=sha(original),
                   candidate_sha256=sha(result), builder_sha256=sha(Path(__file__).read_bytes()),
                   mechanism='native-timed bank1 records0..6; clean bank63 records7/8',
                   retained_live_helpers=['bank1:7C91','bank1:7CAE'])
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
