"""Static installer contracts for #27; not emulator qualification."""
import sys
import unittest
import hashlib
import json
import zlib
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_arena_completion_safe_trial as trial
from verify_pickup_class_palettes import serialized_state


def runtime(rom, bank):
    if bank == 31:
        return rom[0x7f196:0x7f1e3]
    return b''.join(rom[trial.offset(bank, a):trial.offset(bank, a)+n]
                    for a, n in trial.FRAGMENTS)


class CompletionSafeTrial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = (ROOT/'tmp/arena-alias-source-01/candidate.gb').read_bytes()
        cls.rom = trial.build(cls.parent)

    def test_both_legacy_installers_keep_conditional_completion(self):
        for bank in (16, 31):
            with self.subTest(bank=bank):
                code = runtime(self.rom, bank)
                self.assertEqual(code[56:59], bytes.fromhex('C3DFDB'))
                self.assertEqual(code[59:], runtime(self.parent, bank)[59:])
                self.assertEqual(code[59:], trial.LEGACY)
                self.assertEqual(code[2:5], bytes.fromhex('FA80D8'))

    def test_direct_resolver_spans_two_installed_fragments(self):
        code = runtime(self.rom, 13)
        self.assertEqual(code[56:59], bytes.fromhex('C39734'))
        self.assertEqual(code[59:] + self.rom[0x35830:0x35831], trial.RESOLVER)
        self.assertEqual(code[2:5], bytes.fromhex('CDDFDB'))

    def test_every_known_guard_installer_and_caller_moves_together(self):
        old = trial.OLD_GUARD
        locations = [i for i in range(len(self.parent)-len(old)+1)
                     if self.parent[i:i+len(old)] == old]
        self.assertEqual(locations, [0x35830, 0x4155d, 0x7f1e3])
        for pos in locations:
            self.assertEqual(self.rom[pos:pos+12], trial.NEW_GUARD)
        self.assertNotIn(bytes.fromhex('CDF1DB'), self.rom)
        for pos in (0x42f5, 0x4354):
            self.assertEqual(self.rom[pos:pos+3], bytes.fromhex('CDF3DB'))
        self.assertEqual(self.rom[0x4357:0x435a], bytes.fromhex('C3DCDB'))

    def test_pure_returns_target_shared_stack_restore(self):
        for bank in (13, 16, 31):
            code = runtime(self.rom, bank)
            self.assertEqual(11 + code[10], 49)
            self.assertEqual(16 + code[15], 49)
            self.assertEqual(code[49:52], bytes.fromhex('AFE1C9'))

    def test_rejects_other_parent(self):
        wrong = bytearray(self.parent)
        wrong[0x7f196] ^= 1
        with self.assertRaises(ValueError):
            trial.build(wrong)

    def test_retained_native_alias_onset_and_broken_control(self):
        folder = ROOT/'tmp/arena-completion-safe-shalamar-onset-01'
        if not (folder/'receipt.json').exists():
            self.skipTest('local emulator evidence unavailable')
        receipt = json.loads((folder/'receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'], hashlib.sha256(self.rom).hexdigest())
        self.assertFalse(receipt['observer_memory_writes'])
        expected = bytes([0, 0]+[4]*253+[0])
        aliases = []
        for frame in range(1, 181):
            raw = serialized_state(folder/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(raw[4:8], 'little'), zlib.crc32(self.rom)&0xffffffff)
            self.assertEqual(raw[0x3e4], 0)  # active fight, not frozen menu
            self.assertEqual(raw[0x3b7], 12)
            self.assertEqual(raw[0x4a00:0x4b00], expected)
            if raw[0x5c80] == 11:
                aliases.append(frame)
        self.assertEqual(aliases, list(range(119, 181)))
        broken = serialized_state(ROOT/'tmp/star-shalamar-native-inventory-phase721-01/frame-0999.ss0')
        self.assertEqual((broken[0x5c80], broken[0x3b7]), (11, 12))
        self.assertNotEqual(broken[0x4a00:0x4b00], expected)

    def test_assisted_secret_return_keeps_direct_runtime(self):
        from check_secret_pickup_attributes import inspect_planes
        folder = ROOT/'tmp/arena-completion-safe-late-pause-return-01'
        if not (folder/'receipt.json').exists():
            self.skipTest('local transition evidence unavailable')
        receipt = json.loads((folder/'receipt.json').read_text())
        self.assertTrue(receipt['observer_memory_writes'])
        self.assertEqual(receipt['rom_sha256'], hashlib.sha256(self.rom).hexdigest())
        with (folder/'trace.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        with (folder/'item-action.tsv').open() as stream:
            items = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual(len(rows), 12000)
        returned = next(r for r in rows[7500:] if (r['scene'], r['stage']) == ('02', '00'))
        self.assertEqual(returned['frame'], '8334')
        self.assertEqual(items[8333]['pause_timer'], '46')
        for frame, scene in ((7080, 9), (7440, 9), (9000, 2)):
            raw = serialized_state(folder/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(raw[4:8], 'little'), zlib.crc32(self.rom)&0xffffffff)
            self.assertEqual(raw[0x5c80], scene)
            self.assertEqual(raw[0x630d], 10)  # stale cache persists, no longer used here
            self.assertEqual(raw[0x5fdf:0x5ff2], trial.RESOLVER)
            if scene == 9:
                self.assertEqual(inspect_planes(raw, self.rom)['mismatches'], [])

    def test_native_damage_restart_evidence(self):
        from verify_gameover_restart import validate, validate_stage_cards
        from gameover_sequence import validate_sequence
        folder = ROOT/'tmp/arena-completion-safe-natural-restart-01'
        if not (folder/'receipt.json').exists():
            self.skipTest('local restart evidence unavailable')
        receipt = json.loads((folder/'receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'], hashlib.sha256(self.rom).hexdigest())
        self.assertEqual((folder/'runtime/candidate.gb').read_bytes(), self.rom)
        self.assertIn('movement-driven native damage', receipt['stimulus'])
        self.assertEqual((folder/'route.txt').read_text().strip(), 'ok 2 2 2')
        validate(folder)
        validate_stage_cards(folder, saved_game=True)
        self.assertEqual(validate_sequence(folder), {'title_frame_pairs': 482, 'gameover_frames': 102})

    def test_ted_storage_identity_does_not_approve_penta_fixture(self):
        from generate_stream_boss_states import relocated_ted_latches, PENTA_SYNC_INHERITORS_SHA256
        self.assertTrue(relocated_ted_latches(self.rom))
        self.assertEqual(hashlib.sha256(self.rom[17*0x4000:18*0x4000]).hexdigest(),
                         '6aa4f5f8105b300176429bfe69b7dce4688720f915982e3a6243202acc9ce8d7')
        self.assertNotIn(hashlib.sha256(self.rom).hexdigest(), PENTA_SYNC_INHERITORS_SHA256)
        changed = bytearray(self.rom)
        changed[0x44364] ^= 1
        self.assertFalse(relocated_ted_latches(changed))

    def test_ted_menu_replay_does_not_claim_legacy_installer_execution(self):
        from check_boss_menu_fades import inspect_roundtrips
        folder = ROOT/'tmp/arena-completion-safe-ted-menus-01'
        if not (folder/'completion.json').exists():
            self.skipTest('local Ted evidence unavailable')
        receipt = json.loads((folder/'completion.json').read_text())
        self.assertEqual(receipt['rom']['sha256'], hashlib.sha256(self.rom).hexdigest())
        verdict = inspect_roundtrips(folder, 16, 720)
        self.assertEqual(verdict['status'], 'PASS')
        for frame in range(1, 1081):
            raw = serialized_state(folder/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(raw[4:8], 'little'), zlib.crc32(self.rom)&0xffffffff)
            self.assertEqual(raw[0x5fdc:0x5fdf], bytes.fromhex('C39734'))
            self.assertEqual(raw[0x5fdf:0x5ff2], trial.RESOLVER)

    def test_injected_stale_gateway_executes_bank31_repair_and_zero_completion(self):
        folder = ROOT/'tmp/arena-completion-safe-repair-injection-01'
        if not (folder/'completion.json').exists():
            self.skipTest('local fault-injection evidence unavailable')
        receipt = json.loads((folder/'completion.json').read_text())
        self.assertTrue(receipt['diagnostic_only'])
        self.assertTrue(receipt['completed'])
        self.assertEqual(receipt['rom_sha256'], hashlib.sha256(self.rom).hexdigest())
        self.assertIn('D880=0B; DADE..DAE0=C2B9DA', receipt['injection'])
        with (folder/'events.tsv').open() as stream:
            events = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual([e['pc'] for e in events[:7]],
                         ['3492', '6F00', '6F55', '6D4D', 'DBDC', 'DBDF', '3497'])
        self.assertEqual(events[1]['bank'], '1F')
        for frame in (2, 4, 10, 30, 180):
            raw = serialized_state(folder/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(raw[4:8], 'little'), zlib.crc32(self.rom)&0xffffffff)
            self.assertEqual(raw[0x5ede:0x5ee1], bytes.fromhex('C41300'))
            self.assertEqual(raw[0x5fdc:0x5fdf], bytes.fromhex('C3DFDB'))
            self.assertEqual(raw[0x5fdf:0x5ff1], trial.LEGACY)
            self.assertEqual(raw[0x5ff1:0x5ffd], trial.NEW_GUARD)
            self.assertEqual(raw[0x3e1], 0)  # nonzero branch NOT covered

    def test_pending_completion_branch_clears_flag_and_returns(self):
        folder = ROOT/'tmp/arena-completion-safe-pending-walk-injection-01'
        if not (folder/'completion.json').exists():
            self.skipTest('local pending-branch evidence unavailable')
        receipt = json.loads((folder/'completion.json').read_text())
        self.assertTrue(receipt['diagnostic_only'])
        self.assertEqual(receipt['rom_sha256'], hashlib.sha256(self.rom).hexdigest())
        with (folder/'events.tsv').open() as stream:
            events = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual([e['pc'] for e in events[:6]],
                         ['DBDC', 'DBDF', '4000', '4042', 'DBEE', '3497'])
        self.assertEqual([e['ffe1'] for e in events[:6]], ['01']*3+['00']*3)
        self.assertEqual({e['frame'] for e in events[:6]}, {'6'})
        for frame in (7, 30, 180):
            raw = serialized_state(folder/f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(raw[4:8], 'little'), zlib.crc32(self.rom)&0xffffffff)
            self.assertEqual(raw[0x3e1], 0)
            self.assertEqual(raw[0x5c80], 2)
            self.assertEqual(raw[0x5fdf:0x5ff1], trial.LEGACY)
        # Stationary trial is retained as explicit noncoverage, not a pass.
        stationary = ROOT/'tmp/arena-completion-safe-pending-injection-01'
        self.assertIn('injected=false', (stationary/'done').read_text())

    def test_healthy_shalamar_throughput_tradeoff_is_visible(self):
        from verify_boss_speed_parity import classify_throughput
        candidate = ROOT/'tmp/arena-completion-safe-shalamar-speed-01/receipt.json'
        parent = ROOT/'tmp/arena-completion-parent-shalamar-speed-01/receipt.json'
        if not candidate.exists() or not parent.exists():
            self.skipTest('local speed evidence unavailable')
        c, p = json.loads(candidate.read_text()), json.loads(parent.read_text())
        self.assertEqual(c['dx_rom_sha256'], hashlib.sha256(self.rom).hexdigest())
        self.assertEqual(p['dx_rom_sha256'], 'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5')
        for receipt in (c, p):
            self.assertEqual(receipt['observation_frames'], 1800)
            self.assertEqual(receipt['accepted_slow_bosses'], {})
            self.assertIsNone(receipt['bounded_speedup_ceiling'])
            for side in ('og', 'dx'):
                row = receipt['bosses'][0][side]
                self.assertEqual(row['scene_frames'], 1800)
                self.assertEqual(row['main_loop_hits'], row['raw_anchor_hits'])
                self.assertTrue(row['deterministic_replay'])
                trace = Path(row['trace'])
                self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(), row['trace_sha256'])
        self.assertEqual(c['bosses'][0]['dx']['main_loop_hits'], 336)
        self.assertEqual(p['bosses'][0]['dx']['main_loop_hits'], 337)
        self.assertTrue(classify_throughput('shalamar', 336/337, .02, {}, None)['target_met'])
        self.assertFalse(classify_throughput('shalamar', .97, .02, {}, None)['throughput_accepted'])
