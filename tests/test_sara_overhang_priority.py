#!/usr/bin/env python3
"""Offline controls for the sara-overhang-priority stage (#14) and its gate."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "scripts/diagnostics", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import build_sara_overhang_priority as stage  # noqa: E402
import verify_sara_overhang_priority as gate  # noqa: E402

# T-cycles of every opcode on the measured paths (taken/not-taken as 2-tuples).
CYCLES = {
    0xE5: 16, 0xE1: 12, 0xF5: 16, 0xF1: 12, 0xC9: 16, 0xCD: 24, 0x7B: 4, 0x7D: 4,
    0x78: 4, 0x47: 4, 0x4F: 4, 0x5F: 4, 0x57: 4, 0x6F: 4, 0x0F: 4, 0x9F: 4, 0xA7: 4,
    0xAF: 4, 0xB0: 4, 0xB1: 4, 0xB9: 4, 0x3D: 4, 0x00: 4, 0x23: 8, 0x2A: 8, 0x7E: 8,
    0x1A: 8, 0x5E: 8, 0x56: 8, 0x77: 8, 0xA6: 8, 0x35: 12, 0xE6: 8, 0xC6: 8, 0xFE: 8,
    0x26: 8, 0x3E: 8, 0xE0: 12, 0xF0: 12, 0xEA: 16, 0xCB: 8, 0x18: 12,
}
LENGTH = {0xCD: 3, 0xEA: 3, 0xE6: 2, 0xC6: 2, 0xFE: 2, 0x26: 2, 0x3E: 2, 0xE0: 2,
          0xF0: 2, 0xCB: 2, 0x18: 2, 0x20: 2, 0x28: 2, 0x30: 2, 0x38: 2}


def run(code: bytes, org: int, start: int, stop: int | None, taken: dict[int, bool],
        calls: dict[int, tuple[bytes, int]] | None = None) -> int:
    """T-cycles from ``start`` to ``stop`` (or through RET when ``stop`` is None)."""
    pc, total = start, 0
    while pc != stop:
        op = code[pc - org]
        if op in (0x20, 0x28, 0x30, 0x38):
            jump = taken[pc]
            total += 12 if jump else 8
            pc += 2 + (int.from_bytes(code[pc - org + 1:pc - org + 2], "little", signed=True) if jump else 0)
            continue
        if op == 0x18:
            total += 12
            pc += 2 + int.from_bytes(code[pc - org + 1:pc - org + 2], "little", signed=True)
            continue
        if op == 0xCD and calls is not None:
            target = code[pc - org + 1] | code[pc - org + 2] << 8
            body, body_org = calls[target]
            total += 24 + run(body, body_org, target, None, taken)
            pc += 3
            continue
        total += CYCLES[op]
        if op == 0xC9 and stop is None:
            return total
        pc += LENGTH.get(op, 1)
    return total


class CycleTests(unittest.TestCase):
    def test_emitter_flash_paths_match_parent(self) -> None:
        for flash in (False, True):
            # parent: CALL 11A2; CALL 1188 (RES 7,A / RET); AND F8; OR C
            p = 24 + run(stage.HELPER_OLD, stage.HELPER, 0x11A2, None, {0x11B2: not flash})
            p += 24 + 8 + 16 + 8 + 4
            # stage: CALL 11A0; RRCA; AND 80; OR B; OR C; NOP
            n = 24 + run(stage.helper_code(), stage.HELPER, 0x11A0, None, {0x11B0: not flash})
            n += 4 + 8 + 4 + 4 + 4
            self.assertEqual(n, p, f"flash={flash}")

    def test_quadrant_paths_match_parent(self) -> None:
        parent = ROOT / "tmp/p14/main.gb"
        if not parent.is_file():
            self.skipTest("parent ROM fixture absent")
        old = parent.read_bytes()[stage.FLAGS:stage.FLAGS_END]
        new = stage.flags_code()
        # Range-test branches: parent $50DF (JR C $50E8, JR NC $50F0),
        # new $50D7 (JR C $50E0, JR NC $50E8). Quadrant 0 is $50A2..$50B0
        # in the parent and $50A2..$50AE in the stage.
        outcomes = {"below": (True, False), "above": (False, True), "inside": (False, False)}
        expected = {"below": 148, "above": 184, "inside": 208}
        for name, (c1, c2) in outcomes.items():
            zero = name != "inside"
            pq = run(old, stage.FLAGS, 0x50A2, 0x50B0,
                     {0x50E8: c1, 0x50F0: c2, 0x50A5: zero}, {0x50DF: (old, stage.FLAGS)})
            nq = run(new, stage.FLAGS, 0x50A2, 0x50AE,
                     {0x50E0: c1, 0x50E8: c2, 0x50AA: zero}, {0x50D7: (new, stage.FLAGS)})
            self.assertEqual((name, nq), (name, pq))
            self.assertEqual(pq, expected[name])

    def test_quadrant_prologue_and_callsites(self) -> None:
        self.assertEqual(stage.flags_code()[:12], stage.FLAGS_PROLOGUE)
        self.assertEqual(len(stage.CALLSITE_NEW), len(stage.CALLSITE_OLD))
        self.assertEqual(len(stage.helper_code()), stage.HELPER_END - stage.HELPER)
        # FFC4 belongs to the DX map publisher: never stored by this stage.
        self.assertNotIn(bytes.fromhex("E0C4"), stage.flags_code())


class CandidateTests(unittest.TestCase):
    def test_build_and_verify_installed(self) -> None:
        parent = ROOT / "tmp/p14/main.gb"
        if not parent.is_file():
            self.skipTest("parent ROM fixture absent")
        data = parent.read_bytes()
        if hashlib.sha256(data).hexdigest() != stage.PARENT:
            self.skipTest("fixture is not the parent")
        rom = stage.build(data)
        self.assertTrue(stage.verify_installed(rom))
        self.assertFalse(stage.verify_installed(data))
        import release_lock_lineage as lineage
        self.assertEqual(hashlib.sha256(rom).hexdigest(), lineage.CANDIDATE_SHA256)
        owned = [(o, n) for o, n in lineage.DELTA_VS_SARA
                 if lineage.RUN_OWNERS[o] == (lineage.OVERHANG_OWNER,)]
        spans = [(o, o + len(d)) for o, d in stage.edits(rom)]
        self.assertTrue(owned)
        for o, n in owned:
            for i in range(o, o + n):
                self.assertTrue(any(a <= i < b for a, b in spans), hex(i))
        for o, data_ in stage.edits(rom):
            mutant = bytearray(rom)
            mutant[o] ^= 1
            self.assertFalse(stage.verify_installed(bytes(mutant)), hex(o))


class ObserverTests(unittest.TestCase):
    def test_speed_probe_authenticates_exact_stage_bytes(self) -> None:
        import re
        source = (ROOT / "scripts/diagnostics/probe_stage_speed.lua").read_text()
        found = dict((int(a, 16), bytes.fromhex(b)) for a, b in
                     re.findall(r"same\(0x([A-F0-9]+), '([A-F0-9]+)'\)", source))
        self.assertEqual(found[0xDA41], b"\x2A" + stage.CALLSITE_NEW + b"\x12\x13")
        self.assertEqual(found[0x11A0], stage.helper_code().rstrip(b"\x00"))
        # flash stage ends at $11B6 (LD A,L), the probe's X-attribute point
        self.assertEqual(stage.helper_code()[0x11B6 - stage.HELPER], 0x7D)
        self.assertIn("0x11B6)", source)
        self.assertIn("0xDA4A)", source)


class GateLogicTests(unittest.TestCase):
    OAM = ((80, 80), (80, 88), (88, 80), (88, 88))

    def sample(self, priority, hidden, camera="0C08", frame=1260):
        return dict(frame=frame, world=[1240, 1356], camera=camera, scene=2, flags=[1, 1, 0, 1],
                    oam=[[y, x, 0x24, 0x80 if priority else 0] for y, x in self.OAM],
                    footprint_pixels=256, footprint_nonblack=0 if hidden else 40,
                    image_nonblack=7700)

    def run_samples(self, overhang, floor):
        out = {tag: dict(overhang) for tag in gate.OVERHANG}
        out[gate.FLOOR] = floor
        return out

    def test_accepts_hidden_and_visible_controls(self) -> None:
        good = self.run_samples(self.sample(True, True), self.sample(False, False))
        self.assertEqual(gate.evaluate(good, good)["status"], "pass")

    def test_rejects_sara_drawn_over_overhang(self) -> None:
        stock = self.run_samples(self.sample(True, True), self.sample(False, False))
        bad = (
            self.run_samples(self.sample(False, False), self.sample(False, False)),  # db09de8d
            self.run_samples(self.sample(True, False), self.sample(False, False)),   # bit set, drawn
            self.run_samples(self.sample(False, True), self.sample(False, False)),   # hidden w/o priority
            self.run_samples(self.sample(True, True), self.sample(True, False)),     # floor priority
            self.run_samples(self.sample(True, True), self.sample(False, True)),     # floor invisible
            self.run_samples(self.sample(True, True, camera="0808"), self.sample(False, False)),
        )
        for case in bad:
            with self.assertRaises(gate.GateError):
                gate.evaluate(stock, case)
        moved = self.run_samples(self.sample(True, True), self.sample(False, False))
        moved["overhang"] = dict(moved["overhang"], oam=[[81, x, t, a] for _y, x, t, a in moved["overhang"]["oam"]])
        with self.assertRaises(gate.GateError):
            gate.evaluate(stock, moved)


if __name__ == "__main__":
    unittest.main()
