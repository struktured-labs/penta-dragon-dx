from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_stage7_room_commit_wait_r419 as b
class RoomWaitTests(unittest.TestCase):
    def test_dispatch_and_interrupt_balance(self):
        for stage in range(7):
            for room,nxt in [(1,0),(1,1),(1,3),(3,1),(0,255)]:
                pc=0;a=bb=0;z=False;ime=False;reads=0;enabled=False
                for _ in range(100):
                    op=b.TAIL[pc];pc+=1
                    if op==0xF0:
                        port=b.TAIL[pc];pc+=1
                        if port==0xC4:
                            self.assertTrue(ime);reads+=1;a=0x40 if reads<3 else 0
                        else:a={0xBA:stage,0xCE:nxt,0xBD:room}[port]
                    elif op==0xFE:z=a==b.TAIL[pc];pc+=1
                    elif op==0xB7:z=a==0
                    elif op==0xB8:z=a==bb
                    elif op==0x47:bb=a
                    elif op==0xC0:
                        if not z:break
                    elif op==0xC8:
                        if z:break
                    elif op==0xFB:ime=True;enabled=True
                    elif op==0xF3:ime=False
                    elif op==0xCB:self.assertEqual(b.TAIL[pc],0x77);pc+=1;z=not(a&64)
                    elif op==0x20:
                        delta=b.TAIL[pc];pc+=1
                        if not z:pc+=delta-256 if delta>127 else delta
                    elif op==0xC9:break
                    else:self.fail(hex(op))
                else:self.fail('loop did not finish')
                self.assertEqual(enabled,stage==6 and nxt!=0 and nxt!=room)
                self.assertFalse(ime)
    def test_original_packer_except_return_unchanged(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(rom[b.PACK_OFFSET:b.PACK_OFFSET+len(b.PACK)-1],b.PACK[:-1])
        allowed=set(range(b.PACK_OFFSET+len(b.PACK)-1,b.PACK_OFFSET+len(b.PACK)-1+len(b.TAIL)))|{0x14D,0x14E,0x14F}
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))
if __name__=='__main__':unittest.main()
