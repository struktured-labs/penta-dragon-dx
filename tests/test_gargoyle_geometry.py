import importlib.util
import io
import csv
import hashlib
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('geometry', Path(__file__).resolve().parents[1] / 'scripts/diagnostics/check_gargoyle_geometry.py')
geometry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geometry)


def frame():
    state = bytearray(geometry.STATE_BYTES)
    state[0x3bf] = 1
    for i, offset in enumerate(geometry.LAYOUT, 4):
        state[0x260+i*4:0x264+i*4] = bytes((32+offset//4*8, 64+offset%4*8, 0x30+offset, 6))
    return state


class GeometryTests(unittest.TestCase):
    def test_card_entry_ablation_recovers_full_parent_pcm(self):
        root = Path(__file__).resolve().parents[1]
        source = root/'scripts/diagnostics/build_card_route_ablation.py'
        spec = importlib.util.spec_from_file_location('card_ablation', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parent = root/'tmp/fixed-fade-route-trial-01/candidate.gb'
        trial = root/'tmp/card-route-ablation-01/candidate.gb'
        if not trial.is_file():
            self.skipTest('optional local card ablation unavailable')
        original, changed = parent.read_bytes(), trial.read_bytes()
        self.assertEqual(module.build(original), changed)
        self.assertEqual(hashlib.sha256(changed).hexdigest(),
                         '6cf95d403a53d8d9d55e1c7ccfc53e4d299aace1ab4561721779d9ca3435282b')
        self.assertEqual([i for i, (a, b) in enumerate(zip(original, changed)) if a != b],
                         [0x14F, 0x75F1, 0x75F2])
        with self.assertRaises(ValueError):
            module.build(changed)
        late = (root/'tmp/stream-late-return-source-01/candidate.gb').read_bytes()
        with self.assertRaises(ValueError):
            module.build(late)
        with self.assertRaises(ValueError):
            module.build(original, late_return=True)
        late_changed = module.build(late, late_return=True)
        self.assertEqual(hashlib.sha256(late_changed).hexdigest(),
                         '7916d5152ff628fab1b95753bd89fb1c65f850c791d7475480a06b55e28083de')
        self.assertEqual([i for i, (a, b) in enumerate(zip(late, late_changed)) if a != b],
                         [0x14F, 0x75F1, 0x75F2])
        captures = []
        for name in ('fastpath-gargoyle-patrol-01', 'card-route-ablation-gargoyle-01'):
            r = json.loads((root/'tmp'/name/'receipt.json').read_text())
            self.assertEqual(r['status'], 0)
            hashes = {}
            for artifact in ('native.video', 'native.s16le', 'native.wav', 'native.timeline.tsv'):
                with (Path(r['native_capture_directory'])/artifact).open('rb') as stream:
                    hashes[artifact] = hashlib.file_digest(stream, 'sha256').hexdigest()
            captures.append(hashes)
        self.assertEqual(captures[0], captures[1])

    def test_fixed_route_sound_trace_is_neutral_and_localizes_timing(self):
        root = Path(__file__).resolve().parents[1]
        traces = []
        fades = []
        for stem, pin in (
            ('fastpath', 'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b'),
            ('fixed-route', '988b3e07bcfd884c01f7355704a48530502cab157d01d33f2767417ffd9921b7'),
        ):
            captures = []
            for kind in ('patrol', 'sound-on'):
                path = root/'tmp'/f'{stem}-gargoyle-{kind}-01'
                if not (path/'receipt.json').is_file():
                    self.skipTest('optional local sound timing captures unavailable')
                receipt = json.loads((path/'receipt.json').read_text())
                self.assertEqual(receipt['status'], 0)
                self.assertEqual(hashlib.sha256((path/'candidate.gb').read_bytes()).hexdigest(), pin)
                hashes = {}
                for name, expected in receipt['native_capture']['hashes'].items():
                    with (Path(receipt['native_capture_directory'])/name).open('rb') as stream:
                        hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
                    self.assertEqual(hashes[name], expected)
                captures.append(hashes)
                # This is a cold assisted route, not restored-state qualification.
                self.assertEqual(receipt['native_capture']['restored_replay_epoch']['status'], 'FAIL')
            self.assertEqual(captures[0], captures[1])
            with (path/'sound-timing.tsv').open() as stream:
                traces.append(list(csv.DictReader(stream, delimiter='\t')))
            with (path/'secret-fade-timing.tsv').open() as stream:
                fades.append(list(csv.DictReader(stream, delimiter='\t')))
        for timer, count, changed in ((True, 3561, 76), (False, 5819, 133)):
            a, b = [[r for r in rows if (r['kind'] == 'timer') == timer] for rows in traces]
            self.assertEqual(len(a), count)
            self.assertEqual(len(b), count)
            self.assertEqual([(r['kind'], r['value']) for r in a],
                             [(r['kind'], r['value']) for r in b])
            differences = [(int(r['frame']), int(s['cycle'])-int(r['cycle']))
                           for r, s in zip(a, b) if r['cycle'] != s['cycle']]
            self.assertEqual(len(differences), changed)
            self.assertEqual((min(f for f, _ in differences), max(f for f, _ in differences)), (559, 629))
            self.assertEqual((min(d for _, d in differences), max(d for _, d in differences)), (-40, 24))
        self.assertEqual([r['pc'] for r in fades[0]], [r['pc'] for r in fades[1]])
        self.assertEqual([int(b['cycle'])-int(a['cycle']) for a, b in zip(*fades)], [0, 0, 0, 88, -16])

    def test_corrected_patrol_reproduces_report_and_latest_is_coherent(self):
        cases = [
            ('late-return-gargoyle-patrol-01', 'PASS', 0, 1578, 166,
             '12d5229c2f896a41ea2ddde9a03f14b1933c63b44a6abedd54e2a654af3deb2a'),
            ('return-fade16-gargoyle-patrol-01', 'PASS', 0, 1578, 166,
             '727a94199d43a204d70cd8e1e2a2057c4c2e6a047bbc324ac3f604133da3fc95'),
            ('gargoyle-reported-patrol-corrected-01', 'FAIL', 18, 1633, 175,
             '63fc2863a842c884d3af5615037a2f68c0207565a2ecd237eacd8db443c99779'),
            ('gargoyle-latest-patrol-01', 'PASS', 0, 1578, 166,
             'a5251b015485073f7856e9b6dccd6218c148383731956b0913a9087b64bc8651'),
        ]
        for name,status,mixed,coherent,censored,digest in cases:
            path = Path('/mnt/data/tmp')/f'penta-{name}-av/native.states'
            if not path.is_file():
                self.skipTest('optional corrected patrol captures unavailable')
            with path.open('rb') as stream:
                result = geometry.inspect(stream,2400)
            self.assertEqual(result['states_sha256'],digest)
            self.assertEqual(result['status'],status)
            self.assertEqual(len(result['mixed_frames']),mixed)
            self.assertEqual(result['coherent_frames'],coherent)
            self.assertEqual(len(result['not_fully_visible_frames']),censored)

    def test_current_candidate_patrol_preserves_repaired_video_and_pcm(self):
        root=Path(__file__).resolve().parents[1]
        names=('gargoyle-latest-patrol-01','return-fade16-gargoyle-patrol-01')
        pins=('665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7',
              '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        captures=[]
        for name,pin in zip(names,pins):
            p=root/'tmp'/name
            if not (p/'receipt.json').exists():
                self.skipTest('local patrol evidence unavailable')
            receipt=json.loads((p/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertEqual(hashlib.sha256((p/'candidate.gb').read_bytes()).hexdigest(),pin)
            self.assertTrue(receipt['observer_memory_writes'])  # Assisted, not natural progression.
            capture=Path(receipt['native_capture_directory'])
            hashes={}
            for artifact in ('native.video','native.s16le','native.wav','native.timeline.tsv'):
                with (capture/artifact).open('rb') as stream:
                    hashes[artifact]=hashlib.file_digest(stream,'sha256').hexdigest()
                self.assertEqual(hashes[artifact],receipt['native_capture']['hashes'][artifact])
            captures.append(hashes)
            # Cold boot is not a qualified restored-state epoch.
            self.assertEqual(receipt['native_capture']['restored_replay_epoch']['status'],'FAIL')
        self.assertEqual(captures[0],captures[1])

    def test_late_return_video_pass_does_not_hide_audio_failure(self):
        root = Path(__file__).resolve().parents[1]
        receipts = []
        for name in ('return-fade16-gargoyle-patrol-01', 'late-return-gargoyle-patrol-01'):
            path = root/'tmp'/name
            if not (path/'receipt.json').exists():
                self.skipTest('local current patrol captures unavailable')
            r = json.loads((path/'receipt.json').read_text())
            self.assertEqual(r['status'], 0)
            self.assertEqual(hashlib.sha256((path/'candidate.gb').read_bytes()).hexdigest(), r['rom_sha256'])
            for artifact, expected in r['native_capture']['hashes'].items():
                with (Path(r['native_capture_directory'])/artifact).open('rb') as stream:
                    self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(), expected)
            receipts.append(r)
        self.assertEqual(receipts[1]['rom_sha256'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        a, b = [r['native_capture']['hashes'] for r in receipts]
        self.assertEqual(a['native.video'], b['native.video'])
        self.assertEqual(a['native.timeline.tsv'], b['native.timeline.tsv'])
        self.assertNotEqual(a['native.s16le'], b['native.s16le'])
        report = json.loads((root/'tmp/late-return-gargoyle-audio-pair-01/receipt.json').read_text())
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['different_sample_frames'], 2514)
        self.assertFalse(report['checks']['same_digital_silence_intervals'])
        for r in receipts:
            self.assertEqual(r['native_capture']['restored_replay_epoch']['status'], 'FAIL')

    def test_audio_change_is_localized_to_fixed_route_step(self):
        root = Path(__file__).resolve().parents[1]
        cases = [('return-fade16-gargoyle-patrol-01', '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b'),
                 ('fastpath-gargoyle-patrol-01', 'ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b'),
                 ('fixed-route-gargoyle-patrol-01', '988b3e07bcfd884c01f7355704a48530502cab157d01d33f2767417ffd9921b7'),
                 ('late-return-gargoyle-patrol-01', '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')]
        captures = []
        for name, pin in cases:
            path = root/'tmp'/name
            if not (path/'receipt.json').exists():
                self.skipTest('local intermediate replay unavailable')
            r = json.loads((path/'receipt.json').read_text())
            self.assertEqual(hashlib.sha256((path/'candidate.gb').read_bytes()).hexdigest(), pin)
            self.assertEqual(r['status'], 0)
            h = r['native_capture']['hashes']
            for artifact in ('native.video', 'native.s16le', 'native.timeline.tsv'):
                with (Path(r['native_capture_directory'])/artifact).open('rb') as stream:
                    self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(), h[artifact])
            captures.append(h)
        self.assertEqual(len({h['native.video'] for h in captures}), 1)
        self.assertEqual(len({h['native.timeline.tsv'] for h in captures}), 1)
        self.assertEqual(captures[0]['native.s16le'], captures[1]['native.s16le'])
        self.assertNotEqual(captures[1]['native.s16le'], captures[2]['native.s16le'])
        self.assertEqual(captures[2]['native.s16le'], captures[3]['native.s16le'])

    def test_coherent(self):
        self.assertEqual(geometry.inspect(io.BytesIO(frame()), 1)['status'], 'PASS')

    def test_spider_identity_is_explicit(self):
        state=frame()
        state[0x3bf]=2
        self.assertEqual(geometry.inspect(io.BytesIO(state), 1)['status'], 'FAIL')
        self.assertEqual(geometry.inspect(io.BytesIO(state), 1, 2)['status'], 'PASS')
        with self.assertRaises(ValueError):
            geometry.inspect(io.BytesIO(state), 1, 3)

    def test_one_piece_position_mutation_fails(self):
        state = frame()
        state[0x260+19*4+1] += 8
        result = geometry.inspect(io.BytesIO(state), 1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['mixed_frames'][0]['frame'], 1)

    def test_censored_only_is_not_success(self):
        state = frame()
        state[0x260+4*4] = 0
        result = geometry.inspect(io.BytesIO(state), 1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['not_fully_visible_frames'], [1])

    def test_missing_boss_is_not_success(self):
        state = frame()
        state[0x3bf] = 0
        self.assertEqual(geometry.inspect(io.BytesIO(state), 1)['status'], 'FAIL')

    def test_truncation_and_wrong_length_rejected(self):
        for data, count in [(frame()[:-1], 1), (frame(), 2)]:
            with self.assertRaises(ValueError):
                geometry.inspect(io.BytesIO(data), count)

    def test_retained_broken_control_and_incomplete_trial(self):
        for label, count in [('tear', 12), ('atomic', 1)]:
            path = Path(f'/mnt/data/tmp/penta-gargoyle-{label}-av-01/native.states')
            if not path.is_file():
                self.skipTest('optional retained native captures unavailable')
            with path.open('rb') as stream:
                result = geometry.inspect(stream, 1800)
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(len(result['mixed_frames']), count)

    def test_retained_vblank_guard_has_visible_coherent_boss(self):
        path = Path('/mnt/data/tmp/penta-gargoyle-vblank-guard-av-02/native.states')
        if not path.is_file():
            self.skipTest('optional retained native capture unavailable')
        with path.open('rb') as stream:
            result = geometry.inspect(stream, 1800)
        self.assertEqual(result['states_sha256'],
                         '43ab109502051d75b5dbc1c98fd1633ebd42bb81c373c5dd118230b75c2bcc44')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['coherent_frames'], 1061)
        self.assertEqual(len(result['not_fully_visible_frames']), 165)
