"""Negative controls for the reported missing-level/colour/ceiling failures."""
import sys
from pathlib import Path
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
from verify_gameover_restart import compare_images, check_ceiling, validate, validate_stage_cards
import build_gameover_title_guard_trial as title_trial
import build_gameover_row_guard as row_guard
import build_spike_death_trial as spike_death_trial


class ReleaseCoverage(unittest.TestCase):
    def test_matrix_keeps_blank_and_saved_restart_routes(self):
        from verify_release_candidate import build_gates
        gates = {gate.name: gate.command for gate in build_gates(
            ROOT / 'tmp/nonexistent-test-candidate.gb', ROOT / 'tmp/unused-roster',
            expanded_candidate_override=True, menu_icon_candidate_override=True)}
        self.assertNotIn('--saved-game', gates['gameover_spike_restart'])
        self.assertIn('--hazard-death', gates['gameover_spike_restart'])
        for flag in ('--hazard-death', '--saved-game', '--sequence'):
            self.assertIn(flag, gates['gameover_saved_spike_restart'])


class RowGuardPatch(unittest.TestCase):
    def test_unknown_parent_and_successor_rejected(self):
        with self.assertRaises(ValueError):
            row_guard.build(bytes(512 * 1024))
        with self.assertRaises(ValueError):
            row_guard.authenticated_parent(bytes(512 * 1024))

    def test_both_guards_use_original_cleanup_not_raw_mapper(self):
        helper=row_guard.patches()[2][2]
        self.assertIn(bytes.fromhex('CA 5D 43'), helper)
        self.assertIn(bytes.fromhex('CA 5D 45'), helper)
        self.assertNotIn(bytes.fromhex('CA DF 6C'), helper)
        self.assertTrue(helper.endswith(bytes.fromhex('F0 40 CB 7F C3 04 45')))

    def test_only_row_entries_and_unused_helper_cave_owned(self):
        self.assertEqual([p[0] for p in row_guard.patches()], [0x4300,0x4500,0x43B0])
        for address,before,after in row_guard.patches():
            self.assertEqual(len(before),len(after))
        self.assertEqual(row_guard.patches()[2][1], b'\xff'*26)


class TitleRetirementPatch(unittest.TestCase):
    def test_rejects_unknown_parent(self):
        with self.assertRaisesRegex(ValueError, "exact r536"):
            title_trial.build(bytes(512 * 1024))

    def test_patch_preserves_width_and_owns_only_title_bank(self):
        for address, before, after in title_trial.patches():
            self.assertEqual(len(before), len(after))
            self.assertGreaterEqual(title_trial.offset(address), 25 * 0x4000)
            self.assertLessEqual(title_trial.offset(address) + len(after), 26 * 0x4000)

    def test_cold_title_flags_restored_before_palette_write(self):
        payload = title_trial.patches()[1][2]
        self.assertEqual(payload, bytes.fromhex('AF E0 C1 E0 B7 3E 88 E0 68 C3 11 6D'))

    def test_probe_uses_physical_scene_and_hp(self):
        probe = (ROOT / 'scripts/diagnostics/probe_gameover_restart.lua').read_text()
        self.assertIn('wram:read8(address - 0xC000)', probe)
        self.assertIn('native_assistance.write(0xDCBB, 0)', probe)
        self.assertIn(':write8(address - 0xC000, value)', probe)
        self.assertNotIn('emu:read8(0xD880)', probe)
        self.assertNotIn('emu:write8(0xDCBB', probe)

    def test_optional_traversal_keeps_all_three_checkpoints_required(self):
        import inspect
        source = inspect.getsource(validate)
        self.assertIn('"travel-0668", "travel-05AC", "travel-03A4"', source)
        self.assertIn('if traverse else ()', source)
        probe = (ROOT / 'scripts/diagnostics/probe_gameover_restart.lua').read_text()
        self.assertIn('local travel_targets = {0x0668, 0x05AC, 0x03A4}', probe)
        self.assertIn('camera == travel_targets[travel_index]', probe)


class SpikeDeathRecoveryPatch(unittest.TestCase):
    def test_returned_title_guard_preserves_cold_title_timing(self):
        by_location = {
            (bank, address): (before, after)
            for bank, address, before, after in spike_death_trial.patches()
        }
        self.assertNotIn((13, 0x6A6E), by_location)
        self.assertEqual(
            by_location[(13, 0x6A97)],
            (bytes.fromhex('C3 45 7E'), bytes.fromhex('C3 65 58')),
        )

    def test_returned_title_guard_repairs_only_physical_scene_one(self):
        by_location = {
            (bank, address): after
            for bank, address, _before, after in spike_death_trial.patches()
        }
        self.assertEqual(
            by_location[(13, 0x5865)],
            bytes.fromhex('FA 80 D8 FE 01 CA 73 6A C3 45 7E'),
        )

    def test_unknown_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact row-guard parent'):
            spike_death_trial.build(bytes(512 * 1024))


