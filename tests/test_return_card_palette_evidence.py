"""#45: card-to-dungeon replay has no BG-CRAM update to hide setup."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ReturnCardPaletteEvidence(unittest.TestCase):
    def test_interrupt_name_does_not_guarantee_palette_write_window(self):
        names=('return-card-palette-control-01','return-card-irq-window-01',
               'return-card-helper-window-01')
        receipts=[]
        for name in names:
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists(): self.skipTest('local IRQ replay unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['native_capture']['metadata']['frames'],240)
            receipts.append(receipt)
        for key in ('rom_sha256','source_state_sha256','probe_sha256','runner_sha256',
                    'guard_sha256','native_tap_sha256'):
            self.assertEqual(len({r[key] for r in receipts}),1)
        for ext in ('video','states','s16le','timeline.tsv'):
            hashes=[]
            for receipt in receipts:
                path=Path(receipt['native_capture_directory'])/f'native.{ext}'
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(digest,receipt['native_capture']['hashes'][path.name])
                hashes.append(digest)
            self.assertEqual(len(set(hashes)),1)
        base=ROOT/'tmp/return-card-helper-window-01'
        with (base/'irq-cost.tsv').open() as stream:
            irq=list(csv.DictReader(stream,delimiter='\t'))
        spans=[]
        start=None
        for row in irq:
            if row['kind']!='vblank_hook': continue
            if row['event']=='begin':
                self.assertIsNone(start)
                start=int(row['cycle'])
            elif row['event']=='end':
                self.assertIsNotNone(start)
                spans.append((start,int(row['cycle'])))
                start=None
        self.assertIsNone(start)
        with (base/'vblank-helpers.tsv').open() as stream:
            sites=[r for r in csv.DictReader(stream,delimiter='\t') if r['pc']=='6F23']
        self.assertEqual(len(sites),239)
        # Validate banked observations against fixed-address interrupt spans,
        # not a bank-shadow assumption or the helper's misleading name.
        self.assertTrue(all(any(a<=int(r['cycle'])<=b for a,b in spans) for r in sites))
        self.assertEqual(Counter(int(r['stat'])&3 for r in sites),{1:199,3:19,2:13,0:8})
        first=next(r for r in sites if int(r['stat'])&3==3)
        self.assertEqual((int(first['frame']),int(first['ly'])),(113,2))

    def test_delayed_background_writes_and_complete_observer_neutrality(self):
        captures=[]
        for name in ('return-card-palette-window-01','return-card-palette-control-01'):
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists(): self.skipTest('local card replay unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['rom_sha256'],'916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb')
            self.assertEqual(receipt['source_state_sha256'],'c48bc5419fb7d68e95239d46909461d54d8bbc0f48f1f2eee3a11466af989e46')
            self.assertEqual(receipt['native_capture']['metadata']['frames'],240)
            captures.append((receipt,Path(receipt['native_capture_directory'])))
        for ext in ('video','states','s16le','timeline.tsv'):
            hashes=[]
            for receipt,path in captures:
                digest=hashlib.sha256((path/f'native.{ext}').read_bytes()).hexdigest()
                self.assertEqual(digest,receipt['native_capture']['hashes'][f'native.{ext}'])
                hashes.append(digest)
            self.assertEqual(*hashes)
        with (ROOT/'tmp/return-card-palette-window-01/cram-timing.tsv').open() as stream:
            rows=list(csv.DictReader(stream,delimiter='\t'))
        self.assertEqual(len(rows),128)
        bg=[r for r in rows if r['port']=='FF69']
        obj=[r for r in rows if r['port']=='FF6B']
        self.assertEqual((len(bg),len(obj)),(64,64))
        self.assertEqual((min(int(r['frame']) for r in bg),max(int(r['frame']) for r in bg)),(190,197))
        states=(captures[0][1]/'native.states').read_bytes()
        scenes=[states[i*71680+0x5c80] for i in range(240)]
        self.assertIn(0x18,scenes)
        self.assertIn(2,scenes)
        initial=states[0xd4:0x114]
        self.assertTrue(all(states[i*71680+0xd4:i*71680+0x114]==initial for i in range(189)))
        self.assertNotEqual(states[-71680+0xd4:-71680+0x114],initial)

    def test_fade_begins_on_active_card_before_inactive_dungeon(self):
        base=ROOT/'tmp/return-card-palette-window-01'
        if not (base/'receipt.json').exists(): self.skipTest('local card replay unavailable')
        receipt=json.loads((base/'receipt.json').read_text())
        path=Path(receipt['native_capture_directory'])/'native.states'
        raw=path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),receipt['native_capture']['hashes']['native.states'])
        self.assertEqual(len(raw),240*71680)
        # Native serialized IO/HRAM plus physical WRAM bank1: D880 and DF4C.
        offsets=(0x5c80,0x3c1,0x347,0x634c,0x3e4)
        changes=[]
        previous=None
        for i in range(240):
            state=raw[i*71680:(i+1)*71680]
            row=tuple(state[x] for x in offsets)
            if row!=previous: changes.append((i+1,*row))
            previous=row
        self.assertEqual(changes[:11],[
            (1,0x18,1,0xe4,0,1),
            (93,0x18,1,0x90,0,1),
            (97,0x18,1,0x40,0,1),
            (101,0x18,1,0,0,1),
            (121,2,1,0,0,1),
            (123,2,0,0,0,1),
            (141,2,0,0x40,0,1),
            (150,2,0,0x90,0,1),
            (158,2,0,0xe4,0,1),
            (178,2,1,0xe4,0,0),
            (182,2,1,0xe4,1,0),
        ])
        self.assertEqual(changes[11:],[
            *((181+phase,2,1,0xe4,phase,0) for phase in range(2,17)),
            (198,2,1,0xe4,0,0),
        ])
        # This is a retained failure: an FFC1==0-only fade service cannot
        # cover the card's first three shade changes at frames93..101.
        self.assertTrue(all(changes[i][2]==1 for i in (1,2,3)))
