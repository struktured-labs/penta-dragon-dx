from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_room1_deferred_r400 as b
from verify_stage1_spike_palettes import publication_boundary


def prefix(stage,room):
    code=b.PREFIX;pc=0;a=0;z=False
    while pc<len(code):
        op=code[pc];pc+=1
        if op==0xF0:a={0xBA:stage,0xBD:room}[code[pc]];pc+=1
        elif op==0xB7:z=a==0
        elif op==0xFE:z=a==code[pc];pc+=1
        elif op==0x20:
            d=code[pc];pc+=1
            if not z:pc+=d
        elif op==0x3E:a=code[pc];pc+=1
        elif op==0xC9:
            assert a==1 and z
            return True
        else:raise AssertionError(hex(op))
    assert pc==len(code)
    return False


class RoomGateTests(unittest.TestCase):
    def test_all_stage_room_pairs(self):
        for stage in range(256):
            for room in range(256):
                self.assertEqual(prefix(stage,room),stage==0 and room==1)

    def test_scope_and_full_rom_identity(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(publication_boundary(rom)['variant'],'r400-room1-deferred-df6fffb1')
        self.assertEqual(rom[0x4351:0x4357],bytes.fromhex('CA 57 43 CD F1 DB'))
        self.assertEqual(rom[0x42ED:0x42FB],source[0x42ED:0x42FB])
        allowed=set(range(23*0x4000+0x2C80,23*0x4000+0x2D00))
        allowed.update(range(24*0x4000+0x2E00,24*0x4000+0x2E50))
        allowed.update(range(0x4351,0x4357));allowed.update((0x14D,0x14E,0x14F))
        self.assertTrue({i for i,(x,y) in enumerate(zip(source,rom)) if x!=y}<=allowed)


if __name__=='__main__':unittest.main()
