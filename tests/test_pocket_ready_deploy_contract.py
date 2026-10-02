#!/usr/bin/env python3
"""Offline mutation tests for the Stage-1 READY -> Pocket handoff."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "diagnostics"))

import deploy_pocket_rom as deploy  # noqa: E402
import verify_stage1_reported_regressions_ready as ready  # noqa: E402


class PocketReadyDeployContractTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="pocket-ready-contract-", dir=ROOT / "tmp",
        )
        self.output = Path(self.temporary.name).resolve()
        self.rom = self.output / "candidate.gbc"
        self.rom.write_bytes(b"offline-pocket-ready-contract-candidate")
        self.rom_sha256 = deploy.sha256(self.rom)
        self.receipt = self.output / "receipt.json"
        self.payload = self.make_payload()
        self.write_payload(self.payload)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_payload(self) -> dict:
        gates = {}
        for name in sorted(deploy.HARDWARE_TEST_READY_COMMAND_GATES):
            gate_root = self.output / name
            gate_root.mkdir()
            nested_receipt = gate_root / "receipt.json"
            log = gate_root / "driver.log"
            nested_receipt.write_text(json.dumps({"gate": name}) + "\n")
            log.write_text(f"offline evidence for {name}\n")
            gates[name] = {
                "status": deploy.HARDWARE_TEST_READY_GATE_STATUSES[name],
                "exit_status": 0,
                "rom_sha256": self.rom_sha256,
                "receipt": str(nested_receipt.resolve()),
                "receipt_sha256": deploy.sha256(nested_receipt),
                "log": str(log.resolve()),
                "log_sha256": deploy.sha256(log),
            }

        tool_identity = {
            name: {
                "path": str(path.resolve(strict=True)),
                "sha256": deploy.sha256(path),
            }
            for name, path in deploy.hardware_test_ready_tool_paths().items()
        }
        gates["tool_identity_reverification"] = {
            "status": "PASS",
            "all_tool_hashes_unchanged": True,
            "tool_identity": copy.deepcopy(tool_identity),
        }
        issue_coverage = ready.reported_issue_coverage(gates)
        return {
            "schema": deploy.HARDWARE_TEST_READY_SCHEMA,
            "status": "READY",
            "candidate": str(self.rom.resolve()),
            "candidate_sha256": self.rom_sha256,
            "output": str(self.output),
            "gates": gates,
            "reported_issue_coverage": issue_coverage,
            "failures": [],
            "tool_identity": tool_identity,
        }

    def write_payload(self, payload: dict) -> None:
        self.receipt.write_text(json.dumps(payload, indent=2) + "\n")

    def validate(self) -> dict[str, object]:
        return deploy.require_hardware_test_ready_receipt(
            self.receipt,
            self.rom.resolve(),
            self.rom_sha256,
            now_timestamp=self.receipt.stat().st_mtime + 1.0,
        )

    def assert_refused(self, payload: dict, pattern: str) -> None:
        self.write_payload(payload)
        with self.assertRaisesRegex(SystemExit, pattern):
            self.validate()

    def test_contract_inventories_match_current_producer(self) -> None:
        self.assertEqual(ready.SCHEMA, deploy.HARDWARE_TEST_READY_SCHEMA)
        self.assertEqual(
            ready.SCHEMA, "penta-stage1-reported-regressions-ready-v10",
        )
        self.assertEqual(len(deploy.HARDWARE_TEST_READY_GATES), 17)
        self.assertIn(
            "stage1_tilemap_publication_oracle",
            deploy.HARDWARE_TEST_READY_GATES,
        )
        self.assertIn(
            "rendered_continuity_operator_capture_fixture",
            ready.tool_identity(),
        )
        self.assertIn(
            "stage1_current_pickup_state",
            deploy.HARDWARE_TEST_READY_GATES,
        )
        self.assertIn(
            "stage1_current_pickup_host_palettes",
            deploy.HARDWARE_TEST_READY_GATES,
        )
        self.assertIn(
            "native_select_menu_window_exact",
            deploy.HARDWARE_TEST_READY_GATES,
        )
        self.assertIn(
            "natural_stage1_pickup_temporal_raster",
            deploy.HARDWARE_TEST_READY_GATES,
        )
        tree = ast.parse(Path(ready.__file__).read_text())
        producer_gates = {
            node.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "current_gate"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and node.value.value != "preflight"
        }
        self.assertEqual(producer_gates, deploy.HARDWARE_TEST_READY_GATES)
        ready_tools = ready.tool_identity()
        deploy_tools = deploy.hardware_test_ready_tool_paths()
        self.assertEqual(set(ready_tools), set(deploy_tools))
        self.assertEqual(
            {
                name: Path(item["path"]).resolve()
                for name, item in ready_tools.items()
            },
            {name: path.resolve() for name, path in deploy_tools.items()},
        )

    def test_pickup_commands_are_fixed_to_the_release_candidate_tools(self) -> None:
        source = Path(ready.__file__).read_text()
        pickup_state_block = source.split(
            'current_gate = "stage1_current_pickup_state"', 1
        )[1].split(
            'current_gate = "stage1_current_pickup_host_palettes"', 1
        )[0]
        pickup_host_block = source.split(
            'current_gate = "stage1_current_pickup_host_palettes"', 1
        )[1].split(
            'current_gate = "rom_owned_natural_hazard_state"', 1
        )[0]
        self.assertIn("str(PICKUP_STATE_GENERATOR)", pickup_state_block)
        self.assertIn('"--output", str(pickup_state_output)', pickup_state_block)
        self.assertIn("str(PICKUP_HOST_VERIFIER)", pickup_host_block)
        self.assertIn('"--state", str(pickup_state)', pickup_host_block)
        self.assertIn(
            '"--state-receipt", str(pickup_state_receipt)',
            pickup_host_block,
        )
        self.assertNotIn('"--mgba"', pickup_state_block + pickup_host_block)

    def test_shared_pickup_receipt_mutation_controls_pass_offline(self) -> None:
        self.assertEqual(ready.pickup_receipts.self_test(), 0)

    def test_exact_current_v10_receipt_is_accepted_offline(self) -> None:
        accepted = self.validate()
        self.assertEqual(accepted["schema"], ready.SCHEMA)
        self.assertEqual(accepted["candidate_sha256"], self.rom_sha256)
        self.assertNotIn("stop_gate_revalidation", accepted)

    def test_ready_acceptance_has_no_stop_hook_dependency(self) -> None:
        self.assertFalse(hasattr(deploy, "revalidate_ready_receipt_against_stop_gate"))
        self.assertNotIn("codex_stop_hook", deploy.hardware_test_ready_tool_paths())

    def test_v3_receipt_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        mutant["schema"] = "penta-stage1-reported-regressions-ready-v3"
        self.assert_refused(mutant, "schema is unsupported")

    def test_missing_pickup_gate_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        del mutant["gates"]["stage1_current_pickup_host_palettes"]
        self.assert_refused(mutant, "gate inventory is not exact")

    def test_failed_pickup_gate_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        mutant["gates"]["stage1_current_pickup_state"]["status"] = "FAIL"
        self.assert_refused(mutant, "gates are not PASS")

    def test_missing_reported_issue_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        del mutant["reported_issue_coverage"]["rotating_spike_flicker"]
        self.assert_refused(mutant, "coverage inventory is not exact")

    def test_reported_issue_without_assertions_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        mutant["reported_issue_coverage"][
            "sarah_adjacent_transient_object_or_room_tile"
        ]["assertions"] = []
        self.assert_refused(mutant, "coverage is malformed")

    def test_pickup_receipt_hash_mutation_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        mutant["gates"]["stage1_current_pickup_state"][
            "receipt_sha256"
        ] = "0" * 64
        self.assert_refused(mutant, "command evidence is stale or malformed")

    def test_changed_tool_inventory_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        del mutant["tool_identity"]["pickup_host_verifier"]
        mutant["gates"]["tool_identity_reverification"][
            "tool_identity"
        ] = copy.deepcopy(mutant["tool_identity"])
        self.assert_refused(mutant, "tool identity inventory is not exact")

    def test_final_tool_reverification_divergence_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        mutant["gates"]["tool_identity_reverification"][
            "all_tool_hashes_unchanged"
        ] = False
        self.assert_refused(mutant, "lacks exact final tool re-verification")

    def test_noncanonical_candidate_path_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.payload)
        mutant["candidate"] = str(self.output / "." / self.rom.name)
        # pathlib normalizes the simple '/./' form while constructing it, so
        # retain a deliberately noncanonical but equivalent spelling.
        mutant["candidate"] = str(self.output / "unused" / ".." / self.rom.name)
        self.assert_refused(mutant, "names another candidate path")


if __name__ == "__main__":
    unittest.main()
