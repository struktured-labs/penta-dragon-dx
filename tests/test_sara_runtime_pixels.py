import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from check_sara_runtime_pixels import STATE_BYTES, VIDEO_BYTES, compare_frame


class SaraRuntimePixels(unittest.TestCase):
    def fixture(self):
        state=bytearray(STATE_BYTES)
        state[0x3b7]=2; state[0x3c1]=1; state[0x340]=0x82
        state[0x5c80]=10  # combat transient scene, not a reason to omit
        state[0x260:0x264]=bytes((16,8,32,0))
        state[0x400+32*16]=0x80
        state[0x116:0x118]=bytes((31,0))
        video=bytearray(VIDEO_BYTES); video[:3]=bytes((255,0,0))
        return state,video

    def test_runtime_art_and_alias_are_checked(self):
        state,video=self.fixture()
        self.assertEqual(compare_frame(state,video),('checked',1,[]))
        video[0]=0
        self.assertEqual(len(compare_frame(state,video)[2]),1)

    def test_bank1_art_and_flip(self):
        state,video=self.fixture()
        state[0x263]=0x28
        state[0x400+32*16]=0
        state[0x2400+32*16]=1
        self.assertEqual(compare_frame(state,video),('checked',1,[]))

    def test_unsupported_and_absent_not_counted_as_pixel_pass(self):
        state,video=self.fixture(); state[0x263]=0x80
        self.assertEqual(compare_frame(state,video)[0],'priority_requires_background_composition')
        state[0x263]=0; state[0x340]|=4
        self.assertEqual(compare_frame(state,video)[0],'unsupported_lcdc')
        state[0x340]=0x82;state[0x260]=0
        self.assertEqual(compare_frame(state,video),('no_opaque_sara_pixels',0,[]))


if __name__=='__main__': unittest.main()
