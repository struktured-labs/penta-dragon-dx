"""#26 route low-health aliases only after the unchanged healthy secret paths."""
import argparse
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm
from build_secret_sound_alias_trial import PARENT, START
from build_secret_combined_copy_trial import gate as old_gate


def gate():
    a = Asm(0x4000)
    a.db(0xf0, 0xba, 0xfe, 7); a.jr(0x20, 'native')
    a.db(0xfa, 0x80, 0xd8, 0xfe, 9); a.jr(0x28, 'secret')
    a.db(0xfe, 10); a.jr(0x20, 'alias')
    a.label('secret')
    a.db(0x3e, 36, 0xcd, 0x47, 0x08, 0x0e, 0, 0x3e, 1, 0xc9)
    a.label('native')
    a.db(0x11, 0xa0, 0xc1, 0x0e, 0x41, 0xc3, 0x85, 0x6c)
    a.label('alias')
    a.db(0xfe, 11); a.jr(0x20, 'native')
    a.db(0xf0, 0xb7, 0xfe, 9); a.jr(0x28, 'secret')
    a.db(0xfe, 10); a.jr(0x20, 'native'); a.jr(0x28, 'secret')
    return a.finish()


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact completion-safe parent required')
    previous, code = old_gate(), gate()
    if parent[START:START+len(code)] != previous + b'\xff'*(len(code)-len(previous)):
        raise ValueError('gate or extension cave differs')
    result = bytearray(parent)
    result[START:START+len(code)] = code
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    if out.exists() or (root/'tmp').resolve() not in out.parents:
        parser.error('fresh repository-local tmp output required')
    rom = build(args.parent.read_bytes())
    out.mkdir(parents=True)
    (out/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=26, experimental=True, release_qualified=False,
        parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
