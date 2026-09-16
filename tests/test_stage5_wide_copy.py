import hashlib
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))

import stage5_wide_copy as stage5


class Stage5WideCopyTest(unittest.TestCase):
    def test_speed_probe_authenticates_both_private_copies(self):
        probe = (ROOT / "scripts/diagnostics/probe_stage_speed.lua").read_text()
        self.assertIn("function penta_in_stage5_wide_copy()", probe)
        self.assertIn("emu:read8(0xFF99) == 0x15", probe)
        self.assertIn("and emu:read8(0x42B7) == 0xC3", probe)
        self.assertIn("and emu:read8(0x6D04) == 0x41", probe)
        self.assertIn("function penta_in_stage1_native_copy()", probe)
        self.assertIn("emu:read8(0xFF99) == 0x16", probe)
        self.assertIn("function penta_in_stage7_private_copy()", probe)
        self.assertIn("function penta_in_stage7_fused_copy()", probe)
        self.assertIn("emu:read8(0xFF99) == 0x17", probe)
        self.assertIn("emu:read8(0x7093) == 0x11", probe)
        self.assertIn("penta_has_stage7_private_copy = TARGET == 6", probe)
        self.assertIn('"stage7_fused_copy_hits": %d', probe)
        self.assertIn("if penta_has_stage5_wide_copy then", probe)
        self.assertIn("end, 0x6D00)", probe)

    def test_dispatch_and_router_are_exact(self):
        self.assertEqual(stage5.build_dispatch_fragments(), {
            0x0013: bytes.fromhex("F0 BA 00 18 0C"),
            0x0024: bytes.fromhex("E6 FB 18 03"),
            0x002B: bytes.fromhex("C2 95 42 18 0C"),
            0x003C: bytes.fromhex("3E 15 18 CD"),
            0x000D: bytes.fromhex("C3 47 08"),
        })
        self.assertEqual(
            stage5.build_dispatch_fragments(stage7_pure_six=True)[0x0024],
            bytes.fromhex("E6 01 18 03"),
        )
        self.assertEqual(
            stage5.build_dx_completion(),
            bytes.fromhex(
                "E0 FF 3E 01 BF F5 C5 D5 E5 21 CC 06 E5 3E 01 C3 61 00"
            ),
        )
        self.assertEqual(
            stage5.build_native_completion(),
            bytes.fromhex("F5 C5 D5 E5 21 A1 03 E5 3E 01 C3 61 00"),
        )
        self.assertEqual(stage5.build_dx_early_branch(), bytes.fromhex("18 7F"))
        self.assertEqual(
            stage5.build_dx_early_completion(),
            bytes.fromhex("F5 C5 D5 E5 21 CC 06 E5 3E 01 C3 61 00"),
        )
        self.assertEqual(
            stage5.build_router(stage5_wide=True),
            bytes.fromhex(
                "33 33 F0 BA B7 28 21 FE 04 28 26 "
                "FA 0B DC 3C E6 01 EA 0B DC 28 09 "
                "3E 01 21 A0 42 E5 C3 61 00 "
                "3E 01 21 A5 42 E5 C3 61 00 "
                "3E 16 21 95 42 E5 C3 61 00 C3 95 42"
            ),
        )
        self.assertEqual(
            stage5.build_router(stage5_wide=False),
            bytes.fromhex(
                "33 33 F0 BA B7 28 1D "
                "FA 0B DC 3C E6 01 EA 0B DC 28 09 "
                "3E 01 21 A0 42 E5 C3 61 00 "
                "3E 01 21 A5 42 E5 C3 61 00 "
                "3E 16 21 95 42 E5 C3 61 00"
            ),
        )
        self.assertEqual(
            stage5.build_router(stage5_wide=True, stage7_pure_six=True),
            bytes.fromhex(
                "33 33 F0 BA B7 28 25 FE 04 28 2A FE 06 28 29 "
                "FA 0B DC 3C E6 01 EA 0B DC 28 09 "
                "3E 01 21 A0 42 E5 C3 61 00 "
                "3E 01 21 A5 42 E5 C3 61 00 "
                "3E 16 21 95 42 E5 C3 61 00 C3 95 42 "
                "3E 17 21 95 42 E5 C3 61 00"
            ),
        )

    def test_copy_sequence_rejoins_canonical_semantic_tail(self):
        code = stage5.build_wide_copy()
        self.assertEqual(code[-5:], bytes.fromhex("0E 00 C3 EC 42"))
        replayable = bytearray(code)
        replayable[-5:] = bytes.fromhex("0E 00 3E 01 C9")
        self.assertEqual(
            stage5.model_new(bytes(replayable), org=stage5.WIDE_COPY_ADDR),
            stage5.model_old(),
        )
        self.assertEqual(stage5.STAGE5_TAIL_WAIT_GROUPS, 0)

    def test_stage7_copy_sequence_and_timing_proof(self):
        code, evidence = stage5.build_stage7_fast_copy()
        self.assertEqual(code[-5:], bytes.fromhex("0E 00 C3 EC 42"))
        replayable = bytearray(code)
        replayable[-5:] = bytes.fromhex("0E 00 3E 01 C9")
        self.assertEqual(
            stage5.model_new(
                bytes(replayable), org=stage5.STAGE7_FAST_COPY_ADDR
            ),
            stage5.model_old(),
        )
        self.assertEqual(evidence, {
            "groups": 96,
            "cells": 576,
            "page_crossing_groups": 1,
            "maximum_critical_cycles": 41,
        })
        self.assertEqual(
            stage5.build_stage7_dispatch(),
            bytes.fromhex("F0 40 07 DA 00 6D C3 B7 42"),
        )

    def test_stage7_fused_dirty_helper_rejoins_current_tail(self):
        helper, fused_entry, fast, fast_entry, evidence = (
            stage5.build_stage7_fused_copies()
        )
        self.assertEqual(len(helper), 1043)
        self.assertEqual(fused_entry, 0x6EA2)
        self.assertEqual(fast_entry, 0x7093)
        self.assertEqual(fast_entry + len(fast), 0x7D45)
        self.assertEqual(helper[-5:], bytes.fromhex("0E 00 C3 EC 42"))
        self.assertEqual(fast[-5:], bytes.fromhex("0E 00 C3 EC 42"))
        self.assertEqual(evidence["maximum_critical_cycles"], 41)
        self.assertEqual(
            stage5.build_stage7_fused_dispatch(fast_entry),
            bytes.fromhex("F0 40 07 DA 93 70 C3 B7 42"),
        )
        self.assertEqual(
            stage5.build_stage7_fused_branch(fused_entry),
            bytes.fromhex("CA 00 6C CD 13 DA 11 A0 C1 0E 41 C3 A2 6E"),
        )

    def test_install_scope_and_clones(self):
        rom = bytearray([0xFF]) * (32 * stage5.BANK_SIZE)
        for call_site in stage5.CALL_SITES:
            rom[call_site:call_site + 3] = stage5.CALL_PREIMAGE
        for address, preimage in stage5.DISPATCH_FRAGMENT_PREIMAGES.items():
            rom[address:address + len(preimage)] = preimage
        for address, fence in stage5.VECTOR_FENCES.items():
            rom[address:address + len(fence)] = fence
        rom[
            stage5.MAPPER_WRAPPER_ADDR:
            stage5.MAPPER_WRAPPER_ADDR + len(stage5.MAPPER_WRAPPER)
        ] = stage5.MAPPER_WRAPPER
        for offset, opcode, target in stage5.REVIEWED_DATA_FALSE_MENTIONS:
            rom[offset:offset + 3] = bytes([
                opcode, target & 0xFF, target >> 8,
            ])
        rom[
            stage5.FIXED_POP_RET_ADDR:
            stage5.FIXED_POP_RET_ADDR + len(stage5.FIXED_POP_RET)
        ] = stage5.FIXED_POP_RET
        rom[
            stage5.FIXED_POP_RETI_ADDR:
            stage5.FIXED_POP_RETI_ADDR + len(stage5.FIXED_POP_RETI)
        ] = stage5.FIXED_POP_RETI
        dx_copy = bytearray(
            stage5.DX_COPY_END - stage5.DX_COPY_ADDR
        )
        dx_copy[:len(stage5.DX_ENTRY_PREIMAGE)] = stage5.DX_ENTRY_PREIMAGE
        hook = stage5.DX_TILE_LOOP_ADDR - stage5.DX_COPY_ADDR
        dx_copy[hook:hook + 3] = bytes.fromhex("11 A0 C1")
        pure_branch = stage5.DX_PURE_BRANCH_ADDR - stage5.DX_COPY_ADDR
        dx_copy[pure_branch:pure_branch + 7] = bytes.fromhex(
            "28 05 CD 13 DA 18 00"
        )
        early_return = stage5.DX_EARLY_RETURN_ADDR - stage5.DX_COPY_ADDR
        dx_copy[early_return:early_return + 2] = bytes.fromhex("FB C9")
        dx_copy[-6:] = bytes.fromhex("E0 FF 3E 01 BF D9")
        rom[stage5.DX_COPY_ADDR:stage5.DX_COPY_END] = dx_copy
        before = bytes(rom)
        dx_sha256 = hashlib.sha256(dx_copy).hexdigest()
        with mock.patch.object(stage5, "DX_COPY_SHA256", dx_sha256):
            report = stage5.install(rom, stage7_pure_six=True)
        self.assertEqual(report.windows_per_publication, 120)
        self.assertEqual(report.stage7_pure_windows, 96)
        self.assertEqual(report.stage7_maximum_critical_cycles, 41)

        router_offset = stage5.bank_offset(
            stage5.ROUTER_BANK, stage5.ROUTER_ADDR
        )
        self.assertEqual(
            rom[
                router_offset:
                router_offset + len(stage5.build_router(
                    stage7_pure_six=True
                ))
            ],
            stage5.build_router(stage7_pure_six=True),
        )
        clone_hook = stage5.bank_offset(
            stage5.ROUTER_BANK, stage5.DX_TILE_LOOP_ADDR
        )
        self.assertEqual(rom[clone_hook:clone_hook + 3], bytes.fromhex("C3 00 6D"))
        clone_tail = stage5.bank_offset(
            stage5.ROUTER_BANK, stage5.DX_COPY_END - 6
        )
        self.assertEqual(
            rom[clone_tail:clone_tail + len(stage5.build_dx_completion())],
            stage5.build_dx_completion(),
        )
        early_branch = stage5.bank_offset(
            stage5.ROUTER_BANK, stage5.DX_EARLY_RETURN_ADDR
        )
        self.assertEqual(
            rom[early_branch:early_branch + 2],
            stage5.build_dx_early_branch(),
        )
        early_completion = stage5.bank_offset(
            stage5.ROUTER_BANK, stage5.DX_EARLY_COMPLETION_ADDR
        )
        self.assertEqual(
            rom[
                early_completion:
                early_completion + len(stage5.build_dx_early_completion())
            ],
            stage5.build_dx_early_completion(),
        )
        native = stage5.NATIVE_ROM.read_bytes()[
            stage5.DX_COPY_ADDR:stage5.NATIVE_COPY_END
        ]
        native_offset = stage5.bank_offset(
            stage5.NATIVE_STAGE1_BANK, stage5.DX_COPY_ADDR
        )
        self.assertEqual(
            rom[native_offset:native_offset + len(native) - 1],
            native[:-1],
        )
        native_completion = stage5.bank_offset(
            stage5.NATIVE_STAGE1_BANK, stage5.NATIVE_COPY_END - 1
        )
        self.assertEqual(
            rom[
                native_completion:
                native_completion + len(stage5.build_native_completion())
            ],
            stage5.build_native_completion(),
        )
        stage7_branch = stage5.bank_offset(
            stage5.STAGE7_BANK, stage5.DX_PURE_BRANCH_ADDR
        )
        self.assertEqual(
            rom[stage7_branch:stage7_branch + 7],
            bytes.fromhex("CA 80 6C CD 13 DA 00"),
        )
        stage7_dispatch = stage5.bank_offset(
            stage5.STAGE7_BANK, stage5.STAGE7_DISPATCH_ADDR
        )
        self.assertEqual(
            rom[
                stage7_dispatch:
                stage7_dispatch + len(stage5.build_stage7_dispatch())
            ],
            stage5.build_stage7_dispatch(),
        )
        stage7_fast = stage5.bank_offset(
            stage5.STAGE7_BANK, stage5.STAGE7_FAST_COPY_ADDR
        )
        fast, _ = stage5.build_stage7_fast_copy()
        self.assertEqual(rom[stage7_fast:stage7_fast + len(fast)], fast)

        allowed = {
            offset
            for address, preimage in stage5.DISPATCH_FRAGMENT_PREIMAGES.items()
            for offset in range(address, address + len(preimage))
        }
        for call_site in stage5.CALL_SITES:
            allowed.update(range(call_site, call_site + len(stage5.CALL_PATCH)))
        allowed.update(range(
            stage5.ROUTER_BANK * stage5.BANK_SIZE,
            (stage5.ROUTER_BANK + 1) * stage5.BANK_SIZE,
        ))
        allowed.update(range(
            stage5.NATIVE_STAGE1_BANK * stage5.BANK_SIZE,
            (stage5.NATIVE_STAGE1_BANK + 1) * stage5.BANK_SIZE,
        ))
        allowed.update(range(
            stage5.STAGE7_BANK * stage5.BANK_SIZE,
            (stage5.STAGE7_BANK + 1) * stage5.BANK_SIZE,
        ))
        changed = {
            index for index, (old, new) in enumerate(zip(before, rom))
            if old != new
        }
        self.assertTrue(changed <= allowed)
        self.assertEqual(
            rom[stage5.DX_COPY_ADDR:
                stage5.DX_COPY_ADDR + len(stage5.DX_ENTRY_PREIMAGE)],
            stage5.DX_ENTRY_PREIMAGE,
        )

        fused_rom = bytearray(before)
        with mock.patch.object(stage5, "DX_COPY_SHA256", dx_sha256):
            fused_report = stage5.install(
                fused_rom,
                stage7_pure_six=True,
                stage7_fused_dirty=True,
            )
        self.assertEqual(fused_report.stage7_pure_windows, 96)
        self.assertEqual(fused_report.stage7_dirty_windows, 144)
        self.assertEqual(fused_report.stage7_fused_entry, 0x6EA2)
        self.assertEqual(fused_report.stage7_fast_entry, 0x7093)
        fused_branch = stage5.bank_offset(
            stage5.STAGE7_BANK, stage5.DX_PURE_BRANCH_ADDR
        )
        self.assertEqual(
            fused_rom[fused_branch:fused_branch + 14],
            stage5.build_stage7_fused_branch(0x6EA2),
        )
        helper, _, fast, fast_entry, _ = stage5.build_stage7_fused_copies()
        helper_offset = stage5.bank_offset(
            stage5.STAGE7_BANK, stage5.STAGE7_FUSED_HELPER_ADDR
        )
        self.assertEqual(
            fused_rom[helper_offset:helper_offset + len(helper)], helper
        )
        fast_offset = stage5.bank_offset(stage5.STAGE7_BANK, fast_entry)
        self.assertEqual(fused_rom[fast_offset:fast_offset + len(fast)], fast)


if __name__ == "__main__":
    unittest.main()
