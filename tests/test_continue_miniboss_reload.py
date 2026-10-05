#!/usr/bin/env python3
"""Offline controls for the continue-miniboss-reload stage and its gate."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "scripts/diagnostics", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import build_continue_miniboss_reload_trial as stage  # noqa: E402
import verify_stage1_miniboss_continue_palette as gate  # noqa: E402


def off(bank: int, address: int) -> int:
    return bank * 0x4000 + address - 0x4000


class RouterTests(unittest.TestCase):
    # M-cycles of the straight-line opcodes on the post-edge paths.
    CYCLES = {0x7A: 1, 0xE5: 4, 0x21: 3, 0xC3: 4, 0xEA: 4, 0xE0: 3, 0xC9: 4, 0xE1: 3,
              0x2A: 2, 0xE2: 2, 0x26: 2, 0x03: 2, 0x0B: 2, 0x00: 1, 0x3E: 2, 0xCD: 6}
    LEN = {0x21: 3, 0xC3: 3, 0xEA: 3, 0xE0: 2, 0x26: 2, 0x3E: 2, 0xCD: 3}

    def cost(self, code: bytes) -> list[int]:
        """Cumulative M-cycles after each instruction of straight-line code."""
        out, i, total = [], 0, 0
        while i < len(code):
            total += self.CYCLES[code[i]]
            out.append(total)
            i += self.LEN.get(code[i], 1)
        return out

    def test_dispatcher_fits_and_targets(self) -> None:
        code, labels = stage.assemble(stage.TREE_ORG, stage.dispatcher_items())
        self.assertLessEqual(stage.TREE_ORG + len(code), stage.TREE_LIMIT)
        # RCOLD is the parent router byte for byte.
        start = labels["RCOLD"] - stage.TREE_ORG
        self.assertEqual(code[start:start + len(stage.OLD_ROUTER)], stage.OLD_ROUTER)
        for name in ("RC68", "RC7C"):
            base = labels[name] - stage.TREE_ORG
            # identical fast paths and HBlank wait as the parent router
            self.assertEqual(code[base:base + 0x26], stage.OLD_ROUTER[:0x26], name)

    def test_post_edge_cycles_match_parent_and_writes_are_early(self) -> None:
        code, labels = stage.assemble(stage.TREE_ORG, stage.dispatcher_items())
        # Parent, from the HBlank edge to bank13 $71EC: router tail, $0061,
        # $09BE, then the bank-13 writer (POP HL + four LD A,[HL+]/LDH [C],A).
        parent = (stage.OLD_ROUTER[0x26:] + bytes.fromhex("EA09DC C3BE09")
                  + bytes.fromhex("E099 EA0021 C9") + stage.WRITER[:9])
        parent_cost = self.cost(parent)
        for name, extra in (("RC68", b""), ("RC7C", bytes.fromhex("267C"))):
            s = labels[name + "S"] - stage.TREE_ORG
            n = 8 + len(extra) + 1 + len(stage.pad(stage.RC_PAD[name])) // 2 + 3
            path = code[s:s + n]
            self.assertEqual(path[-3:], bytes.fromhex("C3E971"))  # JP $71E9 (bank20)
            # + CALL $0061 at $71E9, $0061 and $09BE, RET into bank13 $71EC
            new = path + bytes.fromhex("CD6100 EA09DC C3BE09 E099 EA0021 C9")
            self.assertEqual(self.cost(new)[-1], parent_cost[-1], name)
            # fourth CRAM write: parent 54 M after the edge (208 dots, past the
            # 167-dot mode-0 + mode-2 minimum); now 16 M, 22 M with poll latency
            self.assertGreater(parent_cost[-1] * 4, 87 + 80)
            self.assertLessEqual((self.cost(path)[7] + 8) * 4, 87 + 80)


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import release_lock_lineage as lineage
        cls.lineage = lineage
        cls.candidate = None
        for path in sorted((ROOT / "tmp").glob("*/build/source-a/candidate.gb")) + \
                sorted((ROOT / "tmp").glob("**/srcbuild/candidate.gb")):
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() == lineage.CANDIDATE_SHA256:
                cls.candidate = data
                break

    def setUp(self) -> None:
        if self.candidate is None:
            self.skipTest("no locally built release-lock candidate")

    def test_installed_and_owned_runs(self) -> None:
        rom = self.candidate
        self.assertTrue(stage.verify_installed(rom))
        spans = [(o, o + len(d)) for o, d in stage.edits(rom)]
        owned = [(o, n) for o, n in self.lineage.DELTA_VS_SARA
                 if self.lineage.RUN_OWNERS[o] == (self.lineage.CONTINUE_OWNER,)]
        self.assertTrue(owned)
        for o, n in owned:
            for i in range(o, o + n):
                self.assertTrue(any(a <= i < b for a, b in spans), hex(i))
        # The later #14 sara-overhang-priority stage owns disjoint runs; revert
        # both so the result is this stage's exact parent.
        import build_sara_overhang_priority as overhang
        parent = bytearray(self.lineage.revert_owned(
            rom, {self.lineage.CONTINUE_OWNER, self.lineage.OVERHANG_OWNER}))
        # Outside bank 39 and the header checksum, reverting the owned runs
        # reproduces the exact stage parent.
        parent[off(stage.PRIVATE_BANK, 0x4000):off(stage.PRIVATE_BANK, 0x8000)] = b"\xFF" * 0x4000
        parent[0x14E:0x150] = ((sum(parent[:0x14E]) + sum(parent[0x150:])) & 0xFFFF).to_bytes(2, "big")
        self.assertEqual(hashlib.sha256(parent).hexdigest(), stage.PARENT)
        self.assertEqual(overhang.build(stage.build(bytes(parent))), rom)
        self.assertFalse(stage.verify_installed(bytes(parent)))

    def test_inherited_static_checks_and_mutants(self) -> None:
        import crystal_transition_contract
        import menu_commit_protocol
        import stage_card_palette_handoff
        rom = self.candidate
        # The stage stays clear of these historical contracts' spans.
        self.assertEqual(crystal_transition_contract.verify_transition(rom), "title-port-r443e3")
        menu_commit_protocol.authenticate(rom)
        self.assertTrue(stage_card_palette_handoff.inspect_stage_card_palette_handoff(rom)["installed"])
        for offset in (off(20, 0x6330), off(20, 0x6810), off(20, 0x6E40), off(20, 0x7040),
                       off(20, 0x7A2B), off(1, 0x4AD6), off(13, 0x7188), off(16, 0x7183),
                       off(stage.PRIVATE_BANK, 0x6C85)):
            mutant = bytearray(rom)
            mutant[offset] ^= 0x01
            mutant = bytes(mutant)
            self.assertFalse(stage.verify_installed(mutant), hex(offset))
            self.assertFalse(self.lineage.is_candidate(mutant))


class GateLogicTests(unittest.TestCase):
    def events(self, case: str, post: str | None = None, mode3: bool = False) -> list[dict]:
        bg = "FF7F947E4A3D0000" * 8
        scene, ffbf = (0x0A, 1) if case == "miniboss" else (0x02, 0)
        events = [dict(frame=1, kind="gameplay")]
        if case == "miniboss":
            events.append(dict(frame=2, kind="miniboss", ffbf=1, scene=0x02))
        events += [dict(frame=3, kind="cram", tag="pre-death", bg=bg, obj="", scene=scene, ffbf=ffbf),
                   dict(frame=4, kind="stimulus"), dict(frame=5, kind="death"),
                   dict(frame=6, kind="resume", scene=scene, ffbf=ffbf)]
        for tag in gate.SAMPLES:
            events.append(dict(frame=7, kind="cram", tag=tag, bg=post or bg, obj="", scene=scene, ffbf=ffbf))
        if mode3:
            events.append(dict(frame=8, kind="mode3_write", port=0xFF69, index=0xE7, ly=39, pc=0x71EA))
        events.append(dict(frame=9, kind="done", cram_writes=100))
        return events

    def test_accepts_restored_palettes(self) -> None:
        for case in gate.CASES:
            self.assertEqual(gate.evaluate(case, self.events(case))["status"], "pass")

    def test_rejects_death_fade_and_mode3(self) -> None:
        fade = "7FFF7FFF7FFF7F29" * 8
        with self.assertRaises(gate.GateError):
            gate.evaluate("miniboss", self.events("miniboss", post=fade))
        with self.assertRaises(gate.GateError):
            gate.evaluate("control", self.events("control", mode3=True))
        wrong = self.events("miniboss")
        wrong[-5]["scene"] = 0x02
        with self.assertRaises(gate.GateError):
            gate.evaluate("miniboss", wrong)


if __name__ == "__main__":
    unittest.main()

