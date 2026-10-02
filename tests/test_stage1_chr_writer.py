from __future__ import annotations

import inspect
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_chr_writer as writer  # noqa: E402
import verify_stage1_north_integrity as north  # noqa: E402


R316_SHA256 = (
    "1373479e5a63c1adfa958ae1e278d99d32032b1d3d08386fc3a4d7641496dc2e"
)


class Stage1ChrWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidate_path = (
            ROOT / "tmp/stage1-selector-latch-relocation-r316/candidate.gb"
        )
        if not cls.candidate_path.is_file():
            raise unittest.SkipTest(
                "r316 candidate fixture is absent from repository-local tmp/"
            )
        cls.candidate = cls.candidate_path.read_bytes()
        if writer.digest(cls.candidate) != R316_SHA256:
            raise AssertionError("r316 candidate fixture identity changed")
        cls.expected = writer.canonical_pages(cls.candidate)

    @staticmethod
    def event(
        address: int,
        value: int,
        *,
        frame: int,
        **overrides: int,
    ) -> dict[str, int]:
        row = {
            "frame": frame,
            "gameplay": 0,
            "address": address,
            "old": 0,
            "new": value,
            "pc": 0x0D47 if address & 1 == 0 else 0x0D4A,
            "bank": 7,
            "af": 0,
            "bc": 0,
            "de": address,
            "hl": 0x5001 + address - 0x9000,
            "sp": 0xDFF0,
            "caller": writer.STOCK_COPY_RETURN,
            "ffa4": 0x10,
            "ffa5": 0x11,
            "ffa6": 0x12,
            "ffa7": 0x13,
            "ffa8": 0x14,
            "ffa9": 0x15,
            "ffaa": 0x16,
            "ffab": 0x17,
            "lcdc": 0x83,
            "scene": 0x18,
            "room": 5,
            "active": 1,
        }
        row.update(overrides)
        return row

    def valid_events(self) -> list[dict[str, int]]:
        rows = []
        for index, (base, page) in enumerate(self.expected.items()):
            frame = 477 + index
            rows.extend(
                self.event(base + offset, value, frame=frame)
                for offset, value in enumerate(page)
            )
        return rows

    def test_canonical_pages_are_independently_pinned(self) -> None:
        self.assertEqual(set(self.expected), set(range(0x9000, 0x9800, 0x100)))
        for index, (address, page) in enumerate(self.expected.items()):
            self.assertEqual(writer.digest(page), writer.PAGE_SHA256[index])
            mutated = bytearray(self.candidate)
            mutated[writer.CANONICAL_OFFSET + index * 0x100] ^= 1
            with self.assertRaisesRegex(ValueError, f"\\${address:04X}"):
                writer.canonical_pages(bytes(mutated))

    def test_parser_accepts_full_selector_snapshot_and_both_endpoints(self) -> None:
        fields = dict(
            frame=477, gameplay=0, address=0x9000, old=0, new=0x12,
            pc=0x0D47, bank=7, af=0, bc=0, de=0x9000, hl=0x5000,
            sp=0xDFF0, caller=writer.STOCK_COPY_RETURN,
            lcdc=0x83, scene=0x18,
            room=5, active=1,
        )
        selectors = "1011121314151617"
        rows = []
        for address in (0x9000, 0x97FF):
            fields["address"] = address
            rows.append(
                "f{frame}:g{gameplay}:a{address:04X}:o{old:02X}:n{new:02X}:"
                "p{pc:04X}:b{bank:02X}:af{af:04X}:bc{bc:04X}:"
                "de{de:04X}:hl{hl:04X}:sp{sp:04X}:k{caller:04X}:"
                f"u{selectors}:"
                "l{lcdc:02X}:s{scene:02X}:r{room:02X}:i{active:02X}"
                .format(**fields)
            )
        parsed = writer.parse_events(";".join(rows))
        self.assertEqual([row["address"] for row in parsed], [0x9000, 0x97FF])
        self.assertEqual(
            [parsed[0][field] for field in writer.SELECTOR_FIELDS],
            list(range(0x10, 0x18)),
        )

        with self.assertRaisesRegex(ValueError, "out-of-page"):
            writer.parse_events(rows[0].replace("a9000", "a9800"))
        with self.assertRaisesRegex(ValueError, "malformed"):
            writer.parse_events(rows[0].replace("p0D47", "p0d47"))

    def test_complete_canonical_load_is_bound_before_first_gameplay(self) -> None:
        result = writer.analyze_events(
            self.valid_events(), self.expected, first_gameplay=492
        )
        self.assertTrue(result["exact"])
        self.assertEqual(result["stage_load_event_count"], 0x800)
        self.assertEqual(result["stage_load_last_frame"], 484)
        self.assertEqual(result["stage_load_to_gameplay_frames"], 8)
        self.assertTrue(result["stage_load_sequence_exact"])
        self.assertTrue(result["stage_load_owner_exact"])
        self.assertTrue(result["stage_load_coverage_exact"])
        self.assertEqual(result["post_load_pre_gameplay_event_count"], 0)
        self.assertEqual(result["post_gameplay_event_count"], 0)

    def test_stock_loader_return_address_is_derived_and_pinned(self) -> None:
        self.assertEqual(writer.STOCK_COPY_CALL_OFFSET, 0x0D)
        self.assertEqual(writer.STOCK_COPY_CALL_ADDR, 0x0CA9)
        self.assertEqual(writer.STOCK_COPY_RETURN, 0x0CAC)
        self.assertEqual(
            self.candidate[
                writer.STOCK_COPY_CALL_ADDR:
                writer.STOCK_COPY_RETURN
            ],
            bytes.fromhex("CD350D"),
        )
        writer.validate_stock_loader(self.candidate)

        mutated = bytearray(self.candidate)
        mutated[writer.STOCK_COPY_CALL_ADDR] ^= 1
        with self.assertRaisesRegex(ValueError, "selector loop"):
            writer.validate_stock_loader(bytes(mutated))

        rows = self.valid_events()
        for row in rows:
            row["caller"] = 0x0CAB
        result = writer.analyze_events(
            rows, self.expected, first_gameplay=492
        )
        self.assertFalse(result["exact"])
        self.assertEqual(result["stage_load_event_count"], 0)

    def test_pre_gameplay_corrupt_byte_cannot_hide_behind_final_dump(self) -> None:
        rows = self.valid_events()
        rows[0]["new"] ^= 1
        result = writer.analyze_events(rows, self.expected, first_gameplay=492)
        self.assertFalse(result["exact"])
        self.assertEqual(result["stage_load_bad_byte_count"], 1)

    def test_every_known_dx_selector_collision_mutation_fails(self) -> None:
        for field in ("ffa5", "ffa7", "ffa8", "ffa9"):
            with self.subTest(field=field):
                rows = self.valid_events()
                rows[0][field] ^= 1
                result = writer.analyze_events(
                    rows, self.expected, first_gameplay=492
                )
                self.assertFalse(result["exact"])
                self.assertEqual(result["stage_load_bad_selector_count"], 1)

    def test_partial_stale_or_wrong_owner_loads_fail(self) -> None:
        mutations = []
        missing_endpoint = self.valid_events()
        missing_endpoint.pop(0xFF)
        mutations.append(missing_endpoint)

        stale = self.valid_events()
        for row in stale:
            row["frame"] -= 100
        mutations.append(stale)

        wrong_caller = self.valid_events()
        for row in wrong_caller:
            row["caller"] = 0xFFFF
        mutations.append(wrong_caller)

        duplicate = self.valid_events()
        duplicate.insert(1, dict(duplicate[0]))
        mutations.append(duplicate)

        wrong_pc = self.valid_events()
        wrong_pc[0]["pc"] = 0x0D4A
        mutations.append(wrong_pc)

        for rows in mutations:
            with self.subTest(kind=len(rows)):
                result = writer.analyze_events(
                    rows, self.expected, first_gameplay=492
                )
                self.assertFalse(result["exact"])

    def test_transient_write_between_loader_and_gameplay_fails(self) -> None:
        rows = self.valid_events()
        rows.append(self.event(
            0x9100, self.expected[0x9100][0] ^ 1,
            frame=490, scene=0, room=5,
        ))
        result = writer.analyze_events(rows, self.expected, first_gameplay=492)
        self.assertFalse(result["exact"])
        self.assertEqual(result["post_load_pre_gameplay_event_count"], 1)
        self.assertEqual(
            result["bad_post_load_pre_gameplay_event_count"], 1
        )

    def test_interleaved_foreign_write_during_loader_fails(self) -> None:
        rows = self.valid_events()
        rows.insert(100, self.event(
            0x9100, self.expected[0x9100][0] ^ 1,
            frame=477, scene=0, room=5,
        ))
        result = writer.analyze_events(rows, self.expected, first_gameplay=492)
        self.assertFalse(result["exact"])
        self.assertEqual(result["stage_load_event_count"], 0x800)
        self.assertEqual(result["post_load_pre_gameplay_event_count"], 1)
        self.assertEqual(
            result["bad_post_load_pre_gameplay_event_count"], 1
        )

    def test_bad_post_gameplay_write_and_reordered_trace_fail(self) -> None:
        rows = self.valid_events()
        rows.append(self.event(
            0x9100, self.expected[0x9100][0] ^ 1,
            frame=500, scene=2, room=1,
        ))
        result = writer.analyze_events(rows, self.expected, first_gameplay=492)
        self.assertFalse(result["exact"])
        self.assertEqual(result["bad_post_gameplay_event_count"], 1)

        reordered = self.valid_events()
        reordered[0]["frame"] = 600
        with self.assertRaisesRegex(ValueError, "not frame ordered"):
            writer.analyze_events(reordered, self.expected, first_gameplay=492)

    def test_trace_saturation_is_explicit_and_fail_closed(self) -> None:
        complete = writer.trace_counts({
            "chr_write_count": "10",
            "chr_write_stored_count": "10",
            "chr_write_dropped_count": "0",
        }, 10)
        self.assertTrue(complete["complete"])

        saturated = writer.trace_counts({
            "chr_write_count": "11",
            "chr_write_stored_count": "10",
            "chr_write_dropped_count": "1",
        }, 10)
        self.assertFalse(saturated["complete"])

        for report in (
            {},
            {"chr_write_count": "10", "chr_write_stored_count": "9",
             "chr_write_dropped_count": "0"},
            {"chr_write_count": "10", "chr_write_stored_count": "10",
             "chr_write_dropped_count": "1"},
        ):
            with self.subTest(report=report):
                with self.assertRaisesRegex(ValueError, "count drift"):
                    writer.trace_counts(report, 10)

    def test_scratch_and_singleflight_contracts_are_static(self) -> None:
        child = writer.TMP / "stage1-chr-writer-unit" / "out"
        self.assertEqual(writer.checked_output(child), child.resolve())
        for rejected in (writer.TMP, writer.ROOT / "tests"):
            with self.assertRaisesRegex(ValueError, "repository tmp"):
                writer.checked_output(rejected)

        probe = north.PROBE.read_text()
        self.assertIn("local CHR_WRITE_LIMIT = 32768", probe)
        self.assertIn("chr_write_dropped_count", probe)
        self.assertIn("0x9000, 0x97FF", probe)
        self.assertIn("0x97FF, C.WATCHPOINT_TYPE.WRITE", probe)
        self.assertIn("emu:read8(0xFFA4)", probe)
        self.assertIn("emu:read8(0xFFAB)", probe)
        route_source = inspect.getsource(north.run_route)
        self.assertIn('env["STAGE1_NORTH_TRACE_CHR_WRITES"] = "1"', route_source)
        self.assertIn("str(MGBA)", route_source)
        self.assertNotIn("--mgba", route_source)

        identities = writer.tool_identities()
        self.assertEqual(
            set(identities),
            {
                "verifier", "probe", "route_driver", "mgba_launcher",
                "mgba_guard", "mgba_qt",
            },
        )
        for identity in identities.values():
            self.assertEqual(len(identity["sha256"]), 64)
            self.assertGreater(identity["size"], 0)

        main_source = inspect.getsource(writer.main)
        self.assertIn("source candidate changed", main_source)
        self.assertIn("tested a different ROM copy", main_source)
        self.assertIn("tool identity changed", main_source)


if __name__ == "__main__":
    unittest.main()
