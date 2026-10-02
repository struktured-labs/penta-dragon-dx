"""#45 experimental private secret-return orchestration; not release qualified.

Restore native shared fade hooks. Transition1498/149B enters bank20; only a
stage00 destination uses cloned loader/card/fade code. Native callees get a fixed callback;
existing compact CGB fade bodies remain byte-identical and return via bank1.
"""
import argparse
import hashlib
import json
from pathlib import Path

from compose_ending_bgp_handoff_r518 import Asm
import return_bank_call as calls

PARENT = 'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b'
BASE = 0x6314
LIMIT = 0x67ED


def payload(direct_sound_request=False, local_card_waits=False, native_card_chain=False):
    if local_card_waits and native_card_chain:
        raise ValueError('local waits and native chain are distinct experiments')
    a = Asm(BASE)
    thunks = {}

    def native(address, bank=1):
        name = f'native_{bank:02x}_{address:04x}'
        thunks[name] = (address, bank)
        a.absolute(0xCD, name)

    def raw(hexbytes): a.db(*bytes.fromhex(hexbytes))

    # 1498 originally enters169C with bank13; that routine restores bank1.
    native(0x169C, 13)
    # Keep the experiment scoped to the original stage00 ownership predicate.
    # Other destinations resume the native shared loader with bank1 selected.
    raw('F0BA B7')
    a.jr(0x28, 'stage_zero')
    raw('216C14 E5 C39A09')
    a.label('stage_zero')
    raw('F0EB 3C E601 E0EB')
    a.absolute(0xCD, 'loader')
    native(0x14BC)
    a.absolute(0xCD, 'fade')
    raw('AF E0E4 3E01 C39A09')

    a.label('loader')
    raw('3E40 E0BC 3E48 E0BB')
    native(0x174E)
    a.absolute(0xCD, 'card')
    raw('2185DC 0628')
    native(0x09A2)
    native(0x4F7E)
    raw('F0BA')
    native(0x0C29)
    native(0x0C96)
    native(0x1EC0)
    raw('F5 3E13')
    if direct_sound_request:
        # RST38 is fixed-bank code: it does not need the native-bank thunk.
        # Keep the original request -> AF restore -> scene-store sequence.
        raw('FF')
    else:
        native(0x0038)
    raw('F1 F0B7 EA80D8 C9')

    a.label('card')
    for address in (0x492B, 0x0A16, 0x109E, 0x7653): native(address)
    raw('AF E043 E042 F040 CB9F E040')
    native(0x4B52)
    raw('F5 3E18 EA80D8 F1')
    if native_card_chain:
        # 0F47 preserves BC. Preload all100 waits, then execute both original
        # routines in bank1 with no intervening mapper callback. This changes
        # stack depth and removes the intervening LD B,64 timing: not parity.
        raw('0664')
        a.absolute(0xCD, 'card_native_chain')
    elif local_card_waits:
        a.absolute(0xCD, 'card_native_fade')
        raw('0664')
        a.absolute(0xCD, 'card_native_waits')
    else:
        native(0x0F47)
        raw('0664')
        native(0x4068)
    # Skip the historical dispatcher's POP HL/POP AF, retaining the actual
    # deadline/backup/card body. Its JP099A returns through our fixed callback.
    native(0x5C22, 20)
    raw('C9')

    a.label('fade')
    raw('F0C1 E0DE AF E0C1')
    native(0x16DD)
    raw('F0CA CB77')
    a.jr(0x20, 'alternate')
    native(0x0A0E)
    # This private entry reuses the card's backup, exactly as the former
    # caller147C branch did, without examining synthetic return addresses.
    native(0x560D, 20)
    a.jr(0x18, 'settle')
    a.label('alternate')
    native(0x0F51)
    a.label('settle')
    raw('3E07')
    a.label('wait')
    raw('F5')
    native(0x16DD)
    raw('F1 3D')
    a.jr(0x20, 'wait')
    raw('F0DE E0C1 C9')

    if local_card_waits:
        # Same instructions/counts as native0F47/0F5A,406F and4068/407E;
        # only absolute calls relocate. RST08 still uses the fixed service.
        a.label('card_native_fade')
        raw('E5 C5 0604 AF 21D40F 1800')
        a.label('card_native_shade')
        a.absolute(0xCD, 'card_native_tick_wait')
        raw('2A CF00 05')
        a.jr(0x20, 'card_native_shade')
        raw('C1 E1 C9')
        a.label('card_native_tick_wait')
        raw('F5 AF E0D4 F0D4 FE04 20FA AF E0D4 F1 C9')
        a.label('card_native_waits')
        a.absolute(0xCD, 'card_native_mode_wait')
        raw('05')
        a.jr(0x20, 'card_native_waits')
        raw('C9')
        a.label('card_native_mode_wait')
        raw('F041 E603 FE03 20F8 F041 E603 3D 20F9 C9')

    if native_card_chain:
        a.label('card_native_chain')
        a.db(*calls.native_chain((0x0F47, 0x4068)))
    for name, (address, bank) in thunks.items():
        a.label(name)
        a.db(*calls.native_call(address, bank))
    result = a.finish()
    if BASE + len(result) > LIMIT: raise ValueError('private cave exhausted')
    return result, a.labels


