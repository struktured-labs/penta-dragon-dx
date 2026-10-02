from __future__ import annotations

import inspect
import hashlib
import json
import copy
import tempfile
import os
from pathlib import Path
import sys
import time
import unittest
from unittest import mock
import zlib


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_scene0b_captured_menu_receipt as binder  # noqa: E402
import verify_stage1_scene0b_live_menu_roundtrip as live  # noqa: E402
import build_stage1_scene0b_runtime_selfheal_r313 as r313  # noqa: E402
import build_stage1_scene0b_publication_commit_r314 as r314  # noqa: E402
import build_stage1_row_gate_abi_speed_r318 as r318  # noqa: E402
import normalize_mgba_state_pc as state_normalizer  # noqa: E402
from stage1_hazard_art import (  # noqa: E402
    compile_stage1_hazard_terminal_variants,
    load_stage1_hazard_config,
)


def with_reviewed_terminal_art(candidate: bytes) -> bytes:
    """Retain the test revision's code while applying r343 cap art."""
    config = load_stage1_hazard_config()
    stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()
    variants = compile_stage1_hazard_terminal_variants(stock, config)
    result = bytearray(candidate)
    for tile, variant in variants.items():
        start = config.source_offset + tile * 16
        result[start:start + 16] = variant
    return bytes(result)


