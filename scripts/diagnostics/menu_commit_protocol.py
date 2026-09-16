"""Source-authenticated r443 packed-map transaction used by race fixtures.

DFC4/DF5C was the pre-r383 request pair. Current FFC4 owns the packed
absolute/ready/page/SCY bits; DF5C owns latched SCX, not a ready flag.
"""
import hashlib
from stage_card_palette_handoff import VBLANK_GUARDED_COMMIT
from build_later_stage_deferred_dma_r443 import isr_pretest
from expansion_bank25_r456 import expected_bank25

NAME = 'ffc4-absolute-ready-page-scy-df5c-scx-r443'


def expected_parts():
    commit = VBLANK_GUARDED_COMMIT.replace(
        bytes.fromhex('AF EA 5C DF'), bytes(4), 1
    ).replace(
        bytes.fromhex('FA 00 DC E6 0F E0 43'), bytes.fromhex('FA 5C DF E6 0F E0 43'), 1
    ).replace(
        bytes.fromhex('FA 02 DC E6 0F E0 42'), bytes.fromhex('F0 C4 E6 0F E0 42'), 1
    ).replace(
        bytes.fromhex('F0 C4 B7 28 15 E6 04 07'), bytes.fromhex('F0 C4 CB 7F 28 15 E6 10 0F'), 1
    ).replace(
        bytes.fromhex('F0 40 EE 48 E0 40 C3 1D 6F'), bytes.fromhex('AF E0 C4 F0 40 EE 48 E0 40'), 1
    )
    commit = bytearray(commit)
    commit[0x7407-0x73FC:0x740F-0x73FC] = bytes.fromhex('C3 03 77 00 00 00 00 00')
    # The scene-2 reload sentinel is dealiased to DF5D (r443e/f).
    reload_test = bytes.fromhex('FA80D8 FE02 C22D74 FA5DDF 3D C22D74 AF EA5DDF C30F74')
    return [(13, 0x73FC, bytes(commit)),
            (13, 0x7464, bytes.fromhex('F044 E6FC FE90 C21D6F C3EE76 00000000')),
            (13, 0x7485, bytes.fromhex('C30074')),
            (13, 0x76EE, isr_pretest()+reload_test),
            (25, 0x4000, expected_bank25()),
            (0, 0x0847, bytes.fromhex('CD6100 CD806C C36100'))]


def authenticate(rom):
    from build_spike_death_trial import CANDIDATE_SHA, authenticated_parent
    if hashlib.sha256(rom).hexdigest() == CANDIDATE_SHA:
        # The successor owns two disjoint private bank-25 spans. Reverse and
        # authenticate that complete delta before checking the inherited map
        # transaction, rather than weakening the bank-25 byte contract.
        rom = authenticated_parent(rom)
    parts = expected_parts()
    for bank, address, code in parts:
        offset = bank*0x4000+address-(0x4000 if bank else 0)
        if rom[offset:offset+len(code)] != code:
            raise ValueError(f'unknown completed-map protocol at {bank:02X}:{address:04X}')
    commit = parts[0][2]
    store = bytes.fromhex('F040 E6B7 B0 E040')
    assert commit.count(store) == 1
    # CPU boundary immediately after the real absolute selector store.
    post_pc = 0x73FC+commit.index(store)+len(store)
    return dict(name=NAME, post_pc=post_pc,
                source_sha256=hashlib.sha256(b''.join(p[2] for p in parts)).hexdigest())
