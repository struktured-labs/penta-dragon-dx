"""Conservative normal-speed budget from mode-0 start through last VRAM write.

Assume a minimum 87-dot HBlank followed by 80-dot OAM scan. Polling must
observe mode 3 first, then find mode 0 within its minimum duration. Include
a full poll period of phase uncertainty and a source-page crossing.
"""
import unittest


class WideCopyBudget(unittest.TestCase):
    def test_slow_six_tile_poll_exceeds_budget(self):
        writable_mcycles=(87+80)/4
        group=6*(2+1+2)+1  # LD A,(DE); INC E; LD(HL+),A; one INC DE
        old_period=3+2+3  # LDH; AND; taken JR
        old_after_sample=2+2  # AND; untaken JR, after read
        self.assertGreater(old_period+old_after_sample+group,writable_mcycles)

    def test_carry_poll_steady_state_only_fits(self):
        period=3+1+3  # LDH; RRCA; taken JR
        after_sample=1+2
        group=6*(2+1+2)+1
        self.assertLessEqual(period+after_sample+group,(87+80)/4)
        self.assertLess(period,87/4)  # cannot skip all of mode 0

    def test_first_sample_after_mode3_gate_needs_five_tiles(self):
        first_sample_delay=2+2+2+3  # AND; CP; untaken JR; next LDH
        after_sample=1+2  # RRCA and untaken JR
        self.assertGreater(first_sample_delay+after_sample+31,(87+80)/4)
        self.assertLessEqual(first_sample_delay+after_sample+26,(87+80)/4)
