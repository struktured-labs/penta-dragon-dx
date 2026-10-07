import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from build_later_lowhealth_dispatch import OLD,NEW,build
from check_lowhealth_stage2_attributes import assess


def execute(code,raw,canonical):
    # Execute the resolver's exact bounded instruction sequence (RET is split).
    assert code[:8]==bytes.fromhex('FA80D8FE0BC0F0B7')
    assert code[8::2]==bytes.fromhex('D6FE383EC6')
    if raw!=11:return raw
    a=(canonical-code[9])&255
    if a>=code[11]:a=code[15]
    return (a+code[17])&255


class LowHealthDispatch(unittest.TestCase):
    def test_all_scene_and_canonical_inputs(self):
        for raw in range(256):
            for canonical in range(256):
                expected=raw if raw!=11 else canonical if 3<=canonical<=20 else 11
                self.assertEqual(execute(NEW,raw,canonical),expected)
                if raw!=11 or not 3<=canonical<=10:
                    self.assertEqual(execute(NEW,raw,canonical),execute(OLD,raw,canonical))

    def test_only_immediates_changed(self):
        self.assertEqual([i for i,(a,b) in enumerate(zip(OLD,NEW)) if a!=b],[9,11,15,17])
        self.assertEqual(len(OLD),len(NEW))

    def test_wrong_parent_rejected(self):
        with self.assertRaises(ValueError):build(bytes(1048576))

    def fixture(self):
        raw=bytearray(71680)
        raw[0x5C80],raw[0x3BA],raw[0x3B7]=11,1,3
        for tile in (0xAE,0xAF,0xBE,0xBF,0xC6,0xC7,0xD6,0xD7):raw[0x4A00+tile]=2
        return raw

    def test_neutral_maps_pass(self):self.assertTrue(assess(self.fixture())['passed'])

    def test_stale_boss_attribute_fails_even_if_palettes_match(self):
        raw=self.fixture();raw[0x4000]=4
        with self.assertRaisesRegex(ValueError,'stale/missing'):assess(raw)

    def test_missing_pickup_color_fails(self):
        raw=self.fixture();raw[0x1C00]=0xAE
        with self.assertRaisesRegex(ValueError,'stale/missing'):assess(raw)
        raw[0x3C00]=2
        self.assertTrue(assess(raw)['passed'])

    def test_wrong_scene_and_policy_fail(self):
        raw=self.fixture();raw[0x5C80]=3
        with self.assertRaises(ValueError):assess(raw)
        raw=self.fixture();raw[0x4AAE]=0
        with self.assertRaises(ValueError):assess(raw)


if __name__=='__main__':unittest.main()
