#!/usr/bin/env python3
"""Offline mutation controls for the Stage-1 OBJ visual contract."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_obj_visual_contract as obj  # noqa: E402


PRIMARY_HEX = (
    "0000007c005800300000e003c00100000000be2e1f51420800001f0017000f00"
    "0000ff03df0000000000a0026001000000001f7c0f4c00000000e07fc03c0000"
    "00001f600f40000000001f00bf0000000000bf0c59080f040000947f8a664049"
    "0000b4704f58083c0000c80bc406c00100001f0f580a50010000ff7fd65a8c31"
    "0607060706070607"
)
VARIANT_HEX = (
    "00001f7c175810300000e07fc04e802d0000e07fc05e803e0000ff03bf029f01"
    "0000ff00bf005f00"
)


class Stage1ObjVisualContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="stage1-obj-visual-offline-", dir=ROOT / "tmp"
        )
        self.root = Path(self.temporary.name)
        stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
        candidate = bytearray(obj.ROM_SIZE)
        candidate[0x134:0x144] = obj.gbas_payload(obj.OPERATOR_CAPTURE)[0x10:0x20]
        candidate[0x143] = 0xC0
        candidate[
            obj.SARA_OBJ_SOURCE_OFFSET:
            obj.SARA_OBJ_SOURCE_OFFSET + obj.SARA_OBJ_SOURCE_SIZE
        ] = stock[
            obj.SARA_OBJ_SOURCE_OFFSET:
            obj.SARA_OBJ_SOURCE_OFFSET + obj.SARA_OBJ_SOURCE_SIZE
        ]
        candidate[
            obj.GARGOYLE_OBJ_SOURCE_OFFSET:
            obj.GARGOYLE_OBJ_SOURCE_OFFSET + obj.GARGOYLE_OBJ_SOURCE_SIZE
        ] = stock[
            obj.GARGOYLE_OBJ_SOURCE_OFFSET:
            obj.GARGOYLE_OBJ_SOURCE_OFFSET + obj.GARGOYLE_OBJ_SOURCE_SIZE
        ]
        candidate[
            obj.OBJ_PRIMARY_OFFSET:
            obj.OBJ_PRIMARY_OFFSET + obj.OBJ_PRIMARY_SIZE
        ] = bytes.fromhex(PRIMARY_HEX)
        candidate[
            obj.OBJ_VARIANT_OFFSET:
            obj.OBJ_VARIANT_OFFSET + obj.OBJ_VARIANT_SIZE
        ] = bytes.fromhex(VARIANT_HEX)
        self.candidate = self.root / "candidate.gb"
        self.candidate.write_bytes(candidate)

        contract = obj.candidate_contract(bytes(candidate))
        self.expected_cram = obj.expected_obj_cram(
            contract, ffbf=1, ffc0=0, ffd0=0
        )
        self.sara_pattern = stock[0x20280:0x20290]
        self.sara_lower_pattern = stock[0x20290:0x202A0]
        self.boss_pattern = stock[0x24100:0x24110]
        self.boss_lower_pattern = stock[0x24110:0x24120]
        self.fixed_upper_pattern = stock[0x201C0:0x201D0]
        self.fixed_pattern = stock[0x201D0:0x201E0]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_identity_retarget_preserves_all_machine_memory(self) -> None:
        state = self.root / "identity.ss0"
        receipt = obj.retarget_operator_state(obj.OPERATOR_CAPTURE, state, self.candidate)
        self.assertEqual(set(receipt["changed_gbAs_offsets"]) - {4, 5, 6, 7}, {0x1F})
        before = obj.gbas_payload(obj.OPERATOR_CAPTURE)
        after = obj.gbas_payload(state)
        self.assertEqual(before[0x20:], after[0x20:])
        self.assertEqual(after[0x10:0x20], self.candidate.read_bytes()[0x134:0x144])

    def test_identity_retarget_rejects_other_game(self) -> None:
        candidate = bytearray(self.candidate.read_bytes())
        candidate[0x134] ^= 1
        self.candidate.write_bytes(candidate)
        with self.assertRaisesRegex(ValueError, "title bytes"):
            obj.retarget_operator_state(obj.OPERATOR_CAPTURE, self.root / "wrong.ss0", self.candidate)

    def valid_rows(self) -> list[dict]:
        phases: list[tuple[str, list[int]]] = [
            ("baseline", [0] * 12),
            ("menu_entry", [0, 1]),
            ("menu_hold", [1] * 60),
            ("menu_exit", [1, 0]),
            ("post_close", [0] * 60),
        ]
        rows = []
        sample = frame = 0
        for phase, owned_values in phases:
            for phase_frame, owned in enumerate(owned_values, 1):
                sample += 1
                frame += 1
                rows.append({
                    "sample": sample,
                    "frame": frame,
                    "phase": phase,
                    "phase_frame": phase_frame,
                    "scene": 0x0B,
                    "active": 1,
                    "room": 7,
                    "menu_owned": owned,
                    "ffe4": owned,
                    "lcdc": 0xE3 if owned else 0x8B,
                    "ffbe": 0,
                    "ffbf": 1,
                    "ffc0": 0,
                    "ffd0": 0,
                    "df04": 0,
                    "obj_cram": self.expected_cram,
                    "visible_oam": [
                        {
                            "slot": 0, "y": 80, "x": 80,
                            "tile": 0x28, "attr": 0x02,
                            "patterns": self.sara_pattern,
                        },
                        {
                            "slot": 4, "y": 40, "x": 105,
                            "tile": 0x40, "attr": 0x06,
                            "patterns": self.boss_pattern,
                        },
                        {
                            "slot": 31, "y": 120, "x": 12,
                            "tile": 0x1D, "attr": 0x04,
                            "patterns": self.fixed_pattern,
                        },
                    ],
                })
        return rows

    def write_trace(self, rows: list[dict], name: str = "trace.tsv") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [obj.TRACE_HEADER]
        for row in rows:
            oam = ";".join(
                f"{item['slot']},{item['y']},{item['x']},"
                f"{item['tile']},{item['attr']},{item['patterns'].hex()}"
                for item in row["visible_oam"]
            )
            lines.append("\t".join(map(str, (
                row["sample"], row["frame"], row["phase"],
                row["phase_frame"], row["scene"], row["active"],
                row["room"], row["menu_owned"], row["ffe4"], row["lcdc"],
                row["ffbe"], row["ffbf"], row["ffc0"], row["ffd0"],
                row["df04"], row["obj_cram"].hex(), oam,
            ))))
        path.write_text("\n".join(lines) + "\n")
        return path

    def bind(self, rows: list[dict], name: str = "trace.tsv") -> dict:
        return obj.bind_trace(self.candidate, self.write_trace(rows, name))

    def make_live_receipt(self, name: str = "live") -> Path:
        output = self.root / name
        runtime = output / "runtime"
        runtime.mkdir(parents=True)
        runtime_rom = runtime / "candidate.gb"
        runtime_rom.write_bytes(self.candidate.read_bytes())
        runtime_state = runtime / "operator.ss0"
        retarget = obj.retarget_operator_state(
            obj.OPERATOR_CAPTURE, runtime_state, runtime_rom
        )
        prefix = output / "stage1-obj"
        startup = Path(str(prefix) + ".startup")
        core_ready = Path(str(prefix) + ".core-ready")
        report_path = Path(str(prefix) + ".report")
        done = Path(str(prefix) + ".done")
        trace = Path(str(prefix) + ".trace.tsv")
        launch_path = output / "launch-contract.json"
        log = output / "emulator.log"
        token = "ab" * 32
        launch_started = time.time_ns()

        rows = self.valid_rows()
        self.write_trace(rows, f"{name}/stage1-obj.trace.tsv")
        core = obj.bind_trace(runtime_rom, trace)
        startup.write_text(f"startup_token={token}\n")
        core_ready.write_text(f"startup_token={token}\n")
        done.write_text(f"status=ok\nstartup_token={token}\n")
        report_lines = [
            "status=ok", "reason=complete", f"startup_token={token}",
            f"frames={rows[-1]['frame']}", f"samples={core['samples']}",
            "menu_open_events=1", "menu_close_events=1",
            "obj_cram_domain_samples=0",
            f"obj_cram_index_samples={core['samples']}",
            "obj_cram_restore_failures=0",
        ]
        report_lines.extend(
            f"samples_{phase}={core['phase_samples'][phase]}"
            for phase in obj.PHASE_ORDER
        )
        report_path.write_text("\n".join(report_lines) + "\n")
        log.write_text("synthetic offline receipt fixture; no emulator\n")

        tools = obj.verify_probe_source()
        probe_environment = {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "PENTA_STAGE1_OBJ_OUT": str(prefix),
            "PENTA_STAGE1_OBJ_STATE": str(runtime_state),
            "PENTA_STAGE1_OBJ_FRAME_LIMIT": str(obj.FRAME_LIMIT),
            "PENTA_STAGE1_OBJ_BASELINE_FRAMES": str(
                obj.PHASE_MINIMUMS["baseline"]
            ),
            "PENTA_STAGE1_OBJ_MENU_HOLD_FRAMES": str(
                obj.PHASE_MINIMUMS["menu_hold"]
            ),
            "PENTA_STAGE1_OBJ_POST_CLOSE_FRAMES": str(
                obj.PHASE_MINIMUMS["post_close"]
            ),
        }
        launch = {
            "schema": "penta-stage1-obj-visual-launch-v1",
            "command": [
                str(obj.LAUNCHER), "--fastforward",
                "-C", f"savegamePath={runtime}",
                "-C", f"savestatePath={runtime}",
                "--script", str(obj.PROBE), str(runtime_rom),
            ],
            "cwd": str(output),
            "candidate": str(runtime_rom),
            "candidate_sha256": obj.sha256(runtime_rom),
            "source_candidate": str(self.candidate.resolve()),
            "source_candidate_sha256": obj.sha256(self.candidate),
            "startup_token_sha256": obj.sha256_bytes(token.encode()),
            "launch_started_at_ns": launch_started,
            "frame_limit": obj.FRAME_LIMIT,
            "timeout_seconds": obj.RUN_TIMEOUT_SECONDS,
            "retarget": retarget,
            "tool_identity": tools,
            "probe_environment": probe_environment,
        }
        launch_path.write_text(json.dumps(launch, sort_keys=True) + "\n")
        core.update({
            "source_candidate": str(self.candidate.resolve()),
            "source_candidate_sha256": obj.sha256(self.candidate),
            "runtime_candidate": str(runtime_rom),
            "runtime_candidate_sha256": obj.sha256(runtime_rom),
            "operator_state": retarget,
            "startup_marker": str(startup),
            "startup_marker_sha256": obj.sha256(startup),
            "core_ready_marker": str(core_ready),
            "core_ready_marker_sha256": obj.sha256(core_ready),
            "producer_report": str(report_path),
            "producer_report_sha256": obj.sha256(report_path),
            "completion_marker": str(done),
            "completion_marker_sha256": obj.sha256(done),
            "launch_contract": str(launch_path),
            "launch_contract_sha256": obj.sha256(launch_path),
            "emulator_log": str(log),
            "emulator_log_sha256": obj.sha256(log),
            "tool_identity": tools,
            "controlled_teardown": {
                "exact_child_terminated": False,
                "termination_method": "already-exited",
                "return_code": 0,
            },
            "launch_started_at_ns": launch_started,
            "bound_at_ns": time.time_ns(),
        })
        receipt = output / "stage1-obj-visual.receipt.json"
        receipt.write_text(json.dumps(core, indent=2, sort_keys=True) + "\n")
        return receipt

    def test_exact_hardware_obj_contract_passes(self) -> None:
        receipt = self.bind(self.valid_rows())
        self.assertEqual(receipt["status"], "pass")
        self.assertEqual(receipt["obj_cram_mismatch_frames"], 0)
        self.assertEqual(receipt["oam_palette_mismatches"], 0)
        self.assertEqual(receipt["obj_bank1_entries"], 0)
        self.assertEqual(receipt["obj_pattern_mismatches"], 0)
        self.assertEqual(receipt["obj_loader_source_pattern_mismatches"], 0)
        self.assertEqual(
            receipt["referenced_obj_loader_source_patterns"],
            receipt["referenced_obj_patterns"],
        )
        self.assertGreater(receipt["sara_oam_entries"], 0)
        self.assertGreater(receipt["gargoyle_oam_entries"], 0)
        self.assertTrue(all(receipt["checks"].values()))

    def test_stable_wrong_obj_cram_cannot_pass(self) -> None:
        rows = self.valid_rows()
        for row in rows:
            bad = bytearray(row["obj_cram"])
            bad[6] ^= 0x20
            row["obj_cram"] = bytes(bad)
        with self.assertRaisesRegex(obj.ObjVisualError, "OBJ CRAM differs"):
            self.bind(rows, "wrong-cram.tsv")

    def test_wrong_semantic_oam_palette_cannot_pass(self) -> None:
        rows = self.valid_rows()
        for row in rows:
            row["visible_oam"][1]["attr"] = 5
        with self.assertRaisesRegex(
            obj.ObjVisualError, "semantic palette mismatches"
        ):
            self.bind(rows, "wrong-palette.tsv")

    def test_sara_floor_through_priority_cannot_pass(self) -> None:
        rows = self.valid_rows()
        for row in rows:
            row["visible_oam"][0]["attr"] |= 0x80
        with self.assertRaisesRegex(
            obj.ObjVisualError, "floor-through priority bit 7"
        ):
            self.bind(rows, "sara-floor-through.tsv")

    def test_obj_bank_one_selection_cannot_pass(self) -> None:
        rows = self.valid_rows()
        for row in rows:
            row["visible_oam"][0]["attr"] |= 0x08
        with self.assertRaisesRegex(obj.ObjVisualError, "selected OBJ bank 1"):
            self.bind(rows, "bank1.tsv")

    def test_noncanonical_referenced_chr_cannot_pass(self) -> None:
        rows = self.valid_rows()
        for row in rows:
            row["visible_oam"][1]["patterns"] = bytes.fromhex("A5" * 16)
        with self.assertRaisesRegex(
            obj.ObjVisualError, "wrong physical tile-ID CHR patterns"
        ):
            self.bind(rows, "wrong-chr.tsv")

    def test_swapped_valid_stock_pattern_cannot_pass(self) -> None:
        rows = self.valid_rows()
        for row in rows:
            # Tile $41 is a valid Gargoyle chunk from the same pinned source,
            # but it is not the reviewed physical destination for tile ID $40.
            row["visible_oam"][1]["patterns"] = self.boss_lower_pattern
        with self.assertRaisesRegex(
            obj.ObjVisualError, "wrong physical tile-ID CHR patterns"
        ):
            self.bind(rows, "swapped-valid-stock-chr.tsv")

    def test_candidate_cannot_self_bless_mutated_obj_art(self) -> None:
        candidate = bytearray(self.candidate.read_bytes())
        candidate[obj.obj_loader_source_offset(0x28)] ^= 0x01
        self.candidate.write_bytes(candidate)
        with self.assertRaisesRegex(
            obj.ObjVisualError, "candidate OBJ loader-source patterns"
        ):
            self.bind(self.valid_rows(), "self-blessed-art.tsv")

    def test_unused_obj_art_mutation_does_not_overconstrain_route(self) -> None:
        candidate = bytearray(self.candidate.read_bytes())
        candidate[obj.obj_loader_source_offset(0x10)] ^= 0x01
        self.candidate.write_bytes(candidate)
        receipt = self.bind(self.valid_rows(), "unused-art.tsv")
        self.assertEqual(receipt["obj_loader_source_pattern_mismatches"], 0)

    def test_missing_menu_hold_coverage_cannot_pass(self) -> None:
        rows = [
            row for row in self.valid_rows()
            if row["phase"] != "menu_hold" or row["phase_frame"] <= 8
        ]
        for sample, row in enumerate(rows, 1):
            row["sample"] = sample
        with self.assertRaisesRegex(obj.ObjVisualError, "menu_hold samples"):
            self.bind(rows, "short-hold.tsv")

    def test_8x16_objects_bind_both_referenced_patterns(self) -> None:
        rows = self.valid_rows()
        for row in rows:
            row["lcdc"] |= 0x04
            row["visible_oam"][0]["patterns"] = (
                self.sara_pattern + self.sara_lower_pattern
            )
            row["visible_oam"][1]["patterns"] = (
                self.boss_pattern + self.boss_lower_pattern
            )
            row["visible_oam"][2]["patterns"] = (
                self.fixed_upper_pattern + self.fixed_pattern
            )
        receipt = self.bind(rows, "8x16.tsv")
        self.assertEqual(
            receipt["referenced_obj_patterns"],
            receipt["visible_oam_entries"] * 2,
        )

    def test_semantic_policy_covers_boss_sara_and_fixed_slot(self) -> None:
        contract = obj.candidate_contract(self.candidate.read_bytes())
        self.assertEqual(obj.expected_oam_palette(
            contract, slot=0, tile=0x28, ffbe=0, ffbf=0
        ), 2)
        self.assertEqual(obj.expected_oam_palette(
            contract, slot=0, tile=0x28, ffbe=1, ffbf=0
        ), 1)
        self.assertEqual(obj.expected_oam_palette(
            contract, slot=4, tile=0x40, ffbe=0, ffbf=1
        ), 6)
        self.assertEqual(obj.expected_oam_palette(
            contract, slot=31, tile=0x1D, ffbe=0, ffbf=1
        ), 4)

    def test_strict_live_receipt_revalidates_offline(self) -> None:
        receipt = self.make_live_receipt("strict-pass")
        result = obj.validate_live_receipt(receipt, self.candidate)
        self.assertTrue(result["offline_revalidated"])
        self.assertEqual(result["receipt_sha256"], obj.sha256(receipt))

    def test_live_receipt_rejects_extra_schema_field(self) -> None:
        receipt = self.make_live_receipt("strict-extra-key")
        value = json.loads(receipt.read_text())
        value["unreviewed_claim"] = True
        receipt.write_text(json.dumps(value, sort_keys=True) + "\n")
        with self.assertRaisesRegex(obj.ObjVisualError, "fields changed"):
            obj.validate_live_receipt(receipt, self.candidate)

    def test_live_receipt_rejects_swapped_valid_pattern_even_if_rehashed(self) -> None:
        receipt = self.make_live_receipt("strict-swapped-pattern")
        value = json.loads(receipt.read_text())
        trace = Path(value["trace"])
        original = self.boss_pattern.hex()
        swapped = self.boss_lower_pattern.hex()
        text = trace.read_text()
        self.assertIn(original, text)
        trace.write_text(text.replace(original, swapped, 1))
        value["trace_sha256"] = obj.sha256(trace)
        receipt.write_text(json.dumps(value, sort_keys=True) + "\n")
        with self.assertRaisesRegex(
            obj.ObjVisualError, "wrong physical tile-ID CHR patterns"
        ):
            obj.validate_live_receipt(receipt, self.candidate)

    def test_live_receipt_rejects_cross_run_token_even_if_rehashed(self) -> None:
        receipt = self.make_live_receipt("strict-token")
        value = json.loads(receipt.read_text())
        marker = Path(value["core_ready_marker"])
        marker.write_text(f"startup_token={'cd' * 32}\n")
        value["core_ready_marker_sha256"] = obj.sha256(marker)
        receipt.write_text(json.dumps(value, sort_keys=True) + "\n")
        with self.assertRaisesRegex(obj.ObjVisualError, "token binding differs"):
            obj.validate_live_receipt(receipt, self.candidate)

    def test_live_receipt_rejects_another_candidate(self) -> None:
        receipt = self.make_live_receipt("strict-candidate")
        other = self.root / "other.gb"
        payload = bytearray(self.candidate.read_bytes())
        payload[0x1234] ^= 1
        other.write_bytes(payload)
        with self.assertRaisesRegex(obj.ObjVisualError, "another source candidate"):
            obj.validate_live_receipt(receipt, other)

    def test_evidence_output_must_be_below_project_scratch(self) -> None:
        with self.assertRaisesRegex(
            obj.ObjVisualError, "below repo tmp/ or /mnt/data/tmp/"
        ):
            obj.scratch_descendant(ROOT / "outside-scratch", "test output")

    def test_probe_has_restored_index_only_and_singleflight_has_no_override(self) -> None:
        identity = obj.verify_probe_source()
        self.assertTrue(identity["raw_vram_bank0_only"])
        self.assertFalse(identity["obj_cram_data_writes"])
        self.assertEqual(identity["obj_cram_index_write_sites"], 2)
        self.assertTrue(identity["obj_cram_index_restored"])
        self.assertFalse(identity["emulator_override"])
        probe = obj.PROBE.read_text()
        self.assertEqual(probe.count("emu:write8("), 2)
        self.assertNotIn("emu:write8(0xFF6B", probe)
        verifier = Path(obj.__file__).read_text()
        self.assertIn('str(LAUNCHER), "--fastforward"', verifier)
        self.assertNotIn('parser.add_argument("--mgba"', verifier)


if __name__ == "__main__":
    unittest.main()
