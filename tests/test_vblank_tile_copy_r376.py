import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_vblank_tile_copy_r376 as patch


def run(scene,ly):
    code=patch.HELPER; pc=0; a=0; zero=False; ime=True; stats=[]
    stat_reads=iter((2,3,3,0))
    for _ in range(60):
        op=code[pc];pc+=1
        if op==0xF3:ime=False
        elif op==0xFA:
            assert code[pc:pc+2]==bytes.fromhex('80 D8');pc+=2;a=scene
        elif op==0xF0:
            addr=code[pc];pc+=1
            if addr==0x44:a=ly
            else:
                assert addr==0x41;a=next(stat_reads);stats.append(a)
        elif op==0xE6:a &= code[pc];pc+=1;zero=a==0
        elif op==0xFE:zero=a==code[pc];pc+=1
        elif op in (0x20,0x28):
            d=code[pc];pc+=1
            if (op==0x20 and not zero) or (op==0x28 and zero):pc+=d if d<128 else d-256
        elif op==0xC3:
            assert code[pc:pc+2]==bytes.fromhex('CF 42')
            return ime,stats
        else:raise AssertionError(hex(op))
    raise AssertionError('no completion')


class TileCopyTests(unittest.TestCase):
    def test_only_early_stage1_vblank_bypasses_original_wait(self):
        for scene in (0,2,3,7,11):
            for ly in range(154):
                ime,stats=run(scene,ly)
                self.assertFalse(ime)
                self.assertEqual(stats,[] if scene==2 and 144<=ly<=151 else [2,3,3,0])

    def test_exact_owned_ranges_and_unmodified_write_group(self):
        source=patch.BASE.read_bytes();rom=patch.build(source)
        allowed=set(range(patch.ENTRY,patch.ENTRY+len(patch.OLD)))
        allowed.update(range(patch.CAVE,patch.CAVE+len(patch.HELPER)))
        allowed.update((0x14D,0x14E,0x14F))
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(source,rom))))
        self.assertEqual(rom[0x42CF:0x42DB],bytes.fromhex('1A 13 22')*4)
        self.assertEqual(rom[0x432D:0x4330],bytes.fromhex('C3 54 43'))


if __name__=='__main__':unittest.main()
