"""#26: distinguish nested VBlank hook cost from disjoint IRQ bodies."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def intervals(rows):
    pending, complete, orphan = {}, [], []
    for row in rows:
        kind = row['kind']
        if row['event'] == 'begin':
            if kind in pending:
                raise ValueError('Repeated IRQ entry without exit')
            pending[kind] = row
        elif row['event'] == 'end':
            begin = pending.pop(kind, None)
            if begin is None:
                orphan.append(row)
            else:
                if begin['sp'] != row['sp']:
                    raise ValueError('Unbalanced IRQ boundary stack')
                if int(row['cycle']) < int(begin['cycle']):
                    raise ValueError('Reversed interval')
                complete.append((kind, int(begin['cycle']), int(row['cycle'])))
        else:
            raise ValueError('Unmeasured interrupt source')
    return complete, orphan, pending


class SecretIRQAccounting(unittest.TestCase):
    def test_palette_service_rewrites_identical_bg0_after_vblank(self):
        folder=ROOT/'tmp/secret-fast-palette-writes-01'
        if not folder.exists(): self.skipTest('Local palette-write trace unavailable')
        trace=folder/'cram-timing.tsv'
        self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(),
                         'cf157f7e881ca34461f5c5d08ccef6d75ac00909c745a6de64dc7f8971eae520')
        with trace.open() as stream:
            rows=list(csv.DictReader(stream,delimiter='\t'))
        self.assertEqual(len(rows),56)
        self.assertFalse(any(int(r['lcdc'],16)&128 and r['mode']=='3' for r in rows))
        frame=[r for r in rows if r['frame']=='7']
        self.assertEqual(len(frame),16)
        self.assertEqual([(r['port'],r['index'],r['value']) for r in frame[:8]],
                         [(r['port'],r['index'],r['value']) for r in frame[8:]])
        self.assertEqual([int(r['index'],16)&63 for r in frame[:8]],list(range(8)))
        self.assertTrue(all(r['port']=='FF69' for r in frame))
        self.assertTrue(all(r['mode']=='1' for r in frame[:8]))
        self.assertTrue(all(int(r['ly'])<144 for r in frame[8:]))
        for suffix in ('s16le','video','states','timeline.tsv','wav'):
            observed=Path('/mnt/data/tmp/penta-secret-fast-palette-writes-01-av')/('native.'+suffix)
            control=Path('/mnt/data/tmp/penta-secret-fast-gated-audio-01-av')/('native.'+suffix)
            self.assertEqual(observed.read_bytes(),control.read_bytes())

    def test_prelude_spike_is_one_scene_transition_not_repeated_detection(self):
        folder = ROOT/'tmp/secret-fast-prelude-cost-01'
        if not folder.exists():
            self.skipTest('Local prelude capture unavailable')
        trace = folder/'vblank-helpers.tsv'
        self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(),
                         'c05b642c4b9ca40324fb1d40728a89b4a01a145df33148def667324672320a4a')
        with trace.open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual(sum(r['pc']=='6F90' for r in rows),480)
        changed = [r for r in rows if r['pc']=='6F98']
        self.assertEqual([r['frame'] for r in changed],['6'])
        transition = {r['pc']:r for r in rows if r['frame']=='6'}
        self.assertEqual(int(transition['6E83']['cycle'])-
                         int(transition['6FA2']['cycle']),13632)
        self.assertEqual((transition['6FA2']['ly'],transition['6E83']['ly']),('152','13'))
        base = Path('/mnt/data/tmp/penta-secret-fast-prelude-cost-01-av')
        control = Path('/mnt/data/tmp/penta-secret-fast-gated-audio-01-av')
        for suffix in ('s16le','video','states','timeline.tsv','wav'):
            with self.subTest(suffix=suffix):
                self.assertEqual((base/('native.'+suffix)).read_bytes(),
                                 (control/('native.'+suffix)).read_bytes())

    def test_late_dma_does_not_prove_missing_sara_pixels(self):
        from PIL import Image
        base = Path('/mnt/data/tmp/penta-secret-fast-oam-lcd-01-av')
        if not base.exists():
            self.skipTest('Local rendered capture unavailable')
        states, video = (base/'native.states').read_bytes(), (base/'native.video').read_bytes()
        self.assertEqual(len(states), 480*71680)
        self.assertEqual(len(video), 480*160*144*4)
        checked = 0
        for frame in range(480):
            state = states[frame*71680:(frame+1)*71680]
            image = Image.frombytes('RGBA', (160,144), video[frame*92160:(frame+1)*92160])
            self.assertFalse(state[0x340] & 4, '8x16 sprites need a different decoder')
            for slot in range(4):
                y, x, tile, attr = state[0x260+4*slot:0x264+4*slot]
                self.assertEqual(attr & 0x88, 0, 'priority/bank not qualified by this check')
                for dy in range(8):
                    sy = 7-dy if attr & 64 else dy
                    off = 0x400+tile*16+2*sy
                    lo, hi = state[off:off+2]
                    for dx in range(8):
                        bit = dx if attr & 32 else 7-dx
                        index = ((lo >> bit)&1) | (((hi >> bit)&1)<<1)
                        px, py = x-8+dx, y-16+dy
                        if not index or not (0 <= px < 160 and 0 <= py < 144):
                            continue
                        at = 0x114+(attr&7)*8+index*2
                        word = int.from_bytes(state[at:at+2], 'little')
                        rgb = tuple(((word >> s)&31)*33//4 for s in (0,5,10))
                        self.assertEqual(image.getpixel((px,py))[:3], rgb, (frame,slot,px,py))
                        checked += 1
        self.assertGreater(checked, 40000)

    def test_lcd_enabled_stock_control_also_has_late_dma(self):
        for name, control, late in (
                ('secret-stock-oam-lcd-01', 'secret-stock-startup-gated-off-01', 133),
                ('secret-fast-oam-lcd-01', 'secret-fast-gated-audio-01', 109)):
            base = ROOT/'tmp'/name
            if not base.exists():
                self.skipTest('Local LCD capture unavailable')
            with (base/'oam-dma.tsv').open() as f:
                rows = list(csv.DictReader(f, delimiter='\t'))
            self.assertEqual(len(rows), 480)
            self.assertTrue(all(int(r['lcdc'],16)&128 for r in rows))
            self.assertEqual(sum(int(r['ly'])<144 for r in rows), late)
            for suffix in ('s16le', 'video', 'states', 'timeline.tsv', 'wav'):
                hashes = []
                for run in (name,control):
                    with (Path('/mnt/data/tmp')/f'penta-{run}-av'/f'native.{suffix}').open('rb') as f:
                        hashes.append(hashlib.file_digest(f,'sha256').hexdigest())
                self.assertEqual(*hashes, (name,suffix))

    def test_helper_dma_capture_preserves_primary_output(self):
        name = 'secret-fast-vblank-dma-02'
        base = ROOT/'tmp'/name
        if not base.exists():
            self.skipTest('Local helper capture unavailable')
        for suffix in ('s16le', 'video', 'states', 'timeline.tsv', 'wav'):
            hashes = []
            for run in (name, 'secret-fast-gated-audio-01'):
                with (Path('/mnt/data/tmp')/f'penta-{run}-av'/f'native.{suffix}').open('rb') as f:
                    hashes.append(hashlib.file_digest(f, 'sha256').hexdigest())
            self.assertEqual(*hashes, suffix)
        with (base/'vblank-helpers.tsv').open() as f:
            rows = list(csv.DictReader(f, delimiter='\t'))
        order = ['73FC', '6F1D', '6F20', '6F23', '6F26', '6F3D',
                 '6F68', '6F6E', '6F82', '6F8C', '6F8F']
        self.assertEqual(len(rows), 480*len(order))
        for offset in range(0, len(rows), len(order)):
            group = rows[offset:offset+len(order)]
            self.assertEqual([r['pc'] for r in group], order)
            times = [int(r['cycle']) for r in group]
            self.assertEqual(times, sorted(times))
        with (base/'oam-dma.tsv').open() as f:
            writes = list(csv.DictReader(f, delimiter='\t'))
        self.assertEqual(len(writes), 480)
        # Preserve this adverse finding, not a claim of sprite-tear causality.
        self.assertEqual(sum(int(r['ly']) < 144 for r in writes), 109)
        with (base/'oam-boundary.tsv').open() as f:
            boundaries = list(csv.DictReader(f, delimiter='\t'))
        self.assertEqual(len(boundaries), 960)
        for pc, count in [('FF80', 103), ('FF8B', 110)]:
            self.assertEqual(sum(r['pc'] == pc and int(r['ly']) < 144
                                 for r in boundaries), count)

    def test_actual_capture_neutrality_and_nested_hook(self):
        for name, control in (
                ('secret-stock-irq-cost-02', 'secret-stock-startup-gated-off-01'),
                ('secret-fast-irq-cost-02', 'secret-fast-gated-audio-01')):
            base = ROOT/'tmp'/name
            if not base.exists():
                self.skipTest('Local capture unavailable')
            receipt = json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'], 0)
            self.assertEqual(hashlib.sha256((base/'probe.lua').read_bytes()).hexdigest(),
                             receipt['probe_sha256'])
            for suffix in ('s16le', 'video', 'states', 'timeline.tsv', 'wav'):
                hashes = []
                for run in (name, control):
                    with (Path('/mnt/data/tmp')/f'penta-{run}-av'/f'native.{suffix}').open('rb') as f:
                        hashes.append(hashlib.file_digest(f, 'sha256').hexdigest())
                self.assertEqual(*hashes, (name, suffix))
            with (base/'irq-cost.tsv').open() as f:
                complete, orphan, pending = intervals(list(csv.DictReader(f, delimiter='\t')))
            bodies = sorted((a, b) for k, a, b in complete if k != 'vblank_hook')
            self.assertTrue(all(b <= c for (_, b), (c, _) in zip(bodies, bodies[1:])))
            vblanks = [(a, b) for k, a, b in complete if k == 'vblank']
            hooks = [(a, b) for k, a, b in complete if k == 'vblank_hook']
            self.assertTrue(hooks)
            uncontained = [(a, b) for a, b in hooks
                           if not any(c <= a <= b <= d for c, d in vblanks)]
            # Stock restores inside VBlank: retain its complete hook but do not
            # invent the missing outer entry or charge this hook twice.
            self.assertEqual(len(uncontained), 1 if 'stock' in name else 0)
            for a, b in uncontained:
                self.assertTrue(any(r['kind'] == 'vblank' and
                                    b <= int(r['cycle']) <= vblanks[0][0]
                                    for r in orphan))
            self.assertEqual(len(orphan), 1 if 'stock' in name else 0)
            self.assertEqual(set(pending), {'timer'} if 'stock' in name else set())

    def test_repeated_entry_is_not_silently_discarded(self):
        row = dict(event='begin', kind='timer', cycle='10', sp='DFF3')
        with self.assertRaises(ValueError):
            intervals([row, row])


if __name__ == '__main__':
    unittest.main()
