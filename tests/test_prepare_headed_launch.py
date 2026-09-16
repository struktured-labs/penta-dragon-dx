#!/usr/bin/env python3
"""Non-emulator tests for headed ROM selection and provenance."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = PROJECT_ROOT / "scripts/prepare_headed_launch.py"
SPEC = importlib.util.spec_from_file_location(
    "prepare_headed_launch_under_test", HELPER_PATH
)
assert SPEC is not None and SPEC.loader is not None
HELPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HELPER
SPEC.loader.exec_module(HELPER)


class HeadedLaunchProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch_root = PROJECT_ROOT / "tmp"
        scratch_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="headed-launch-unit-", dir=scratch_root
        )
        self.root = Path(self.temporary.name).resolve()
        (self.root / "candidate").mkdir()
        (self.root / "rom/working").mkdir(parents=True)
        (self.root / "scripts").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_candidate(self, content: bytes = b"verified candidate") -> Path:
        candidate = self.root / "candidate/pinned.gb"
        candidate.write_bytes(content)
        return candidate

    def test_explicit_rom_writes_bound_durable_receipt(self) -> None:
        candidate = self.write_candidate()
        prepared = HELPER.prepare_launch(self.root, str(candidate))

        self.assertEqual(prepared.rom_path, candidate.resolve())
        self.assertTrue(prepared.receipt_path.is_file())
        self.assertEqual(
            prepared.receipt_path.parent,
            self.root / HELPER.RECEIPT_RELATIVE_ROOT,
        )
        receipt = json.loads(prepared.receipt_path.read_text())
        self.assertEqual(receipt["schema"], HELPER.RECEIPT_SCHEMA)
        self.assertEqual(receipt["rom"]["resolved_path"], str(candidate.resolve()))
        self.assertEqual(receipt["rom"]["sha256"], prepared.rom_sha256)
        self.assertNotIn("gate", receipt)
        self.assertEqual(prepared.receipt_path.stat().st_mode & 0o777, 0o600)

    def test_explicit_rom_is_selected_without_a_candidate_pin(self) -> None:
        selected = self.root / "rom/working/stream.gb"
        selected.write_bytes(b"explicit stream build")
        prepared = HELPER.prepare_launch(self.root, str(selected))
        self.assertEqual(prepared.rom_path, selected.resolve())

    def test_current_project_stop_gate_is_absent(self) -> None:
        self.assertFalse((PROJECT_ROOT / ".codex/hooks.json").exists())
        self.assertFalse((PROJECT_ROOT / ".codex/stage1-ready-gate.json").exists())

    def test_stale_gate_file_does_not_override_explicit_selection(self) -> None:
        selected = self.write_candidate()
        (self.root / ".codex").mkdir()
        (self.root / ".codex/stage1-ready-gate.json").write_text("{}\n")
        prepared = HELPER.prepare_launch(self.root, str(selected))
        self.assertEqual(prepared.rom_path, selected.resolve())

    def test_explicit_rom_receipt_records_current_hash(self) -> None:
        candidate = self.write_candidate()
        candidate.write_bytes(b"current explicit bytes")
        prepared = HELPER.prepare_launch(self.root, str(candidate))
        self.assertEqual(
            prepared.rom_sha256,
            hashlib.sha256(b"current explicit bytes").hexdigest(),
        )

    def test_no_arg_has_no_generic_fallback_without_active_gate(self) -> None:
        with self.assertRaisesRegex(
            HELPER.LaunchPreparationError, "pass the intended ROM explicitly"
        ):
            HELPER.prepare_launch(self.root, None)

    def test_missing_explicit_rom_is_blocked(self) -> None:
        with self.assertRaisesRegex(
            HELPER.LaunchPreparationError, "selected ROM cannot be resolved"
        ):
            HELPER.prepare_launch(self.root, "candidate/missing.gb")

    def test_second_rom_like_positional_argument_is_blocked(self) -> None:
        candidate = self.write_candidate()
        with self.assertRaisesRegex(
            HELPER.LaunchPreparationError, "extra ROM-like positional argument"
        ):
            HELPER.prepare_launch(
                self.root,
                str(candidate),
                ["--script", "probe.lua", "penta_dragon_dx_rc11.gbc"],
            )

    def test_launcher_has_no_silent_rom_default_and_prepares_before_exec(self) -> None:
        launcher = (PROJECT_ROOT / "scripts/launch_mgba.sh").read_text()
        self.assertNotIn("penta_dragon_dx_FIXED", launcher)
        prepare_index = launcher.index("scripts/prepare_headed_launch.py")
        exec_index = launcher.index('exec "$GUARDED_MGBA"')
        self.assertLess(prepare_index, exec_index)
        self.assertNotRegex(
            launcher,
            r"(?m)^[ \t]*(?:exec[ \t]+)?(?:[^ \t=]*/)?"
            r"mgba(?:-qt|-headless)?\b",
        )


if __name__ == "__main__":
    unittest.main()
