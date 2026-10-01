import importlib.util
from pathlib import Path
import struct
import json
import shlex
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).resolve().parents[1] / 'scripts/mister_palette_bridge.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PaletteTests(unittest.TestCase):
    def test_apply_and_undo_transaction_with_simulated_device(self):
        root = Path(__file__).resolve().parents[1]/'tmp'
        root.mkdir(exist_ok=True)
        for failure in (None, 'upload', 'launcher', 'readback', 'load', 'undo'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(dir=root) as work:
                rom,state = self.fixture()
                colors = ['#000000','#ffffff','#00ff00','#0000ff']
                expected_rom,expected_state,_ = m.patch(rom,state,9,colors)
                bridge = object.__new__(m.Bridge)
                bridge.rom,bridge.stem,bridge.history = rom,'original',[]
                remote,loads,checkpoints = {},[],[]

                def checkpoint(directory):
                    checkpoints.append(directory)
                    return state if len(checkpoints)==1 or failure=='readback' else expected_state

                def copy(source,target):
                    self.assertTrue(str(target).startswith('rivalmage:'))
                    remote[str(target).split(':',1)[1]] = Path(source).read_bytes()
                    if failure == 'launcher' and str(target).endswith('.mgl'):
                        remote[str(target).split(':',1)[1]] = b'truncated launcher'

                def ssh(command):
                    parts = shlex.split(command)
                    self.assertEqual(parts[0],'sha256sum')
                    digest = '0'*64 if failure=='upload' else m.sha(remote[parts[1]])
                    return (digest+'  '+parts[1]+'\n').encode()

                def load(stem):
                    loads.append(stem)
                    if failure=='load' and len(loads)==1:
                        raise RuntimeError('simulated load failure')
                    if failure=='undo' and stem=='original':
                        raise RuntimeError('simulated undo failure')

                with patch.object(m,'WORK',Path(work)), \
                     patch.object(bridge,'checkpoint',side_effect=checkpoint), \
                     patch.object(bridge,'copy',side_effect=copy), \
                     patch.object(bridge,'ssh',side_effect=ssh), \
                     patch.object(bridge,'load',side_effect=load), \
                     patch.object(m.subprocess,'run',side_effect=AssertionError('real device access')):
                    if failure in ('upload','launcher','readback','load'):
                        with self.assertRaises((ValueError,RuntimeError)):
                            bridge.apply(9,colors)
                    else:
                        self.assertIn('readback passed',bridge.apply(9,colors))
                    if failure in ('upload','launcher'):
                        self.assertEqual(loads,[])
                        self.assertEqual((bridge.rom,bridge.stem,bridge.history),(rom,'original',[]))
                        continue
                    self.assertEqual(bridge.rom,expected_rom)
                    self.assertEqual(bridge.history,[('original',rom)])
                    self.assertEqual(len(remote),3)
                    self.assertEqual(remote['/media/fat/games/GBC/'+bridge.stem+'.gbc'],expected_rom)
                    self.assertEqual(remote[bridge.state_path()],expected_state)
                    receipt = json.loads(next(Path(work).glob('edit-*/receipt.json')).read_text())
                    self.assertEqual(receipt['state_palette_offsets'],[176])
                    self.assertEqual('readback passed' in receipt['status'],failure not in ('readback','load'))
                    if failure=='undo':
                        before = bridge.stem
                        with self.assertRaisesRegex(RuntimeError,'undo failure'):
                            bridge.undo()
                        self.assertEqual((bridge.stem,bridge.rom,bridge.history),(before,expected_rom,[('original',rom)]))
                    else:
                        bridge.undo()
                        self.assertEqual(loads[-1],'original')
                        self.assertEqual((bridge.rom,bridge.stem,bridge.history),(rom,'original',[]))

    def test_supported_sources_get_distinct_stems_without_hardware_calls(self):
        for pin in (m.PIN, m.ROW_GUARD_PIN, m.SARA_ATOMIC_PIN, m.TED_MENU_PIN, m.STAR_PIN, m.RETURN_FADE_PIN):
            with patch.object(Path, 'read_bytes', return_value=b'fixture'), \
                 patch.object(m, 'sha', return_value=pin), \
                 patch.object(m.Bridge, 'ssh', side_effect=AssertionError('hardware access')):
                bridge = m.Bridge(Path('explicit-source.gbc'))
                self.assertEqual(bridge.source_pin, pin)
                self.assertEqual(bridge.stem, 'Penta-Dragon-DX-' + pin[:12])

    def test_unknown_source_is_rejected(self):
        with patch.object(Path, 'read_bytes', return_value=b'unknown'):
            with self.assertRaisesRegex(ValueError, 'exact supported pin'):
                m.Bridge(Path('unknown.gbc'))

    def test_labels_cover_stable_palette_ids(self):
        self.assertEqual(len(m.LABELS), len(m.NAMES))
        self.assertEqual(len(m.LABELS), len(m.OFFSETS))
        self.assertIn('Rotating spike', m.LABELS[5][0])
        self.assertIn('not protruding teeth', m.LABELS[5][1])

    def fixture(self):
        rom = bytearray(524288)
        state = bytearray(181040)
        struct.pack_into('<I', state, 4, 0xB0CA)
        row = m.encode(['#000000', '#ff0000', '#00ff00', '#0000ff'])
        rom[m.OFFSETS[9]:m.OFFSETS[9]+8] = row
        state[176:184] = row
        return bytes(rom), bytes(state)

    def test_only_palette_and_checksum_change(self):
        rom, state = self.fixture()
        new, ss, matches = m.patch(rom, state, 9, ['#000000', '#ffffff', '#00ff00', '#0000ff'])
        self.assertEqual(matches, [176])
        self.assertTrue(all(a == b or i in range(176, 184) for i, (a,b) in enumerate(zip(state, ss))))
        self.assertTrue(all(a == b or i in range(m.OFFSETS[9], m.OFFSETS[9]+8) or i in (334,335) for i,(a,b) in enumerate(zip(rom,new))))
        self.assertEqual(int.from_bytes(new[334:336], 'big'), (sum(new[:334])+sum(new[336:])) & 65535)

    def test_inactive_override_rejected(self):
        rom, state = self.fixture()
        rom=bytearray(rom)
        rom[m.OFFSETS[0]:m.OFFSETS[0]+8]=m.encode(['#000000','#ff0000','#00ff00','#0000ff'])
        state = state[:96] + bytes([255])*64 + state[160:]
        with self.assertRaisesRegex(ValueError, 'not active'):
            m.patch(bytes(rom), state, 0, ['#ffffff']*4)

    def test_obj_primary_alias_is_rejected(self):
        rom,state=self.fixture()
        rom=bytearray(rom)
        rom[m.OFFSETS[10]:m.OFFSETS[10]+8]=rom[m.OFFSETS[9]:m.OFFSETS[9]+8]
        with self.assertRaisesRegex(ValueError,'Ambiguous active palette'):
            m.patch(bytes(rom),state,9,['#000000','#ffffff','#00ff00','#0000ff'])

    def test_invalid_apply_never_creates_checkpoint_or_contacts_device(self):
        rom, _ = self.fixture()
        alias = bytearray(rom)
        alias[m.OFFSETS[10]:m.OFFSETS[10]+8] = alias[m.OFFSETS[9]:m.OFFSETS[9]+8]
        cases = (
            (bytes(alias),9,['#000000','#ffffff','#00ff00','#0000ff'],'Ambiguous'),
            (rom,9,m.decode(rom[m.OFFSETS[9]:m.OFFSETS[9]+8]),'No color change'),
            (rom,9,['#ffffff']*4,'transparent'),
            (rom,True,['#ffffff']*4,'Unknown primary'),
            (rom,9,['invalid']*4,'#RRGGBB'),
            (b'bad',9,['#ffffff']*4,'ROM size'),
        )
        for source,index,colors,error in cases:
            with self.subTest(error=error):
                bridge = object.__new__(m.Bridge)
                bridge.rom, bridge.stem, bridge.history = source,'unchanged',[]
                with patch.object(Path,'mkdir',side_effect=AssertionError('filesystem mutation')), \
                     patch.object(m.Bridge,'checkpoint',side_effect=AssertionError('checkpoint')), \
                     patch.object(m.Bridge,'ssh',side_effect=AssertionError('hardware access')), \
                     patch.object(m.Bridge,'copy',side_effect=AssertionError('upload')), \
                     patch.object(m.Bridge,'load',side_effect=AssertionError('reload')):
                    with self.assertRaisesRegex(ValueError,error):
                        bridge.apply(index,colors)
                self.assertEqual((bridge.rom,bridge.stem,bridge.history),(source,'unchanged',[]))

    def test_sequential_equal_rows_reject_unrelated_palette_edit(self):
        rom,state=self.fixture()
        rom=bytearray(rom);state=bytearray(state)
        for i in range(7):
            row=struct.pack('<4H',i+1,100+i,200+i,300+i)
            rom[m.OFFSETS[i]:m.OFFSETS[i]+8]=row
            state[96+i*8:104+i*8]=row
        bg1=bytes(rom[m.OFFSETS[1]:m.OFFSETS[1]+8])
        first,resumed,matches=m.patch(bytes(rom),bytes(state),0,m.decode(bg1))
        self.assertEqual(matches,[96])
        colors=m.decode(bg1);colors[1]='#abcdef'
        with self.assertRaisesRegex(ValueError,'Ambiguous active palette.*BG1'):
            m.patch(first,resumed,0,colors)
        self.assertEqual(resumed[104:112],bg1)
        self.assertEqual(first[m.OFFSETS[1]:m.OFFSETS[1]+8],bg1)

    def test_unique_primary_can_have_multiple_active_copies(self):
        rom,state=self.fixture()
        state=bytearray(state);state[184:192]=state[176:184]
        _,changed,matches=m.patch(rom,bytes(state),9,
            ['#000000','#ffffff','#00ff00','#0000ff'])
        self.assertEqual(matches,[176,184])
        self.assertEqual(changed[176:184],changed[184:192])

    def test_transparency_preserved(self):
        rom, state = self.fixture()
        with self.assertRaisesRegex(ValueError, 'transparent'):
            m.patch(rom, state, 9, ['#ffffff']*4)

    def test_state_layout_rejected(self):
        rom, state = self.fixture()
        with self.assertRaisesRegex(ValueError, 'layout'):
            m.patch(rom, state[:-1], 9, ['#ffffff']*4)

    def test_rgb_roundtrip(self):
        for value in range(32):
            row = struct.pack('<4H', *([value | value << 5 | value << 10]*4))
            self.assertEqual(m.encode(m.decode(row)), row)

    def test_expanded_palette_edits_preserve_all_other_bytes(self):
        rom, state = self.fixture()
        rom = bytearray(rom + bytes([0xA5])*524288)
        rom[0x147:0x149] = bytes((0x1B,0x05))
        for index,offset in enumerate(m.OFFSETS):
            with self.subTest(index=index):
                source=bytearray(rom)
                # Keep independently owned primary definitions distinct.
                source[m.OFFSETS[9]:m.OFFSETS[9]+8]=m.encode(['#000000','#888888','#00ff00','#0000ff'])
                source[offset:offset+8]=m.encode(['#000000','#ff0000','#00ff00','#0000ff'])
                active=bytearray(state)
                pos=96 if index<7 else 160
                active[pos:pos+8]=source[offset:offset+8]
                changed,resumed,matches=m.patch(bytes(source),bytes(active),index,
                    ['#000000','#ffffff','#00ff00','#0000ff'])
                self.assertIn(pos,matches)
                allowed=set(range(offset,offset+8))|{334,335}
                self.assertEqual(len(changed),len(source))
                self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(source,changed))))
                allowed_state={i for p in matches for i in range(p,p+8)}
                self.assertTrue(all(a==b or i in allowed_state for i,(a,b) in enumerate(zip(active,resumed))))
                self.assertEqual(int.from_bytes(changed[334:336],'big'),
                    (sum(changed[:334])+sum(changed[336:]))&65535)

    def test_expanded_rom_wrong_mapper_or_size_code_rejected(self):
        rom,state=self.fixture()
        for header in (bytes((0x1B,0x04)),bytes((0x03,0x05))):
            expanded=bytearray(rom+bytes(524288));expanded[0x147:0x149]=header
            with self.assertRaisesRegex(ValueError,'expanded ROM header'):
                m.patch(bytes(expanded),state,9,['#000000','#ffffff','#00ff00','#0000ff'])

    def test_actual_ted_candidate_primary_rows_and_private_overrides_preserved(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'tmp/ted-menu-reinstall-trial-01/candidate.gb'
        parent=root/'tmp/sara-atomic-pose-source-16/candidate.gb'
        if not path.exists() or not parent.exists():
            self.skipTest('local exact candidates unavailable')
        rom,old=path.read_bytes(),parent.read_bytes()
        self.assertEqual(m.sha(rom),m.TED_MENU_PIN)
        self.assertEqual(m.sha(old),m.SARA_ATOMIC_PIN)
        with patch.object(m.Bridge,'ssh',side_effect=AssertionError('hardware access')):
            self.assertEqual(m.Bridge(path).source_pin,m.TED_MENU_PIN)
        for index,offset in enumerate(m.OFFSETS):
            self.assertEqual(rom[offset:offset+8],old[offset:offset+8])
            state=bytearray(181040);struct.pack_into('<I',state,4,0xB0CA)
            pos=96 if index<7 else 160
            state[pos:pos+8]=rom[offset:offset+8]
            colors=m.decode(rom[offset:offset+8]);colors[1]='#ffffff'
            changed,resumed,matches=m.patch(rom,bytes(state),index,colors)
            allowed=set(range(offset,offset+8))|{334,335}
            self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(rom,changed))))
            self.assertEqual(changed[524288:],rom[524288:])
            allowed_state={i for p in matches for i in range(p,p+8)}
            self.assertTrue(all(a==b or i in allowed_state for i,(a,b) in enumerate(zip(state,resumed))))

    def test_actual_star_candidate_edits_preserve_fixes(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'tmp/stream-presentation-source-01/candidate.gb'
        parent=root/'tmp/ted-menu-reinstall-trial-01/candidate.gb'
        if not path.exists() or not parent.exists():
            self.skipTest('local exact source-built star candidate unavailable')
        rom,old=path.read_bytes(),parent.read_bytes()
        self.assertEqual(m.sha(rom),m.STAR_PIN)
        self.assertEqual(m.sha(old),m.TED_MENU_PIN)
        with patch.object(m.Bridge,'ssh',side_effect=AssertionError('hardware access')):
            self.assertEqual(m.Bridge(path).source_pin,m.STAR_PIN)
        for index,offset in enumerate(m.OFFSETS):
            with self.subTest(index=index):
                self.assertEqual(rom[offset:offset+8],old[offset:offset+8])
                state=bytearray(181040);struct.pack_into('<I',state,4,0xB0CA)
                pos=96 if index<7 else 160
                state[pos:pos+8]=rom[offset:offset+8]
                colors=m.decode(rom[offset:offset+8]);colors[1]='#ffffff'
                changed,resumed,matches=m.patch(rom,bytes(state),index,colors)
                allowed=set(range(offset,offset+8))|{334,335}
                self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(rom,changed))))
                allowed_state={i for p in matches for i in range(p,p+8)}
                self.assertTrue(all(a==b or i in allowed_state for i,(a,b) in enumerate(zip(state,resumed))))
                self.assertEqual(int.from_bytes(changed[334:336],'big'),
                    (sum(changed[:334])+sum(changed[336:]))&65535)
        # A one-byte modified candidate must not become an accepted starting ROM.
        unknown=bytearray(rom);unknown[0x200]^=1
        with patch.object(Path,'read_bytes',return_value=bytes(unknown)):
            with self.assertRaisesRegex(ValueError,'exact supported pin'):
                m.Bridge(path)

    def test_actual_late_return_candidate_primary_edits_preserve_fixes(self):
        path = m.ROOT/'tmp/stream-late-return-source-01/candidate.gb'
        parent = m.ROOT/'tmp/return-cgb-fade-trial-16/candidate.gb'
        if not path.exists() or not parent.exists():
            self.skipTest('local exact late-return candidate unavailable')
        rom, old = path.read_bytes(), parent.read_bytes()
        pin = '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'
        self.assertEqual(m.sha(rom), pin)
        self.assertEqual(m.sha(old), m.RETURN_FADE_PIN)
        with patch.object(m.subprocess, 'run', side_effect=AssertionError('device access')), \
             patch.object(Path, 'mkdir', return_value=None):
            self.assertEqual(m.Bridge(path).source_pin, pin)
            for index, offset in enumerate(m.OFFSETS):
                with self.subTest(index=index):
                    self.assertEqual(rom[offset:offset+8], old[offset:offset+8])
                    state = bytearray(181040)
                    struct.pack_into('<I', state, 4, 0xB0CA)
                    for row, source in enumerate(m.OFFSETS):
                        pos = 96+8*row if row < 7 else 160+8*(row-7)
                        state[pos:pos+8] = rom[source:source+8]
                    colors = m.decode(rom[offset:offset+8]); colors[1] = '#ffffff'
                    changed, resumed, matches = m.patch(rom, bytes(state), index, colors)
                    pos = 96+8*index if index < 7 else 160+8*(index-7)
                    self.assertEqual(matches, [pos])
                    allowed = set(range(offset, offset+8)) | {334, 335}
                    self.assertTrue(all(a == b or i in allowed for i, (a,b) in enumerate(zip(rom, changed))))
                    self.assertTrue(all(a == b or pos <= i < pos+8 for i, (a,b) in enumerate(zip(state, resumed))))
                    self.assertEqual(changed[offset:offset+8], m.encode(colors))
                    self.assertEqual(resumed[pos:pos+8], m.encode(colors))
                    self.assertEqual(int.from_bytes(changed[334:336], 'big'),
                                     (sum(changed[:334])+sum(changed[336:])) & 65535)
            unknown = bytearray(rom); unknown[0x200] ^= 1
            with patch.object(Path, 'read_bytes', return_value=bytes(unknown)):
                with self.assertRaisesRegex(ValueError, 'exact supported pin'):
                    m.Bridge(path)

    def test_actual_return_candidate_primary_edits_preserve_fixes(self):
        # #19: support the current return-fade build without rolling back fixes.
        path=m.ROOT/'tmp/return-cgb-fade-trial-16/candidate.gb'
        parent=m.ROOT/'tmp/stream-presentation-source-01/candidate.gb'
        if not path.exists() or not parent.exists():
            self.skipTest('local exact return candidate unavailable')
        rom,old=path.read_bytes(),parent.read_bytes()
        pin='126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b'
        self.assertEqual(m.sha(rom),pin)
        self.assertEqual(m.sha(old),m.STAR_PIN)
        with patch.object(m.subprocess,'run',side_effect=AssertionError('device access')):
            self.assertEqual(m.Bridge(path).source_pin,pin)
            for index,offset in enumerate(m.OFFSETS):
                with self.subTest(index=index):
                    self.assertEqual(rom[offset:offset+8],old[offset:offset+8])
                    state=bytearray(181040)
                    struct.pack_into('<I',state,4,0xB0CA)
                    for row,source in enumerate(m.OFFSETS):
                        pos=96+8*row if row<7 else 160+8*(row-7)
                        state[pos:pos+8]=rom[source:source+8]
                    colors=m.decode(rom[offset:offset+8]);colors[1]='#ffffff'
                    changed,resumed,matches=m.patch(rom,bytes(state),index,colors)
                    pos=96+8*index if index<7 else 160+8*(index-7)
                    self.assertEqual(matches,[pos])
                    allowed=set(range(offset,offset+8))|{334,335}
                    self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(rom,changed))))
                    self.assertTrue(all(a==b or pos<=i<pos+8 for i,(a,b) in enumerate(zip(state,resumed))))
                    self.assertEqual(changed[offset:offset+8],m.encode(colors))
                    self.assertEqual(resumed[pos:pos+8],m.encode(colors))
                    self.assertEqual(int.from_bytes(changed[334:336],'big'),
                                     (sum(changed[:334])+sum(changed[336:]))&65535)
            unknown=bytearray(rom);unknown[0x200]^=1
            with patch.object(Path,'read_bytes',return_value=bytes(unknown)):
                with self.assertRaisesRegex(ValueError,'exact supported pin'):
                    m.Bridge(path)


if __name__ == '__main__':
    unittest.main()
