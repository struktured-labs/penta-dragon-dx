"""#19/#39: exact retest ROM, owned edits, and offline Apply/Undo only.

An optional hash-checked fixture avoids rebuilding during local test iteration.
Without it, build from original cartridge/source. No fixture is hardware proof.
"""
import os
from pathlib import Path
import shlex
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch as mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import mister_palette_bridge as bridge

PIN = '6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228'


def state_for(rom, stage=1):
    state = bytearray(181040)
    struct.pack_into('<I', state, 4, 0xB0CA)
    state[520+0x1880] = stage+1
    state[49832+0x37] = stage+1
    state[49832+0x3A] = stage-1
    state[49832+0x41] = 1
    positions = list(range(96,152,8)) + list(range(160,224,8))
    owners = list(range(15)) if stage == 1 else [4]+list(range(1,15))
    for pos, owner in zip(positions, owners):
        offset = bridge.OFFSETS[owner]
        state[pos:pos+8] = rom[offset:offset+8]
    return bytes(state)


class CurrentPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        cls.addClassCleanup(cls.scratch.cleanup)
        fixture = os.environ.get('PENTA_TEST_STREAM_ROM')
        if fixture:
            cls.rom = Path(fixture).read_bytes()
        else:
            from build_stream_source_candidate import build
            output = Path(cls.scratch.name) / 'source'
            build(output)
            cls.rom = (output / 'candidate.gb').read_bytes()
        if bridge.sha(cls.rom) != PIN:
            raise ValueError('test requires exact qualified playtest candidate')
        cls.path = Path(cls.scratch.name) / 'candidate.gb'
        cls.path.write_bytes(cls.rom)

    def test_exact_initial_identity_and_unknown_variant(self):
        with mock.object(bridge, 'WORK', Path(self.scratch.name)), mock.object(
                bridge.subprocess, 'run', side_effect=AssertionError('device access')):
            session = bridge.Bridge(self.path)
            self.assertEqual(session.source_pin, PIN)
            mutated = bytearray(self.rom); mutated[0x200] ^= 1
            bad = Path(self.scratch.name) / 'unknown.gb'; bad.write_bytes(mutated)
            with self.assertRaisesRegex(ValueError, 'exact supported pin'):
                bridge.Bridge(bad)

    def test_all_rows_change_only_owned_palette_and_checksum_bytes(self):
        state = state_for(self.rom)
        for index, offset in enumerate(bridge.OFFSETS):
            with self.subTest(index=index):
                colors = bridge.decode(self.rom[offset:offset+8]); colors[1] = '#123456'
                rom, resumed, matches = bridge.patch(self.rom, state, index, colors)
                pos = 96+index*8 if index < 7 else 160+(index-7)*8
                self.assertEqual(matches, [pos])
                self.assertEqual(rom[:0x14E], self.rom[:0x14E])
                self.assertTrue(all(a == b or i in (*range(offset,offset+8),334,335)
                                    for i,(a,b) in enumerate(zip(self.rom,rom))))
                self.assertTrue(all(a == b or pos <= i < pos+8
                                    for i,(a,b) in enumerate(zip(state,resumed))))
                self.assertTrue(bridge.stage1_layout_supported(rom))
                self.assertEqual(int.from_bytes(rom[334:336],'big'),
                                 (sum(rom[:334])+sum(rom[336:])) & 65535)

    def test_alias_edits_preserve_peer_and_private_rows_in_both_stages(self):
        for stage,index,expected in ((1,0,[96]), (2,4,[96,128])):
            state = bytearray(state_for(self.rom,stage))
            state[152:160] = self.rom[bridge.OFFSETS[index]:bridge.OFFSETS[index]+8]
            peer = self.rom[bridge.OFFSETS[1]:bridge.OFFSETS[1]+8]
            first,state1,matches = bridge.patch(self.rom,bytes(state),index,bridge.decode(peer))
            self.assertEqual(matches,expected)
            second,state2,matches = bridge.patch(first,state1,index,['#123456']*4)
            self.assertEqual(matches,expected)
            self.assertEqual(state2[104:112],bytes(state)[104:112])
            self.assertEqual(state2[152:160],bytes(state)[152:160])
            self.assertEqual(second[bridge.OFFSETS[1]:bridge.OFFSETS[1]+8],peer)
            for offset in (520+0x1880,520+0x1F4C,49832+0x37,49832+0x3A,
                           49832+0x41,49832+0x3F,49832+0x50,49832+0x64,
                           49832+0x40,96):
                with self.subTest(stage=stage,invalid_context=offset):
                    broken = bytearray(state1); broken[offset] ^= 1
                    with self.assertRaisesRegex(ValueError,'Ambiguous'):
                        bridge.patch(first,bytes(broken),index,['#123456']*4)

    def test_nonpalette_mutation_rejects_layout_and_labels(self):
        for offset in (0x147,0x200,0x1A2F,0x37DA8):
            rom = bytearray(self.rom);rom[offset] ^= 1
            self.assertFalse(bridge.stage1_layout_supported(rom))
            self.assertEqual(bridge.labels_for_rom(rom),bridge.LABELS)

    def test_labels_follow_new_projectile_roles_after_palette_edit(self):
        self.assertIn('Sara',bridge.labels_for_rom(self.rom)[7][0])
        self.assertIn('Enemy bullets',bridge.labels_for_rom(self.rom)[10][0])
        row = bridge.OFFSETS[7];colors = bridge.decode(self.rom[row:row+8]);colors[1]='#123456'
        rom,_,_ = bridge.patch(self.rom,state_for(self.rom),7,colors)
        self.assertEqual(bridge.labels_for_rom(rom),bridge.labels_for_rom(self.rom))

    def test_apply_and_undo_without_any_device_subprocess(self):
        for stage,index in ((1,0),(2,4)):
            with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as work, mock.object(
                    bridge,'WORK',Path(work)), mock.object(bridge.subprocess,'run',
                    side_effect=AssertionError('real device access')):
                session = bridge.Bridge(self.path)
                state = state_for(self.rom,stage)
                edited,resumed,_ = bridge.patch(self.rom,state,index,['#123456']*4)
                remote,loads = {},[]
                def upload(source,target):
                    remote[str(target).split(':',1)[1]] = Path(source).read_bytes()
                def ssh(command):
                    words=shlex.split(command);self.assertEqual(words[0],'sha256sum')
                    return bridge.sha(remote[words[1]]).encode()
                with mock.object(session,'checkpoint',side_effect=[state,resumed]), \
                     mock.object(session,'copy',side_effect=upload), \
                     mock.object(session,'ssh',side_effect=ssh), \
                     mock.object(session,'load',side_effect=loads.append):
                    self.assertIn('readback passed',session.apply(index,['#123456']*4))
                    self.assertEqual(session.rom,edited)
                    session.undo()
                    self.assertEqual(session.rom,self.rom)
                    self.assertFalse(session.history)
                    self.assertEqual(len(loads),2)


if __name__ == '__main__':
    unittest.main()
