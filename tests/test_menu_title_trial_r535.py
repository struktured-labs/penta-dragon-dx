from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import build_menu_title_trial_r535 as combined
import build_title_exit_defer_trial_r535 as title


class MenuTitleTrialTests(unittest.TestCase):
    def test_title_extension_preserves_known_dispatch_hot_paths(self):
        source = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()
        only_title = title.build(source, True, True)
        start = 31 * 0x4000 + 0x2C80
        self.assertEqual(only_title[start:start+0xDA], source[start:start+0xDA])
        self.assertEqual(hashlib.sha256(combined.build(source)).hexdigest(),
                         "69ff940ace8e73e82aa5331dde39282d191814c4ca1b814afb19a13fbb6dc197")

    def test_only_game_start_marker_defers_old_title_cleanup(self):
        source = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()
        candidate = combined.build(source)
        leaf = title.late_clear_patches()[4][2]
        self.assertEqual(leaf, bytes.fromhex("FA 4C DF FE A0 28 08 7E 3D 20 04 AF EA 08 DF 3E 0D C9"))
        for old in range(256):
            for marker in range(256):
                pc, a, zero, writes = 0,0,False,{}
                while True:
                    op = leaf[pc]
                    if op == 0xFA: a,pc = marker,pc+3
                    elif op == 0xFE: zero,pc = a == leaf[pc+1],pc+2
                    elif op == 0x28: pc += 2 + (leaf[pc+1] if zero else 0)
                    elif op == 0x20: pc += 2 + (0 if zero else leaf[pc+1])
                    elif op == 0x7E: a,pc = old,pc+1
                    elif op == 0x3D: a = (a-1)&255;zero,pc = a == 0,pc+1
                    elif op == 0xAF: a,zero,pc = 0,True,pc+1
                    elif op == 0xEA:
                        writes[int.from_bytes(leaf[pc+1:pc+3],"little")] = a
                        pc += 3
                    elif op == 0x3E: a,pc = leaf[pc+1],pc+2
                    elif op == 0xC9: break
                    else: self.fail(f"unknown opcode {op:02X}")
                self.assertEqual(writes, {0xDF08:0} if old == 1 and marker != 0xA0 else {})
                self.assertEqual(a, 13)

    def test_inherited_publisher_binding_is_exact(self):
        from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact
        source = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()
        candidate = combined.build(source)
        self.assertEqual(publication_boundary(candidate)["pc"], 0x7457)
        self.assertTrue(semantic_expansion_is_exact(candidate))
        changed = bytearray(candidate)
        changed[0x14F] ^= 1
        with self.assertRaises(RuntimeError):
            publication_boundary(changed)

    def test_handoff_recognition_is_exact_and_rejects_any_rom_mutation(self):
        from stage_card_palette_handoff import inspect_stage_card_palette_handoff
        source = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()
        candidate = combined.build(source)
        self.assertTrue(inspect_stage_card_palette_handoff(candidate)["installed"])
        for offset in (0x14F, 0x3B42, 31 * 0x4000 + 0x3500, 0x37000):
            changed = bytearray(candidate)
            changed[offset] ^= 1
            self.assertFalse(inspect_stage_card_palette_handoff(changed)["installed"])

    def test_exact_composition_and_title_entry_rearm(self):
        source = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()
        result = combined.build(source)
        wrapper = 13 * 0x4000 + 0x36D7
        self.assertEqual(result[wrapper:wrapper+5], bytes.fromhex("3E 1F CD 47 08"))
        self.assertEqual(result[wrapper+5:wrapper+14], source[wrapper+5:wrapper+14])
        leaf = 13 * 0x4000 + 0x2E9F
        self.assertEqual(result[leaf:leaf+5], bytes.fromhex("AF EA 08 DF C9"))
        self.assertEqual(result[0x3B47:0x3B56], source[0x3B47:0x3B56])

    def test_mux_changes_only_exact_native_post_fade_return(self):
        code = title.late_clear_patches()[2][2]
        for caller in range(65536):
            pc, sp, hl, a, zero = 0, 0xDFDE, 0xDFE2, 0, False
            memory = {sp:0xCD,sp+1:0xAB,sp+2:0x4D,sp+3:0x08,sp+4:caller&255,sp+5:caller>>8}
            for _ in range(20):
                op = code[pc]
                if op == 0xE5:
                    sp -= 2
                    memory[sp],memory[sp+1] = hl & 255,hl >> 8
                    pc += 1
                elif op == 0xE1:
                    hl = memory[sp] | memory[sp+1] << 8
                    sp, pc = sp+2, pc+1
                elif op == 0xF8:
                    hl,pc = sp+code[pc+1],pc+2
                elif op == 0x7E:
                    a,pc = memory[hl],pc+1
                elif op == 0xFE:
                    zero,pc = a == code[pc+1],pc+2
                elif op == 0x20:
                    pc += 2 + (0 if zero else code[pc+1])
                elif op == 0x23:
                    hl,pc = hl+1,pc+1
                elif op == 0xC3:
                    target = int.from_bytes(code[pc+1:pc+3],"little")
                    break
                elif op == 0x3E:
                    a,pc = code[pc+1],pc+2
                elif op == 0xB7:
                    zero,pc = a == 0,pc+1
                elif op == 0xC9:
                    target = None
                    break
                else:
                    self.fail(f"unexpected mux opcode {op:02X}")
            else:
                self.fail("mux did not terminate")
            if caller == 0x3B47:
                self.assertEqual((target,sp,hl), (0x7550,0xDFE0,0xABCD))
            elif caller == 0x76DC:
                self.assertEqual((target,sp,hl), (0x75A0,0xDFE0,0xABCD))
            else:
                self.assertEqual((target,sp,hl,a,zero), (None,0xDFE0,0xABCD,1,False))

    def test_unknown_base_and_invalid_trial_combination_fail(self):
        with self.assertRaises(ValueError):
            combined.build(bytes(0x80000))
        with self.assertRaises(ValueError):
            title.build(bytes(0x80000), False, True)

    def test_title_watchpoints_use_nonempty_half_open_ranges(self):
        probe = (ROOT / "scripts/diagnostics/probe_stage_card_stability.lua").read_text()
        self.assertIn("address, address + 1, C.WATCHPOINT_TYPE.WRITE", probe)
        self.assertIn("0xD880, 0xD881, C.WATCHPOINT_TYPE.WRITE", probe)


if __name__ == "__main__":
    unittest.main()
