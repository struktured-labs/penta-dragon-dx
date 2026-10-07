"""#27 diagnostic: rearm at the existing bank-1 background-entry call.

The earlier $1A43 hook called bank1 before native initialization selected it.
Keep that native prelude intact. At $1A4F, replace CALL $759B with a wrapper
which preserves AF, rearms FF91, then tail-jumps to the original routine.
This trial is not release qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = 'f2ff141007fa59acf1afd76f397682c499e3eb108fa02e9a0e3c4e2b5b84f7d4'
EARLY = 0x1A43
HOOK = 0x1A4F
HELPER = 0x7C9A
OLD_EARLY = bytes.fromhex('CD9A7C000000')
NATIVE_EARLY = bytes.fromhex('3E01E0DAE0E4')
OLD_HELPER = bytes.fromhex('3E01E091E0DAE0E4C9')
PAYLOAD = bytes.fromhex('F53E01E091F1C39B75')


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact early-rearm parent required')
    if (parent[EARLY:EARLY+6] != OLD_EARLY
            or parent[HOOK:HOOK+3] != bytes.fromhex('CD9B75')
            or parent[HELPER:HELPER+9] != OLD_HELPER
            or parent[0x1A49:HOOK] != bytes.fromhex('CDFD16CD4E17')):
        raise ValueError('boss prelude preimage changed')
    result = bytearray(parent)
    result[EARLY:EARLY+6] = NATIVE_EARLY
    result[HOOK:HOOK+3] = bytes.fromhex('CD9A7C')
    result[HELPER:HELPER+9] = PAYLOAD
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh worktree tmp output required')
    rom = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=27, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   added_entry_tcycles=64, scope=__doc__)
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