def build(parent, direct_sound_request=False, local_card_waits=False, native_card_chain=False):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact fastpath parent required')
    calls.check_fixed_abi(parent)
    body, labels = payload(direct_sound_request, local_card_waits, native_card_chain)
    if local_card_waits or native_card_chain:
        for address, expected in ((0x0F47, 'E5C50604AF21D40F1809'),
                                  (0x0F5A, 'CD6F402ACF000520F7C1E1C9'),
                                  (0x4068, 'CD7E400520FAC9'),
                                  (0x406F, 'F5AFE0D4F0D4FE0420FAAFE0D4F1C9'),
                                  (0x407E, 'F041E603FE0320F8F041E6033D20F9C9')):
            old = bytes.fromhex(expected)
            if parent[address:address+len(old)] != old:
                raise ValueError(f'native wait ABI changed at {address:04x}')
    patches = {
        calls.CALLBACK: (bytes(6), calls.callback()),
        0x1498: (bytes.fromhex('CD9C16 C36C14'),
                 bytes.fromhex('CDC100 C3') + BASE.to_bytes(2, 'little')),
        0x15DA: (bytes.fromhex('CD8942'), bytes.fromhex('CD7A0F')),
        0x75F0: (bytes.fromhex('C38942'), bytes.fromhex('C3330F')),
        20*16384 + BASE-0x4000: (b'\xff'*len(body), body),
    }
    # Entry ABIs for the reused compact bodies, without copying stale addresses.
    for address, expected in ((0x560B, 'E1F1E5D5C5AFE049C32456'),
                              (0x5C20, 'E1F1E5D5C5AFE0D4CD0A57')):
        offset = 20*16384 + address-0x4000
        if parent[offset:offset+len(bytes.fromhex(expected))] != bytes.fromhex(expected):
            raise ValueError('private fade ABI changed')
    result = bytearray(parent)
    for offset, (old, new) in patches.items():
        if parent[offset:offset+len(old)] != old: raise ValueError(f'preimage {offset:x}')
        result[offset:offset+len(new)] = new
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2,'big')
    return bytes(result), labels


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--direct-sound-request', action='store_true')
    p.add_argument('--local-card-waits', action='store_true')
    p.add_argument('--native-card-chain', action='store_true')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom, labels = build(args.parent.read_bytes(), args.direct_sound_request, args.local_card_waits, args.native_card_chain)
    args.output.mkdir()
    (args.output/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=45, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   call_primitives_sha256=hashlib.sha256(Path(calls.__file__).read_bytes()).hexdigest(),
                   direct_sound_request=args.direct_sound_request,
                   local_card_waits=args.local_card_waits, native_card_chain=args.native_card_chain, labels=labels)
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