class RecoveryAssertions(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tmp", prefix="restart-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.before = self.root / "before.png"
        self.after = self.root / "after.png"
        Image.new("RGB", (160, 144), (60, 80, 120)).save(self.before)
        with Image.open(self.before) as image:
            image.putpixel((20, 40), (0, 255, 255))
            image.save(self.before)

    def test_unchanged_rendering(self):
        compare_images(self.before, self.before, (0, 32, 160, 128))

    def stage_cards(self):
        for label in ('stage-selector', 'stage-card'):
            for name in ('before', 'after-1', 'after-2'):
                with Image.open(self.before) as image:
                    image.save(self.root / f'{label}-{name}.png')

    def test_stage_cards_match(self):
        self.stage_cards()
        validate_stage_cards(self.root)

    def test_matching_blank_selectors_rejected(self):
        self.stage_cards()
        for name in ('before', 'after-1', 'after-2'):
            Image.new('RGB', (160, 144), 'white').save(
                self.root / f'stage-selector-{name}.png')
        with self.assertRaisesRegex(ValueError, 'blank stage screen'):
            validate_stage_cards(self.root)

    def test_stage_card_grayscale_after_second_death_rejected(self):
        self.stage_cards()
        with Image.open(self.before) as image:
            image.convert('L').save(self.root / 'stage-card-after-2.png')
        with self.assertRaisesRegex(ValueError, 'rendering changed'):
            validate_stage_cards(self.root)

    def test_missing_stage_card_rejected(self):
        with self.assertRaises(FileNotFoundError):
            validate_stage_cards(self.root)

    def test_score_selector_corruption_rejected(self):
        self.stage_cards()
        with Image.open(self.before) as image:
            image.putpixel((60, 40), (255, 255, 255))
            image.save(self.root / 'stage-selector-after-1.png')
        with self.assertRaisesRegex(ValueError, 'stage-selector'):
            validate_stage_cards(self.root)

    def test_plain_card_alone_cannot_prove_both_variants(self):
        for name in ('before', 'after-1', 'after-2'):
            with Image.open(self.before) as image:
                image.save(self.root / f'stage-card-{name}.png')
        with self.assertRaises(FileNotFoundError):
            validate_stage_cards(self.root)

    def test_score_label_corruption_rejected(self):
        self.stage_cards()
        with Image.open(self.before) as image:
            image.putpixel((40, 100), (255, 255, 255))
            image.save(self.root / 'stage-selector-after-2.png')
        with self.assertRaisesRegex(ValueError, 'stage-selector'):
            validate_stage_cards(self.root)

    def test_variable_score_digits_allowed(self):
        self.stage_cards()
        with Image.open(self.before) as image:
            image.putpixel((80, 100), (255, 255, 255))
            image.save(self.root / 'stage-selector-after-1.png')
        validate_stage_cards(self.root)

    def test_stage_card_variable_score_excluded(self):
        self.stage_cards()
        with Image.open(self.before) as image:
            image.putpixel((80, 100), (255, 255, 255))
            image.save(self.root / 'stage-card-after-1.png')
        validate_stage_cards(self.root)

    def test_missing_level_rejected(self):
        Image.new("RGB", (160, 144), "white").save(self.after)
        with self.assertRaisesRegex(ValueError, "rendering changed"):
            compare_images(self.before, self.after, (0, 32, 160, 128))

    def test_lost_colour_rejected(self):
        with Image.open(self.before) as image:
            image.convert("L").save(self.after)
        with self.assertRaisesRegex(ValueError, "rendering changed"):
            compare_images(self.before, self.after, (0, 32, 160, 128))

    def test_corrupted_title_version_footer_rejected(self):
        with Image.open(self.before) as image:
            image.putpixel((45, 140), (128, 128, 128))
            image.save(self.after)
        with self.assertRaisesRegex(ValueError, "rendering changed"):
            compare_images(self.before, self.after, (0, 112, 160, 144))

    def test_incomplete_route_rejected(self):
        (self.root / "route.txt").write_text("ok 1 1 1\n")
        with self.assertRaisesRegex(ValueError, "two complete"):
            validate(self.root)

    def test_ceiling_overlap_rejected(self):
        mask = self.root / "mask.png"
        m = Image.new("L", (160, 144))
        m.paste(255, (40, 0, 120, 16)); m.save(mask)
        check_ceiling(self.before, self.before, mask)
        with Image.open(self.before) as image:
            image.putpixel((80, 8), (255, 0, 0)); image.save(self.after)
        with self.assertRaisesRegex(ValueError, "ceiling"):
            check_ceiling(self.after, self.before, mask)

    def test_empty_ceiling_mask_rejected(self):
        mask = self.root / "mask.png"
        Image.new("L", (160, 144)).save(mask)
        with self.assertRaisesRegex(ValueError, "empty ceiling"):
            check_ceiling(self.before, self.before, mask)


if __name__ == "__main__":
    unittest.main()
