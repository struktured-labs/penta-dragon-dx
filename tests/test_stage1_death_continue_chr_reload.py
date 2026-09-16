#!/usr/bin/env python3
"""Offline controls for the natural Stage-1 death/Continue CHR gate."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
if str(DIAGNOSTICS) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_death_continue_chr_reload as gate  # noqa: E402


class DeathContinueChrReloadTests(unittest.TestCase):
    def test_probe_has_one_memory_stimulus_and_neutral_input(self) -> None:
        source = gate.PROBE.read_text()
        contract = gate.audit_probe_source(source)
        self.assertEqual(contract["gameplay_memory_writes"], 1)
        self.assertEqual(contract["gameplay_memory_write"], "$DCBB=00")
        self.assertEqual(source.count("emu:write8("), 1)
        self.assertIn("emu:write8(0xDCBB, 0)", source)

        extra_write = source.replace(
            "emu:write8(0xDCBB, 0)",
            "emu:write8(0xDCBB, 0)\n    emu:write8(0xFF94, 1)",
        )
        with self.assertRaises(gate.GateError):
            gate.audit_probe_source(extra_write)

        active_keys = source.replace("emu:setKeys(0)", "emu:setKeys(1)", 1)
        with self.assertRaises(gate.GateError):
            gate.audit_probe_source(active_keys)

    def test_verifier_has_no_emulator_override_surface(self) -> None:
        source = gate.SELF.read_text()
        generator = gate.STATE_GENERATOR.read_text()
        self.assertNotRegex(source, r"add_argument\([^\n]*--mgba")
        self.assertNotRegex(generator, r"add_argument\([^\n]*--mgba")
        self.assertIn('"PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"', source)
        self.assertIn("environment.pop(name, None)", source)
        self.assertIn('LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"', source)
        self.assertIn('MGBA = ROOT / "scripts/mgba-qt-singleflight"', generator)

    def test_exact_candidate_preimages_and_mutations(self) -> None:
        payload = bytearray((ROOT / "rom/Penta Dragon (J).gb").read_bytes())
        payload.extend(bytes(512 * 1024 - len(payload)))
        payload[0x0143] = gate.CGB_ONLY_FLAG
        synthetic_pages = {
            0x9000 + index * 0x100: bytes([index]) * 0x100
            for index in range(8)
        }
        with mock.patch.object(
            gate.chr_contract, "canonical_pages", return_value=synthetic_pages
        ):
            contract = gate.validate_candidate_contract(bytes(payload))
        self.assertEqual(contract["continue_route"], "bank1:$4AF2-$4B08 exact")

        bad_route = bytearray(payload)
        bad_route[0x4AFB] ^= 0x01
        with mock.patch.object(
            gate.chr_contract, "canonical_pages", return_value=synthetic_pages
        ), self.assertRaises(gate.GateError):
            gate.validate_candidate_contract(bytes(bad_route))

        bad_loader = bytearray(payload)
        bad_loader[0x0C9C] ^= 0x01
        with self.assertRaises(ValueError):
            gate.validate_candidate_contract(bytes(bad_loader))

        bad_header = bytearray(payload)
        bad_header[0x0143] = 0x80
        with mock.patch.object(
            gate.chr_contract, "canonical_pages", return_value=synthetic_pages
        ), self.assertRaises(gate.GateError):
            gate.validate_candidate_contract(bytes(bad_header))

    def test_good_synthetic_transaction_passes(self) -> None:
        evidence = gate.synthetic_good_evidence()
        result = gate.grade_reload_evidence(**evidence)
        self.assertTrue(result["passed"], result["checks"])
        self.assertEqual(result["counts"]["loader_writes"], 0x800)

    def test_all_embedded_mutation_controls_reject(self) -> None:
        controls = gate.mutation_controls()
        self.assertTrue(all(controls.values()), controls)
        self.assertGreaterEqual(len(controls), 12)

    def test_wrong_pc_and_wrong_hl_are_independently_rejected(self) -> None:
        for field, value in (("pc", 0x0D48), ("hl", 0x5002)):
            with self.subTest(field=field):
                evidence = copy.deepcopy(gate.synthetic_good_evidence())
                evidence["chr_rows"][0][field] = value
                result = gate.grade_reload_evidence(**evidence)
                self.assertFalse(result["passed"])
                self.assertFalse(result["checks"][
                    "exactly 0x800 ordered bank7 canonical writes have stock ownership"
                ])

    def test_missing_and_duplicate_loader_writes_are_rejected(self) -> None:
        for mutation in ("missing", "duplicate"):
            with self.subTest(mutation=mutation):
                evidence = copy.deepcopy(gate.synthetic_good_evidence())
                if mutation == "missing":
                    evidence["chr_rows"].pop()
                    evidence["report"]["chr_event_count"] = "2047"
                    evidence["report"]["loader_write_count"] = "2047"
                else:
                    evidence["chr_rows"].append(
                        copy.deepcopy(evidence["chr_rows"][-1])
                    )
                    evidence["report"]["chr_event_count"] = "2049"
                    evidence["report"]["loader_write_count"] = "2049"
                self.assertFalse(gate.grade_reload_evidence(**evidence)["passed"])


if __name__ == "__main__":
    unittest.main()
