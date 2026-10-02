"""#26 experimental secret copier routing for the native low-health sound alias.

Keep native sound state untouched. Only raw0B may consult canonical FFB7;
preserve the stage07 guard and existing raw09/0A paths. Not release-qualified.
"""
import argparse
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm
from build_secret_combined_copy_trial import gate as old_gate

PARENT = 'd901357a105036469b8debbff138fb63e87afb3a0cfbe5a24eeaafa91353910a'
START = 28 * 0x4000


def gate():
    a = Asm(0x4000)
    a.db(0xf0, 0xba, 0xfe, 7); a.jr(0x20, 'native')
    a.db(0xfa, 0x80, 0xd8, 0xfe, 11); a.jr(0x20, 'classify')
    a.db(0xf0, 0xb7)
    a.label('classify')
    a.db(0xfe, 9); a.jr(0x28, 'secret')
    a.db(0xfe, 10); a.jr(0x20, 'native')
    a.label('secret')
    a.db(0x3e, 36, 0xcd, 0x47, 0x08, 0x0e, 0, 0x3e, 1, 0xc9)
    a.label('native')
    a.db(0x11, 0xa0, 0xc1, 0x0e, 0x41, 0xc3, 0x85, 0x6c)
    return a.finish()


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact completion-safe parent required')
    previous, code = old_gate(), gate()
    expected = previous + b'\xff' * (len(code) - len(previous))
    if parent[START:START+len(code)] != expected:
        raise ValueError('secret gate preimage or extension cave differs')
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
    output = args.output.resolve()
    if output.exists() or (root / 'tmp').resolve() not in output.parents:
        parser.error('fresh repository-local tmp output required')
    rom = build(args.parent.read_bytes())
    output.mkdir(parents=True)
    (output / 'candidate.gb').write_bytes(rom)
    receipt = dict(issue=26, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
