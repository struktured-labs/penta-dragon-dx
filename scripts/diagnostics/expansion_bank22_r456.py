"""Independent source composition of Stage7 and Stage4 bank22 services."""
from pathlib import Path
import sys,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
import audit_stage7_dual_plane_hdma_r264 as audit
import build_stage7_visible_rows_r271 as rows
import build_stage7_pointer_advance_r278 as pointer
import build_stage7_lazy_disarm_r279 as disarm
import build_stage4_lazy_departure_r286 as stage4
import build_stage4_delay_trim_r344 as delay
import build_stage1_selector_latch_relocation_r316 as latch
from analyze_later_attr_signature import semantic_lut


def expected_bank22():
    image=bytearray(b'\xff'*16384)
    def put(addr,code):image[addr-0x4000:addr-0x4000+len(code)]=code
    def patch(addr,old,new):
        assert len(old)==len(new) and image[addr-0x4000:addr-0x4000+len(old)]==old,hex(addr)
        put(addr,new)
    helper,labels=audit.build_helper();put(0x6C80,helper)
    for pos in (0x0F,0x569):patch(0x6C80+pos,bytes.fromhex('F0C1FE01C2'),bytes.fromhex('F0C1FE02D2'))
    patch(0x6CF5,b'\x18',bytes([rows.VISIBLE_ROWS]))
    cleanup=labels['phase1_service']-6
    patch(0x705A,bytes.fromhex('1198C3'),bytes([0xC3,cleanup&255,cleanup>>8]))
    patch(0x712F,b'\xaf',bytes([rows.ATTR_HDMA_COMMAND]))
    patch(0x713C,b'\x2f',bytes([rows.ATTR_GDMA_COMMAND]))
    patch(0x715C,b'\x18',bytes([rows.VISIBLE_ROWS]))
    # r273 skips invisible row padding; r278 then shortens its carry path.
    patch(pointer.POINTER_ADVANCE_ADDR,bytes.fromhex('AF2222222222222222'),pointer.OLD_POINTER_ADVANCE)
    patch(pointer.POINTER_ADVANCE_ADDR,pointer.OLD_POINTER_ADVANCE,pointer.NEW_POINTER_ADVANCE)
    patch(disarm.FIRST_GUARD_OPERAND_ADDR,disarm.OLD_GUARD_TARGET,disarm.FIRST_GUARD_TARGET)
    patch(disarm.SECOND_GUARD_OPERAND_ADDR,disarm.OLD_GUARD_TARGET,disarm.SECOND_GUARD_TARGET)
    patch(disarm.DISARM_CAVE_ADDR,disarm.OLD_CAVE,disarm.DISARM+disarm.CLASSIFIER)
    put(0x7500,audit.build_descriptors());put(0x7600,bytes(semantic_lut(7)))
    put(stage4.INSTALLER_ADDR,stage4.build_installer())
    put(stage4.WRAM_PAYLOAD_ADDR,stage4.build_wram_block())
    put(stage4.TRAMPOLINE_PAYLOAD_ADDR,stage4.TRAMPOLINE)
    put(stage4.r285.STAGE4_BANK22_LANDING_ADDR,bytes([0xC3,stage4.INSTALLER_ADDR&255,stage4.INSTALLER_ADDR>>8]))
    patch(delay.CALL_SOURCE_ADDR,delay.OLD_CALL,delay.NEW_CALL)
    for addr,op in ((0x7120,0xF0),(0x7171,0xF0),(0x719C,0xF0),(0x71A2,0xE0),(0x71C6,0xF0),(0x71CC,0xE0),(0x720C,0xF0)):
        patch(addr,bytes([op,0xA5]),bytes([op,1]))
    return bytes(image)


if __name__=='__main__':
    expected=expected_bank22()
    actual=Path(sys.argv[1]).read_bytes()[22*16384:23*16384]
    diffs=[(hex(0x4000+i),hex(a),hex(e)) for i,(a,e) in enumerate(zip(actual,expected)) if a!=e]
    print(hashlib.sha256(expected).hexdigest(),len(diffs),diffs[:30])
