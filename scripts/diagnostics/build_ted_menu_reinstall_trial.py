"""#36: experimental Ted runtime guard for native menu workspace reuse."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT = '8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c'
OLD = bytes.fromhex('FAFFC5 FEC9 CAF5C4 C34059')
NEW = bytes.fromhex('3E14 CDBE09 CAF5C4 C34059')


# Re-pin (docs/audit/release-lock-20261001-repin.md): the release-lock chain
# defers #14 and #34. Parent 5f481bb0... yields byte-identical
# changes (same offsets, preimages and values) as on the original 8ff1c98d...
REPINNED_PARENT = '5f481bb0ae9230cb0cd8ff7284d98d9e0c69ed054f8f8c7402d63dba7e19c1b4'


def offset(bank, address):
    return bank*0x4000 + address-0x4000


def build(parent):
    if hashlib.sha256(parent).hexdigest() not in (PARENT, REPINNED_PARENT):
        raise ValueError('exact title-local parent required')
    gate = offset(16, 0x5CDA)
    if parent[gate:gate+11] != OLD:
        raise ValueError('Ted lazy gate differs')
    # Mapper-only entry preserves BC/DE/HL and flags, without changing DC09.
    if parent[0x9BE:0x9C4] != bytes.fromhex('E099 EA0021 C9'):
        raise ValueError('mapper contract differs')
    result = bytearray(parent)
    result[gate:gate+11] = NEW
    # Entry CALL returns at bank20:5CDF -> helper. Return JP5CDC maps bank16
    # and returns at bank16:5CDF, where the original conditional dispatch lives.
    bridge = bytes.fromhex('CDBE09 C3406C')
    # Keep the original C5FF=C9 requirement. C508 is the JR NZ opcode in the
    # installed executable, overwritten with FE by the native menu metatile
    # writer. A menu hit therefore invokes the complete existing installer,
    # not an in-place opcode repair or a skip of the menu's tile writes.
    guard = bytes.fromhex('FAFFC5 FEC9 2005 FA08C5 FE20 3E10 C3DC5C')
    for address, payload in ((0x5CDC, bridge), (0x6C40, guard)):
        pos = offset(20, address)
        if parent[pos:pos+len(payload)] != b'\xff'*len(payload):
            raise ValueError('occupied private guard cave')
        result[pos:pos+len(payload)] = payload
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp directory required')
    result = build(a.parent.read_bytes())
    a.output.mkdir(parents=True)
    (a.output/'candidate.gb').write_bytes(result)
    receipt = dict(issue=36, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