class Scene0BLiveVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(
            prefix="scene0b-live-offline-", dir=ROOT / "tmp"
        )
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def identity_candidate(
        self, source: Path, name: str = "candidate.gb",
        *, title_byte: int | None = None, flag: int = 0xC0,
    ) -> Path:
        state = binder.gbas_payload(source)
        identity = bytearray(state[0x10:0x20])
        if title_byte is not None:
            identity[0] = title_byte
        identity[15] = flag
        candidate = bytearray(0x200)
        candidate[0x134:0x144] = identity
        path = self.root / name
        path.write_bytes(candidate)
        return path

    def mutated_state(
        self, source: Path, name: str, offset: int, value: int,
    ) -> Path:
        chunks = state_normalizer.png_chunks(source.read_bytes())
        index = next(
            index for index, (kind, _) in enumerate(chunks)
            if kind == b"gbAs"
        )
        raw = bytearray(zlib.decompress(chunks[index][1]))
        raw[offset] = value
        chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
        path = self.root / name
        state_normalizer.write_png(path, chunks)
        return path

    def test_checked_probe_is_reviewed_native_and_observation_only(self) -> None:
        contract = live.audit_probe_source(live.PROBE.read_text())
        self.assertEqual(live.IMPLEMENTATION_STATUS, "IMPLEMENTED_REVIEWED")
        self.assertEqual(
            binder.live_producer_implementation_status(),
            binder.LIVE_IMPLEMENTATION_READY,
        )
        self.assertTrue(contract["native_select_only"])
        self.assertEqual(
            contract["select_input_policy"],
            "hold-until-native-menu-acknowledgement",
        )
        self.assertEqual(live.PROBE.read_text().count("keys = KEY_SELECT"), 2)
        self.assertEqual(contract["publication_latch"], "FF01")
        self.assertEqual(live.PROBE.read_text().count(
            "emu:read8(0xFF01)"
        ), 2)
        self.assertNotIn("emu:read8(0xFFA5)", live.PROBE.read_text())
        self.assertEqual(contract["gameplay_writes"], 0)
        self.assertEqual(contract["fixture_writes"], 0)
        self.assertEqual(contract["vram_injection_bytes"], 0)
        self.assertEqual(contract["observation_only_vbk_write_sites"], 2)
        self.assertTrue(contract["raw_vram_bank0_only"])
        self.assertTrue(contract["bank1_cpu_window_only"])
        self.assertEqual(contract["final_chr_bank_order"], [0, 1])
        self.assertEqual(
            binder.audit_live_probe_bank_contract()["final_chr_bank_order"],
            [0, 1],
        )
        self.assertTrue(contract["deferred_core_accessor"])
        self.assertTrue(contract["deferred_runtime_environment"])
        self.assertTrue(contract["deferred_trace_open"])
        self.assertTrue(contract["token_bound_controlled_teardown"])
        self.assertTrue(contract["optional_cache_audit_is_read_only"])
        self.assertTrue(contract["svbk1_deferred_frame_sampling"])
        self.assertEqual(contract["cache_audit_breakpoint_sites"], 29)
        self.assertEqual(contract["cache_audit_watchpoint_sites"], 1)
        self.assertEqual(contract["cache_audit_wram_writes"], 0)
        source = live.PROBE.read_text()
        self.assertNotIn("local raw_vram = assert", source)
        self.assertGreater(
            source.index("return emu.memory and emu.memory.vram"),
            source.index('callbacks:add("frame"'),
        )
        prefix = source[:source.index('callbacks:add("frame"')]
        self.assertNotIn('os.getenv("PENTA_SCENE0B_STATE")', prefix)
        self.assertNotIn('io.open(OUT .. ".trace.tsv"', prefix)
        self.assertNotIn("tonumber(assert(", source)
        self.assertIn("tonumber(initial_menu_text)", source)
        self.assertIn('boot_fail("runtime-env-invalid"', source)
        self.assertIn('boot_fail("trace-open-failed"', source)
        self.assertNotIn("os.exit(", source)
        self.assertEqual(source.count("emu:stop()"), 2)
        self.assertIn('marker:write("startup_token="', source)
        self.assertIn("lut_mismatches(), STARTUP_TOKEN)", source)
        self.assertIn("PENTA_SCENE0B_CACHE_AUDIT_OUT", source)
        for snippet in (
            'install(address, 13, "epochGate13")',
            'install(address, 16, "epochGate16")',
            'install(0x7CBF, 13, "installer13")',
            'install(0x7CBF, 16, "installer16")',
            'install(0x5559, 13, "epochPublish13")',
            'install(0x5559, 16, "epochPublish16")',
            'install(0xDAD7, nil, "runtimeDAD7")',
            'install(0x001A, nil, "rst18Route001A")',
            'install(0x6CEA, 31, "selfhealEntry6CEA")',
            'install(0x6D35, 31, "selfhealRepair6D35")',
            'install(0x6D4D, 31, "selfhealStart6D4D")',
            'install(0x6DCB, 31, "transactionArmed6DCB")',
            'install(0x6E25, 31, "displayFlip6E25")',
            'install(0x6E2A, 31, "commitEffect6E2A")',
            'install(0x6CC5, 31, "menuMux6CC5")',
            'install(0x6CE2, 31, "menuEffect6CE2")',
            'install(0x4100, 21, "consumer4100")',
            'install(0x4302, 1, "compiler4302")',
            'install(0x4354, 1, "publication4354")',
            'install(0x10E2, 0, "postcopy10E2")',
            'install(0x6CCE, 19, "hazardDispatch6CCE")',
            'install(0x6BA7, 19, "hazardHelper6BA7")',
            'install(0x61B7, 19, "hazardFront61B7")',
            'install(0x4300, 20, "hazardWrite4300")',
            'install(0x4500, 20, "hazardWrite4500")',
        ):
            self.assertIn(snippet, source)
        self.assertIn("C.WATCHPOINT_TYPE.WRITE", source)
        self.assertIn('write_token_marker(".cache-audit-ready")', source)

    def test_capture_contract_pins_identity_only_retarget_policy(self) -> None:
        contract = binder.load_capture_contract()
        policy = contract["live_policy"]
        self.assertEqual(policy["normalization"], "rom-identity-only")
        self.assertEqual(policy["normalization_writes"], 0)
        self.assertEqual(policy["machine_state_writes"], 0)
        self.assertEqual(
            policy["identity_retarget_gbAs_offsets"], [4, 5, 6, 7, 31]
        )
        self.assertEqual(policy["source_serialized_model"], "80")
        self.assertEqual(policy["source_identity_flag"], "80")
        self.assertEqual(policy["target_identity_flag"], "C0")
        for capture in binder.capture_evidence(contract):
            self.assertEqual(capture["serialized_model"], "80")
            self.assertTrue(capture["serialized_rom_identity"].endswith("80"))
            self.assertEqual(capture["serialized_boot_register"], "01")

        mutant = copy.deepcopy(contract)
        mutant["live_policy"]["normalization"] = "rom-crc32-only"
        path = self.root / "mutated-capture-contract.json"
        path.write_text(json.dumps(mutant))
        with mock.patch.object(binder, "FIXTURE", path):
            with self.assertRaisesRegex(
                binder.ContractError, "ROM-identity retarget policy changed"
            ):
                binder.load_capture_contract()

    def test_optional_cache_audit_parser_is_strict_and_read_only(self) -> None:
        sidecar = self.root / "cache-audit.tsv"
        fields = list(live.CACHE_AUDIT_FIELDS)
        row = {name: "00" for name in fields}
        row.update({
            "event": "1", "kind": "frame", "sample": "1", "frame": "2",
            "phase": "captured", "svbk": "01", "ffb7": "02",
            "scene": "0B", "room": "01", "active": "01",
            "df53": "FF", "df57": "FF", "c633": "06",
            "ff99": "0D", "lcdc": "8B", "write_address": "FFFF",
            "old_value": "FF", "new_value": "FF", "pc": "FFFF",
        })
        values = [row[name] for name in fields]
        sidecar.write_text("\t".join(fields) + "\n" + "\t".join(values) + "\n")
        rows = live.parse_cache_audit(sidecar)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ffb7"], 2)
        self.assertEqual(rows[0]["df53"], 0xFF)
        self.assertEqual(rows[0]["c633"], 6)
        sidecar.write_text("wrong\n")
        with self.assertRaisesRegex(live.LiveError, "header changed"):
            live.parse_cache_audit(sidecar)

    def test_selfheal_publication_contract_is_ordered_and_fail_closed(self) -> None:
        def row(event: int, kind: str, **values: int) -> dict[str, int | str]:
            result: dict[str, int | str] = {
                "event": event, "kind": kind, "scene": 0x0B,
                "ffb7": 0x02, "svbk": 1, "dad7_7": 0xC4,
                "dad7_8": 0x13, "dad7_9": 0x00,
                "df53": 0xFF, "df57": 0xFF,
                "scy": 0, "dc02": 0, "c21b": 0, "c2b8": 0,
                "dc0b": 0, "lcdc": 0x83,
                "write_address": 0xFFFF, "old_value": 0xFF,
                "new_value": 0xFF, "ff01": 0,
            }
            result.update(values)
            return result

        rows = [
            row(1, "rst18Route001A"),
            row(2, "selfhealEntry6CEA", dad7_7=0xC2,
                dad7_8=0xB9, dad7_9=0xDA),
            row(3, "selfhealRepair6D35", dad7_7=0xC2,
                dad7_8=0xB9, dad7_9=0xDA),
            row(4, "selfhealStart6D4D", dad7_7=0xCD),
            row(5, "transactionArmed6DCB", dad7_7=0xCD),
            row(6, "runtimeDAD7", dad7_7=0xCD),
            row(7, "consumer4100", dad7_7=0xCD),
            row(8, "writeDF53", dad7_7=0xCD,
                write_address=0xDF53, new_value=0x00),
            row(9, "compiler4302", dad7_7=0xCD),
            row(10, "publication4354", dad7_7=0xCD, ff01=0x99,
                df53=0x00),
            row(11, "postcopy10E2", dad7_7=0xCD, df53=0x00),
            row(12, "hazardDispatch6CCE", dad7_7=0xCD, df53=0x00),
            row(13, "hazardHelper6BA7", dad7_7=0xCD, df53=0x00),
            row(14, "hazardFront61B7", dad7_7=0xCD, df53=0x00),
            row(15, "hazardWrite4300", dad7_7=0xCD, df53=0x00),
            row(16, "displayFlip6E25", dad7_7=0xCD, ff01=0x99,
                df53=0x00),
            row(17, "commitEffect6E2A", ff01=0x99, df53=0x00),
            row(18, "runtimeDAD7", ff01=0x99, df53=0x00),
            row(19, "consumer4100", ff01=0x99, df53=0x00),
            row(20, "writeDF57", write_address=0xDF57,
                new_value=0x00, ff01=0x99, df53=0x00),
            row(21, "compiler4302", ff01=0x99, df53=0x00,
                df57=0x00),
            row(22, "publication4354", ff01=0x9D, df53=0x00,
                df57=0x00),
            row(23, "postcopy10E2", ff01=0x9D, df53=0x00,
                df57=0x00),
            row(24, "hazardDispatch6CCE", ff01=0x9D, df53=0x00,
                df57=0x00),
            row(25, "hazardHelper6BA7", ff01=0x9D, df53=0x00,
                df57=0x00),
            row(26, "hazardFront61B7", ff01=0x9D, df53=0x00,
                df57=0x00),
        ]
        contract = live.selfheal_publication_contract(
            rows, require_semantic_write=True
        )
        self.assertEqual(contract["repair_event"], 3)
        self.assertEqual(contract["start_event"], 4)
        self.assertEqual(contract["armed_event"], 5)
        self.assertEqual(contract["display_event"], 16)
        self.assertEqual(contract["commit_event"], 17)
        self.assertEqual(contract["effect_event"], 17)
        self.assertEqual(
            contract["repopulation_by_address"], {"DF53": 1, "DF57": 1}
        )
        self.assertEqual(contract["hazard_semantic_owner"], {
            "postcopy": 2,
            "dispatcher": 2,
            "helper": 2,
            "geometry_front": 2,
            "writer_4300": 1,
            "writer_4500": 0,
        })
        mutations = []
        repeated_start = copy.deepcopy(rows)
        repeated_start.append(row(27, "selfhealStart6D4D", dad7_7=0xCD))
        mutations.append(repeated_start)
        repeated_commit = copy.deepcopy(rows)
        repeated_commit.append(row(27, "commitEffect6E2A"))
        mutations.append(repeated_commit)
        wrong_order = copy.deepcopy(rows)
        wrong_order[2]["event"], wrong_order[3]["event"] = 4, 3
        mutations.append(wrong_order)
        missing_map = [copy.deepcopy(item) for item in rows
                       if item["kind"] != "writeDF57"]
        mutations.append(missing_map)
        missing_compiler = [copy.deepcopy(item) for item in rows
                            if item["kind"] != "compiler4302"]
        mutations.append(missing_compiler)
        missing_publication = copy.deepcopy(rows)
        missing_publication[21]["ff01"] = 0x99
        mutations.append(missing_publication)
        wrong_semantic_key = copy.deepcopy(rows)
        wrong_semantic_key[7]["new_value"] = 0x01
        mutations.append(wrong_semantic_key)
        alias_tags = copy.deepcopy(rows)
        alias_tags[9]["ff01"], alias_tags[21]["ff01"] = 0x98, 0x9C
        mutations.append(alias_tags)
        partial_preimage = copy.deepcopy(rows)
        partial_preimage[2]["dad7_8"] = 0x13
        mutations.append(partial_preimage)
        missing_semantic_writer = [
            copy.deepcopy(item) for item in rows
            if item["kind"] != "hazardWrite4300"
        ]
        mutations.append(missing_semantic_writer)
        wrong_row_owner = copy.deepcopy(rows)
        next(
            item for item in wrong_row_owner
            if item["kind"] == "hazardHelper6BA7"
        )["ffb7"] = 0x03
        mutations.append(wrong_row_owner)
        prestart_wrong_row_owner = copy.deepcopy(rows)
        prestart_wrong_row_owner.append(
            row(0, "hazardHelper6BA7", ffb7=0x03)
        )
        mutations.append(prestart_wrong_row_owner)
        for mutant in mutations:
            with self.subTest(mutant=mutations.index(mutant)):
                with self.assertRaises(live.LiveError):
                    live.selfheal_publication_contract(
                        mutant, require_semantic_write=True
                    )

    def test_receipt_checks_cannot_pass_vacuously(self) -> None:
        captures = [
            {"label": "candidate-native-closed-after-operator-low-health",
             "sha256": "a",
             "captured_state": {"D880": "0B"}},
            {"label": "operator-low-health-menu-loaded", "sha256": "b",
             "captured_state": {"D880": "0B"}},
        ]
        checks = live.receipt_checks(
            captures, [], {"archived": True},
            {
                "label": "operator-corrupted-walls",
                "captured_state": {"D880": "0B"},
                "incompatibility": {
                    "live_replays": 0,
                    "policy": (
                        "archive-exact-and-reject-live-resume-without-"
                        "cpu-stack-normalization"
                    ),
                },
            },
            {"native_select_only": True, "machine_state_writes": 0},
        )
        self.assertTrue(checks)
        self.assertFalse(any(checks.values()), checks)

    def test_runtime_observation_sites_are_fixture_pinned(self) -> None:
        fixture = json.loads(live.RUNTIME_OBSERVATION_FIXTURE.read_text())
        candidate = self.root / "exact-r318.gb"
        payload = bytearray(r318.DEFAULT_OUTPUT.read_bytes())
        candidate.write_bytes(payload)
        contract = live.runtime_observation_contract(candidate)
        self.assertEqual(set(contract["sites"]), set(fixture["sites"]))
        self.assertEqual(fixture["candidate_sha256"], hashlib.sha256(
            payload
        ).hexdigest())
        self.assertEqual(
            contract["sites"]["stage1_split_key_consumer"]["breakpoint"],
            "4100",
        )
        self.assertEqual(
            contract["sites"]["runtime_selfheal_repair"]["breakpoint"],
            "6D35",
        )
        self.assertEqual(
            contract["sites"]["fixed_rst18_route"]["breakpoint_bank"], None,
        )
        site = fixture["sites"]["current_menu_cache_effect"]
        payload[site["offset"]] ^= 1
        candidate.write_bytes(payload)
        with self.assertRaisesRegex(live.LiveError, "another candidate"):
            live.runtime_observation_contract(candidate)
        fixture["candidate_sha256"] = hashlib.sha256(payload).hexdigest()
        mutant_fixture = self.root / "mutated-runtime-sites.json"
        mutant_fixture.write_text(json.dumps(fixture))
        with mock.patch.object(
            live, "RUNTIME_OBSERVATION_FIXTURE", mutant_fixture
        ):
            with self.assertRaisesRegex(live.LiveError, "reviewed"):
                live.runtime_observation_contract(candidate)

    def test_probe_audit_rejects_lost_bank21_observer(self) -> None:
        mutant = live.PROBE.read_text().replace(
            'install(0x4100, 21, "consumer4100")',
            'install(0x4101, 21, "consumer4100")',
        )
        with self.assertRaisesRegex(live.LiveError, "lacks contract"):
            live.audit_probe_source(mutant)

    def test_probe_audit_rejects_lost_svbk_frame_deferral(self) -> None:
        mutant = live.PROBE.read_text().replace(
            "deferred_wram_frames = deferred_wram_frames + 1",
            "deferred_wram_frames = deferred_wram_frames",
        )
        with self.assertRaisesRegex(live.LiveError, "lacks contract"):
            live.audit_probe_source(mutant)

    def test_probe_audit_rejects_unsampled_repair_settle(self) -> None:
        mutant = live.PROBE.read_text().replace(
            'elseif phase == "repair_settle" then\n'
            "    -- This is candidate-rendered output immediately after the native close,\n"
            "    -- including the first close of the initially menu-loaded operator seed.\n"
            "    -- Sample every frame so a transient palette/tile smear cannot hide in the\n"
            "    -- repair window before the menu is reopened.\n"
            "    sample_phase()",
            'elseif phase == "repair_settle" then\n'
            "    -- This is candidate-rendered output immediately after the native close,\n"
            "    -- including the first close of the initially menu-loaded operator seed.\n"
            "    -- Sample every frame so a transient palette/tile smear cannot hide in the\n"
            "    -- repair window before the menu is reopened.",
        )
        with self.assertRaisesRegex(live.LiveError, "repair-settle"):
            live.audit_probe_source(mutant)

    def test_probe_audit_rejects_unchecked_final_plane_dump(self) -> None:
        mutant = live.PROBE.read_text().replace(
            'if not dump_physical_planes() then\n'
            '      finish("fail", "final-physical-planes-unreadable")\n'
            "      return\n"
            "    end",
            "dump_physical_planes()",
        )
        with self.assertRaisesRegex(live.LiveError, "lacks contract"):
            live.audit_probe_source(mutant)

    def test_probe_and_binder_reject_raw_bank0_alias_for_vbk1(self) -> None:
        mutant = live.PROBE.read_text().replace(
            "values[index] = emu:read8(0x8000 + offset)",
            "values[index] = raw_vram:read8(offset)\n"
            "    -- values[index] = emu:read8(0x8000 + offset)",
        )
        with self.assertRaisesRegex(
            live.LiveError, "raw VRAM reads are not bank-zero-only"
        ):
            live.audit_probe_source(mutant)
        with self.assertRaisesRegex(
            binder.ContractError, "raw VRAM reads are not bank-zero-only"
        ):
            binder.audit_live_probe_bank_contract(mutant)

    def test_final_physical_plane_oracle_is_immutable_and_two_map(self) -> None:
        rom = r313.DEFAULT_OUTPUT.read_bytes()
        lut = rom[live.STAGE1_LUT_OFFSET:live.STAGE1_LUT_OFFSET + 0x100]
        tile_map = bytearray(0x400)
        for column in range(11):
            tile_map[0x20 + column] = 0x64
        expected, positions = live._stage1_semantic_attrs(
            bytes(tile_map), lut, 0x03
        )
        self.assertEqual(len(positions), 11)
        self.assertTrue(all(expected[0x20 + column] == 0x0F
                            for column in range(11)))
        source = bytearray(24 * 24)
        for row in range(24):
            source[row * 24:(row + 1) * 24] = tile_map[
                row * 32:row * 32 + 24
            ]
        dump = self.root / "scene0b.planes.bin"
        metadata = self.root / "scene0b.planes.meta"
        dump.write_bytes(
            bytes(tile_map) * 2 + expected * 2 + bytes(source) + lut
        )
        metadata.write_text(
            "frame=99\nsample=60\nphase=post_close\nlcdc=83\n"
            "scx=00\nscy=00\nscene=0B\nroom=03\nmenu=00\n"
            "schema=maps-v1\nbytes=4928\n"
        )
        receipt = live.physical_plane_receipt(
            dump, metadata, lut, bytes(source)
        )
        self.assertTrue(receipt["runtime_lut_matches_canonical"])
        self.assertTrue(all(
            row["semantic_mismatches_visible"] == 0
            and row["tile_source_mismatches_visible"] == 0
            for row in receipt["maps"].values()
        ))
        mutant = bytearray(dump.read_bytes())
        mutant[0x800 + 0x20] = 0x07
        # Mirror the same non-hazard corruption into C1A0 and the active map.
        # Publication-consistency self-baselining must not bless it.
        mutant[0x6F] ^= 1
        mutant[0x1000 + 87] ^= 1
        dump.write_bytes(mutant)
        receipt = live.physical_plane_receipt(
            dump, metadata, lut, bytes(source)
        )
        self.assertEqual(
            receipt["maps"]["9800"]["semantic_mismatches_visible"], 1
        )
        self.assertEqual(
            receipt["maps"]["9800"]["tile_source_mismatches_visible"], 0
        )
        self.assertEqual(
            receipt["maps"]["9800"][
                "tile_immutable_mismatches_outside_hazard_visible"
            ],
            1,
        )
        self.assertEqual(
            receipt["source_immutable_mismatches_outside_hazard_visible"], 1
        )

    def test_full_compiler_plane_seams_and_padding_are_immutable(self) -> None:
        rom = r313.DEFAULT_OUTPUT.read_bytes()
        lut = rom[live.STAGE1_LUT_OFFSET:live.STAGE1_LUT_OFFSET + 0x100]
        immutable = bytes(24 * 24)
        metadata = self.root / "full-owner.planes.meta"
        metadata.write_text(
            "frame=99\nsample=60\nphase=post_close\nlcdc=83\n"
            "scx=08\nscy=00\nscene=0B\nroom=03\nmenu=00\n"
            "schema=maps-v1\nbytes=4928\n"
        )
        # These four positions were all outside the former viewport-only
        # oracle: left seam, right seam, bottom owned row, and zero padding.
        for case, (row, column) in enumerate(
            ((0, 0), (0, 21), (19, 10), (23, 23)), 1
        ):
            with self.subTest(row=row, column=column):
                tile_map = bytearray(0x400)
                source = bytearray(immutable)
                offset = row * 32 + column
                tile_map[offset] = 0x02
                source[row * 24 + column] = 0x02
                attrs, _ = live._stage1_semantic_attrs(
                    bytes(tile_map), lut, 0x03, set()
                )
                dump = self.root / f"full-owner-{case}.planes.bin"
                dump.write_bytes(
                    bytes(tile_map) * 2 + attrs * 2 + bytes(source) + lut
                )
                receipt = live.physical_plane_receipt(
                    dump, metadata, lut, immutable
                )
                self.assertEqual(
                    receipt[
                        "source_immutable_mismatches_outside_hazard_visible"
                    ],
                    1,
                )
                self.assertEqual(
                    receipt["maps"]["9800"][
                        "tile_immutable_mismatches_outside_hazard_visible"
                    ],
                    1,
                )

    def test_stage1_cram_contract_includes_static_hazard_row(self) -> None:
        candidate = with_reviewed_terminal_art(
            r314.DEFAULT_OUTPUT.read_bytes()
        )
        cram = live.expected_stage1_bg_cram(candidate)
        self.assertEqual(len(cram), 64)
        self.assertEqual(
            cram.hex().upper(),
            "FF7F947E4A3D0000FF7F1F004A290000"
            "FF7F1F7E4A290000FF7FC93A43210000"
            "FF7FE07F803D0000FF7FFF031F000000"
            "FF7F1B7F083D0000FF7F947EFF034A3D",
        )
        for offset in (
            live.STAGE1_BG_PALETTE_OFFSET,
            live.STAGE1_HAZARD_BG7_OFFSET,
        ):
            with self.subTest(offset=f"{offset:X}"):
                mutant = bytearray(candidate)
                mutant[offset] ^= 1
                with self.assertRaisesRegex(
                    live.LiveError, "canonical Stage-1 BG CRAM"
                ):
                    live.expected_stage1_bg_cram(bytes(mutant))
                with self.assertRaisesRegex(
                    binder.ContractError, "canonical Stage-1 BG CRAM"
                ):
                    binder.canonical_runtime_oracles(
                        bytes(mutant), bytes(24 * 24), bytes(0x800)
                    )

    def test_operator_sources_rebuild_from_world_and_sram(self) -> None:
        captures = binder.capture_evidence(binder.load_capture_contract())
        expected = {
            "candidate-native-closed-after-operator-low-health": (
                "071a7e6fc168809e476a8996113956779"
                "d5d06bde774183bc4032b772359d42a"
            ),
            "operator-low-health-menu-loaded": (
                "071a7e6fc168809e476a8996113956779"
                "d5d06bde774183bc4032b772359d42a"
            ),
        }
        for capture in captures:
            rebuilt = live.capture_immutable_source(capture)
            self.assertEqual(
                hashlib.sha256(rebuilt).hexdigest(),
                expected[capture["label"]],
            )

    def test_bg_art_uses_hash_pinned_rom_source_not_negative_capture(
        self,
    ) -> None:
        rom = with_reviewed_terminal_art(r313.DEFAULT_OUTPUT.read_bytes())
        art = live.canonical_stage1_bg_art(rom)
        self.assertEqual(len(art), 0x1000)
        self.assertEqual(hashlib.sha256(art).hexdigest(),
                         live.STAGE1_BG_ART_SHA256)

        contract = binder.load_capture_contract()
        corrupted_spec = contract["archived_incompatible_capture"]
        corrupted = {
            "path": str((ROOT / corrupted_spec["path"]).resolve())
        }
        captured_vram = binder.gbas_payload(
            Path(corrupted["path"])
        )[0x400:0x4400]
        # Signed tile $10 is one of the reported corrupt entrance/wall-edge
        # glyphs.  The bad capture must not be able to define its own truth.
        self.assertNotEqual(
            captured_vram[0x1100:0x1110], art[0x100:0x110]
        )

        mutant = bytearray(rom)
        mutant[live.STAGE1_LOW_TILE_GFX_OFFSET + 0x10 * 16] ^= 0x01
        with self.assertRaisesRegex(live.LiveError, "canonical Stage-1 art"):
            live.canonical_stage1_bg_art(bytes(mutant))

    def test_live_probe_uses_only_independent_immutable_source(self) -> None:
        source = live.PROBE.read_text()
        capture = source.split(
            "local function capture_immutable_source()", 1
        )[1].split("local function reconstruct_current_world_source()", 1)[0]
        self.assertIn("immutable_source_packed", capture)
        self.assertNotIn("emu:read8(0xC1A0", capture)
        self.assertIn(
            'os.getenv("PENTA_SCENE0B_IMMUTABLE_SOURCE")', source
        )
        self.assertIn("reconstruct_current_world_source()", source)
        self.assertIn(
            'os.getenv("PENTA_SCENE0B_STAGE1_TABLES")', source
        )
        tile_oracle = source.split(
            "local function immutable_tile_mismatches()", 1
        )[1].split("local function bg_cram_mismatches()", 1)[0]
        self.assertIn("published_tile_planes[0x8000 + base]", tile_oracle)
        self.assertIn(
            "tiles[relative + 1] ~= expected[relative + 1]",
            tile_oracle,
        )
        self.assertIn(
            "if not animation_owned\n"
            "          and tiles[relative + 1] ~= expected[relative + 1]",
            tile_oracle,
        )
        self.assertEqual(
            tile_oracle.count("exact_hazard_tile_mismatches("), 3
        )
        self.assertIn(
            "exact_hazard_tile_mismatches(current_source)", tile_oracle
        )
        self.assertIn(
            "exact_hazard_tile_mismatches(expected)", tile_oracle
        )
        self.assertIn("exact_hazard_tile_mismatches(tiles)", tile_oracle)
        publisher = "arm_tile_publication_oracle = function()" + source.split(
            "arm_tile_publication_oracle = function()", 1
        )[1].split("local function semantic_attr_mismatches()", 1)[0]
        self.assertIn("reconstruct_current_world_source()", publisher)
        self.assertIn("emu:read8(0xC1A0 + row * 24 + column)", publisher)
        self.assertGreater(
            publisher.index("publish_tile_publication_oracle = function()"),
            publisher.index("arm_tile_publication_oracle = function()"),
        )
        self.assertGreater(
            publisher.index("emu:read8(0xC1A0 + row * 24 + column)"),
            publisher.index("publish_tile_publication_oracle = function()"),
        )
        self.assertIn("published_tile_planes[pending.destination]", publisher)
        self.assertIn("emu:read8(0xFF55) ~= 0xFF", publisher)
        arm = publisher.split(
            "publish_tile_publication_oracle = function()", 1
        )[0]
        self.assertNotIn("if pending_tile_plane then", arm)
        self.assertIn("expected_art[expected_base + byte + 1]", source)
        self.assertNotIn("bank * 0x2000 + address + byte", source)
        self.assertIn("local function read_vbk1(offsets)", source)
        self.assertIn("local function native_menu_owned()", source)
        self.assertIn("last_owned = native_menu_owned()", source)
        self.assertIn("local native_owned = native_menu_owned()", source)
        self.assertIn(
            "values[index] = emu:read8(0x8000 + offset)", source
        )
        self.assertIn("observed_bank1 = read_vbk1(pattern_offsets)", source)
        self.assertIn("local bank1_chr = read_vbk1(chr_offsets)", source)
        self.assertLess(
            source.index("chr_handle:write(byte_blob(bank0_chr))"),
            source.index("chr_handle:write(byte_blob(bank1_chr))"),
        )
        self.assertIn(
            'os.getenv("PENTA_SCENE0B_CANONICAL_BG_ART")', source
        )
        self.assertIn(
            'os.getenv("PENTA_SCENE0B_CANONICAL_HAZARD_BANK1_ART")',
            source,
        )
        self.assertIn('os.getenv("PENTA_SCENE0B_HAZARD_PHASES")', source)

    def test_bg_cram_fallback_restores_only_the_selector(self) -> None:
        source = live.PROBE.read_text()
        function = source.split(
            "local function bg_cram_mismatches()", 1
        )[1].split("local function lut_mismatches()", 1)[0]
        self.assertIn("emu:write8(0xFF68, index)", function)
        self.assertIn("emu:write8(0xFF68, old_index)", function)
        self.assertNotIn("emu:write8(0xFF69", function)
        self.assertIn(
            '"PENTA_SCENE0B_IMMUTABLE_SOURCE": '
            "immutable_source.hex().upper()",
            Path(live.__file__).read_text(),
        )

    def test_stray_tooth_cannot_create_its_own_hazard_exemption(self) -> None:
        rom = r313.DEFAULT_OUTPUT.read_bytes()
        lut = rom[live.STAGE1_LUT_OFFSET:live.STAGE1_LUT_OFFSET + 0x100]
        immutable = bytes(24 * 24)
        tiles = bytearray(0x400)
        stray = 3 * 32 + 15
        tiles[stray] = 0x64
        attrs, _ = live._stage1_semantic_attrs(
            bytes(tiles), lut, 0x03, set()
        )
        attrs = bytearray(attrs)
        attrs[stray] = 0x0F
        mirrored_source = bytearray(24 * 24)
        mirrored_source[3 * 24 + 15] = 0x64
        dump = self.root / "stray.planes.bin"
        metadata = self.root / "stray.planes.meta"
        dump.write_bytes(
            bytes(tiles) * 2 + bytes(attrs) * 2
            + bytes(mirrored_source) + lut
        )
        metadata.write_text(
            "frame=99\nsample=60\nphase=post_close\nlcdc=83\n"
            "scx=00\nscy=00\nscene=0B\nroom=03\nmenu=00\n"
            "schema=maps-v1\nbytes=4928\n"
        )
        receipt = live.physical_plane_receipt(
            dump, metadata, lut, immutable
        )
        self.assertEqual(
            receipt["maps"]["9800"]["semantic_mismatches_visible"], 1
        )
        self.assertEqual(
            receipt["maps"]["9800"][
                "tile_immutable_mismatches_outside_hazard_visible"
            ],
            1,
        )

    def test_launcher_command_is_fixed_singleflight_without_override(self) -> None:
        command = live.launcher_command(
            self.root / "candidate.gb", self.root / "runtime"
        )
        self.assertEqual(Path(command[0]), live.LAUNCHER)
        self.assertEqual(Path(command[0]).name, "mgba-qt-singleflight")
        self.assertNotIn("--mgba", command)
        self.assertNotIn("-l", command)
        self.assertLess(command.index("--script"), command.index(
            str(self.root / "candidate.gb")
        ))
        self.assertEqual(command[-3:-1], ["--script", str(live.PROBE)])

    def test_missing_probe_startup_fails_fast_without_emulator(self) -> None:
        startup = self.root / "missing.startup"
        ready = self.root / "missing.trace"
        core_ready = self.root / "missing.core"
        marker = self.root / "missing.done"
        log = self.root / "subprocess.log"
        started = time.monotonic()
        with self.assertRaisesRegex(live.LiveError, "startup handshake"):
            live.run_process(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                os.environ.copy(), self.root, log, marker, 2.0,
                startup=startup, startup_token="offline-token", ready=ready,
                core_ready=core_ready,
                startup_timeout=0.05, ready_timeout=0.05,
            )
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertTrue((self.root / "startup-process-check.log").is_file())

    def test_started_probe_without_ready_trace_fails_fast(self) -> None:
        startup = self.root / "started.startup"
        ready = self.root / "started.trace"
        core_ready = self.root / "started.core"
        marker = self.root / "started.done"
        token = "offline-ready-token"
        command = [
            sys.executable, "-c",
            (
                "from pathlib import Path; import sys, time; "
                "Path(sys.argv[1]).write_text(sys.argv[2]); time.sleep(10)"
            ),
            str(startup), token,
        ]
        with self.assertRaisesRegex(live.LiveError, "ready trace"):
            live.run_process(
                command, os.environ.copy(), self.root,
                self.root / "ready-subprocess.log", marker, 2.0,
                startup=startup, startup_token=token, ready=ready,
                core_ready=core_ready,
                startup_timeout=0.5, ready_timeout=0.05,
            )

    def test_ready_probe_without_core_accessor_fails_fast(self) -> None:
        startup = self.root / "core.startup"
        ready = self.root / "core.ready"
        core_ready = self.root / "core.missing"
        marker = self.root / "core.done"
        token = "offline-core-token"
        command = [
            sys.executable, "-c",
            (
                "from pathlib import Path; import sys, time; "
                "Path(sys.argv[1]).write_text(sys.argv[3]); "
                "Path(sys.argv[2]).write_text(sys.argv[3]); time.sleep(10)"
            ),
            str(startup), str(ready), token,
        ]
        with self.assertRaisesRegex(live.LiveError, "core VRAM accessor"):
            live.run_process(
                command, os.environ.copy(), self.root,
                self.root / "core-subprocess.log", marker, 2.0,
                startup=startup, startup_token=token, ready=ready,
                core_ready=core_ready, startup_timeout=0.5,
                ready_timeout=0.5, core_timeout=0.05,
            )

    def test_probe_audit_rejects_an_extra_gameplay_write(self) -> None:
        mutant = live.PROBE.read_text() + "\nemu:write8(0xD000, 0)\n"
        with self.assertRaisesRegex(live.LiveError, "exactly four"):
            live.audit_probe_source(mutant)

    def test_probe_audit_rejects_assert_multireturn_into_tonumber(self) -> None:
        mutant = live.PROBE.read_text().replace(
            "tonumber(initial_menu_text)",
            'tonumber(assert(initial_menu_text, "initial menu required"))',
        )
        with self.assertRaisesRegex(live.LiveError, "tonumber's base"):
            live.audit_probe_source(mutant)

    def test_probe_audit_rejects_frame_callback_process_exit(self) -> None:
        mutant = live.PROBE.read_text().replace(
            "emu:stop()", "os.exit(0)", 1,
        )
        with self.assertRaisesRegex(live.LiveError, "tear Qt down"):
            live.audit_probe_source(mutant)

    def test_exact_child_teardown_requires_authenticated_completion(self) -> None:
        startup = self.root / "complete.startup"
        ready = self.root / "complete.ready"
        core_ready = self.root / "complete.core-ready"
        marker = self.root / "complete.done"
        token = "offline-controlled-token"
        command = [
            sys.executable, "-c",
            (
                "from pathlib import Path; import sys, time; "
                "[Path(path).write_text(sys.argv[4]) for path in sys.argv[1:4]]; "
                "Path(sys.argv[5]).write_text('status=ok\\nstartup_token=' "
                "+ sys.argv[4] + '\\n'); time.sleep(10)"
            ),
            str(startup), str(ready), str(core_ready), token, str(marker),
        ]
        outcome = live.run_process(
            command, os.environ.copy(), self.root,
            self.root / "complete-subprocess.log", marker, 2.0,
            startup=startup, startup_token=token, ready=ready,
            core_ready=core_ready, startup_timeout=0.5,
            ready_timeout=0.5, core_timeout=0.5,
        )
        self.assertTrue(outcome["exact_child_terminated"])
        self.assertEqual(outcome["completion_status"], "ok")
        accepted = live.validate_process_teardown(
            outcome, completion_authenticated=True
        )
        self.assertEqual(
            accepted["policy"], "authenticated-exact-child-termination"
        )
        with self.assertRaisesRegex(live.LiveError, "precedes authenticated"):
            live.validate_process_teardown(
                outcome, completion_authenticated=False
            )

    def test_arbitrary_nonzero_exit_is_never_accepted(self) -> None:
        with self.assertRaisesRegex(live.LiveError, "exited unexpectedly"):
            live.validate_process_teardown({
                "exact_child_terminated": False,
                "termination_method": "already-exited",
                "return_code": -11,
            }, completion_authenticated=True)

    def test_completion_report_and_trace_tokens_are_fail_closed(self) -> None:
        marker = self.root / "mutated.done"
        marker.write_text("status=ok\nstartup_token=wrong\n")
        with self.assertRaisesRegex(live.LiveError, "token differs"):
            live.parse_completion_marker(marker, "expected")

        trace = self.root / "mutated.trace.tsv"
        trace.write_text(
            "1\t1\tcaptured\t0B\t01\t01\t00\t8B\t0C\t00\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\twrong\n"
        )
        with self.assertRaisesRegex(live.LiveError, "trace token differs"):
            live.parse_trace(trace, "expected")

    def test_identity_retarget_changes_no_machine_state(self) -> None:
        capture = binder.capture_evidence(binder.load_capture_contract())[0]
        source = Path(capture["path"])
        candidate = self.identity_candidate(source)
        destination = self.root / "retargeted.ss0"
        result = live.retarget_capture(source, destination, candidate)
        before = binder.gbas_payload(source)
        after = binder.gbas_payload(destination)
        differences = [
            index
            for index, values in enumerate(zip(before, after, strict=True))
            if values[0] != values[1]
        ]
        self.assertEqual(differences, result["changed_gbAs_offsets"])
        candidate_crc = (
            zlib.crc32(candidate.read_bytes()) & 0xFFFFFFFF
        ).to_bytes(4, "little")
        expected = [
            4 + index for index, values in enumerate(zip(
                before[4:8], candidate_crc, strict=True
            )) if values[0] != values[1]
        ] + [0x1F]
        self.assertEqual(differences, expected)
        self.assertEqual(before[:4], after[:4])
        self.assertEqual(before[8:0x1F], after[8:0x1F])
        self.assertEqual(before[0x20:], after[0x20:])
        self.assertEqual(before[0x1F], 0x80)
        self.assertEqual(after[0x1F], 0xC0)
        self.assertEqual(after[0x10:0x20], candidate.read_bytes()[0x134:0x144])
        self.assertEqual(result["rom_identity"], after[0x10:0x20].hex())
        self.assertEqual(result["normalization_writes"], 0)
        self.assertEqual(result["vram_injection_bytes"], 0)

    def test_identity_retarget_rejects_machine_and_identity_mutations(
        self,
    ) -> None:
        capture = binder.capture_evidence(binder.load_capture_contract())[0]
        source = Path(capture["path"])
        candidate = self.identity_candidate(source)
        cases = (
            (0x08, 0x00, "model-mutant.ss0", "CGB mode"),
            (0x350, 0xFF, "bios-mutant.ss0", "inside the BIOS"),
            (0x1F, 0x00, "identity-mutant.ss0", "80->\\$C0"),
        )
        for offset, value, name, message in cases:
            with self.subTest(name=name):
                mutant = self.mutated_state(source, name, offset, value)
                with self.assertRaisesRegex(live.LiveError, message):
                    live.retarget_capture(
                        mutant, self.root / f"out-{name}", candidate
                    )

        title_mutant = self.identity_candidate(
            source, "title-mutant.gb", title_byte=ord("X")
        )
        with self.assertRaisesRegex(live.LiveError, "title bytes 0..14"):
            live.retarget_capture(
                source, self.root / "title-mutant.ss0", title_mutant
            )
        compatible_target = self.identity_candidate(
            source, "compatible-target.gb", flag=0x80
        )
        with self.assertRaisesRegex(live.LiveError, "80->\\$C0"):
            live.retarget_capture(
                source, self.root / "compatible-target.ss0",
                compatible_target,
            )
        short_target = self.root / "short-target.gb"
        short_target.write_bytes(b"short")
        with self.assertRaisesRegex(live.LiveError, "too small"):
            live.retarget_capture(
                source, self.root / "short-target.ss0", short_target
            )

        version_mutant = self.mutated_state(
            source, "version-mutant.ss0", 0x00, 0x02
        )
        with self.assertRaisesRegex(binder.ContractError, "version changed"):
            live.retarget_capture(
                version_mutant, self.root / "version-target.ss0", candidate
            )

        chunks = state_normalizer.png_chunks(source.read_bytes())
        index = next(
            index for index, (kind, _) in enumerate(chunks)
            if kind == b"gbAs"
        )
        shortened = zlib.decompress(chunks[index][1])[:-1]
        chunks[index] = (b"gbAs", zlib.compress(shortened, level=9))
        size_mutant = self.root / "size-mutant.ss0"
        state_normalizer.write_png(size_mutant, chunks)
        with self.assertRaisesRegex(binder.ContractError, "size changed"):
            live.retarget_capture(
                size_mutant, self.root / "size-target.ss0", candidate
            )

    def test_archived_bad_screens_and_neutral_controls_are_live(self) -> None:
        controls = live.archived_negative_controls()
        self.assertTrue(all(controls.values()), controls)

        wall_oracle = live.operator_visual_oracle(
            "operator-corrupted-walls"
        )
        archived_frames = [
            {"phase": "post_close", "pixels": wall_oracle["pixels"]}
            for _ in range(24)
        ]
        archived_metrics = live.visual_metrics(
            archived_frames, "operator-corrupted-walls"
        )
        self.assertEqual(archived_metrics["red_green_artifact_frames"], 24)
        self.assertEqual(archived_metrics["wall_edge_artifact_frames"], 24)

        neutral = tuple(
            (165, 165, 255)
            for _ in range(live.SCREEN_WIDTH * live.SCREEN_HEIGHT)
        )
        yellow = list(neutral)
        base = 12 * live.SCREEN_WIDTH + 10
        yellow[base:base + 12] = [(255, 220, 0)] * 12
        magenta = list(neutral)
        for y in range(8):
            for x in range(8):
                magenta[y * live.SCREEN_WIDTH + x] = (200, 20, 180)
        self.assertEqual(live.longest_yellow_run(neutral), 0)
        self.assertEqual(live.longest_yellow_run(yellow), 12)
        self.assertEqual(live.magenta_outside_actor(neutral), 0)
        self.assertEqual(live.magenta_outside_actor(magenta), 64)
        gray_hazard = list(neutral)
        gray_hazard[base:base + 6] = [(255, 220, 0)] * 6
        gray_hazard[base + 6:base + 10] = [(82, 82, 123)] * 4
        self.assertGreaterEqual(live.gray_near_hazard(gray_hazard), 3)

    def test_operator_visual_masks_are_hash_pinned_not_candidate_learned(
        self,
    ) -> None:
        expected = {
            "operator-corrupted-walls": (2588, "e0eb724ad0b5b86c"),
            "operator-low-health-menu-loaded": (6483, "c149949d529de0cd"),
        }
        for label, (count, digest_prefix) in expected.items():
            oracle = live.operator_visual_oracle(label)
            self.assertEqual(len(oracle["wall_mask"]), count)
            self.assertTrue(
                oracle["wall_mask_sha256"].startswith(digest_prefix)
            )
            self.assertEqual(
                live.mask_sha256(oracle["wall_mask"]),
                oracle["wall_mask_sha256"],
            )
        wall_oracle = live.operator_visual_oracle(
            "operator-corrupted-walls"
        )
        self.assertEqual(len(wall_oracle["forbidden_chromatic_mask"]), 57)
        source = inspect.getsource(live.visual_metrics)
        self.assertIn("operator_visual_oracle(oracle_label)", source)
        self.assertNotIn("stable_wall_mask", source)
        self.assertIn(
            "visual_oracle_fixture", binder.expected_live_tool_identity()
        )

    def test_persistent_red_green_and_clear_walls_cannot_train_baseline(
        self,
    ) -> None:
        label = "operator-corrupted-walls"
        oracle = live.operator_visual_oracle(label)
        clean = list(oracle["pixels"])
        for index, color in enumerate(clean[:
                live.SCREEN_WIDTH * live.PLAYFIELD_HEIGHT]):
            x, y = index % live.SCREEN_WIDTH, index // live.SCREEN_WIDTH
            if (
                (live.is_red_or_green(color) or live.is_magenta(color))
                and not (64 <= x < 96 and 32 <= y < 104)
            ):
                clean[index] = (82, 82, 82)

        wall = sorted(oracle["wall_mask"])
        forbidden = sorted(oracle["forbidden_chromatic_mask"])
        chromatic = list(clean)
        chromatic[forbidden[0]] = (255, 0, 0)
        chromatic[forbidden[1]] = (0, 255, 0)
        frames = [
            {"phase": "post_close", "pixels": tuple(chromatic)}
            for _ in range(24)
        ]
        metrics = live.visual_metrics(frames, label)
        self.assertEqual(metrics["red_green_artifact_frames"], 24)
        self.assertEqual(metrics["wall_edge_artifact_frames"], 24)

        cleared = list(clean)
        for index in wall[:8]:
            cleared[index] = (165, 165, 255)
        frames = [
            {"phase": "post_close", "pixels": tuple(cleared)}
            for _ in range(24)
        ]
        metrics = live.visual_metrics(frames, label)
        self.assertEqual(metrics["wall_edge_artifact_frames"], 24)
        self.assertEqual(metrics["weird_edge_tile_frames"], 24)

    def test_moving_magenta_sprite_cannot_mask_or_trip_wall_oracle(self) -> None:
        label = "operator-corrupted-walls"
        oracle = live.operator_visual_oracle(label)
        clean = list(oracle["pixels"])
        for index, color in enumerate(clean[:
                live.SCREEN_WIDTH * live.PLAYFIELD_HEIGHT]):
            if live.is_red_or_green(color) or live.is_magenta(color):
                clean[index] = (82, 82, 82)
        wall = sorted(oracle["wall_mask"])
        frames = []
        for number in range(24):
            pixels = list(clean)
            pixels[wall[number * 2]] = (200, 20, 180)
            pixels[wall[number * 2 + 1]] = (200, 20, 180)
            frames.append({"phase": "post_close", "pixels": tuple(pixels)})
        metrics = live.visual_metrics(frames, label)
        self.assertEqual(metrics["red_green_artifact_frames"], 0)
        self.assertEqual(metrics["wall_edge_artifact_frames"], 0)

    def test_visual_oracle_fixture_mask_mutation_is_rejected(self) -> None:
        fixture = json.loads(live.VISUAL_ORACLE_FIXTURE.read_text())
        fixture["captures"][0]["wall_mask_pixels"] += 1
        mutant = self.root / "mutated-visual-oracle.json"
        mutant.write_text(json.dumps(fixture))
        with mock.patch.object(live, "VISUAL_ORACLE_FIXTURE", mutant):
            with self.assertRaisesRegex(live.LiveError, "wall mask changed"):
                live.operator_visual_oracle("operator-corrupted-walls")


if __name__ == "__main__":
    unittest.main()
