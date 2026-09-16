"""Full source reconstruction; CLI comparison is separate from expectation."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
import build_stage2_runtime_sparse_r255 as r255
import build_stage2_runtime_sparse_r256 as r256
import build_stage2_runtime_unrolled_r257 as r257
import build_stage2_runtime_hdma6_r260 as r260
import build_stage2_isolated_entry_r263 as r263
import build_stage2_seven_rows_r441 as r441
import build_exact_source_dirty_r385 as r385
import build_conditional_lut_invalidation_r386 as r386
import build_stage1_subscene_tracking_r442 as r442
import build_v302_title_fix as palettes
import stage_card_palette_handoff as card
import build_stage1_split_phase_key_r209 as r209
import build_stage1_room01_atomic_wall_r298 as r298
import build_room_writer_wait_r420 as r420


def expected_bank21():
    image=bytearray(b'\xff'*16384)
    def put(addr,code): image[addr-0x4000:addr-0x4000+len(code)]=code
    put(0x4300,(r256.PROLOGUE+r255.build_sparse_helper()).replace(bytes.fromhex('F0A5'),bytes.fromhex('F001')))
    put(r255.RESTORE_ENTRY,r255.build_restore_helper())
    put(r255.ORIGINAL_BLOB,r255.original_row_helper())
    special=r260.build_runtime().replace(bytes.fromhex('F0A5'),bytes.fromhex('F001'))
    put(r255.SPECIAL_BLOB,special+bytes(len(r255.build_special_runtime())-len(special)))
    put(0x4C00,b'\xc1'+r257.build_full_helper())
    entry=r263.build_stage2_entry(len(r255.build_special_runtime()))
    put(r255.RARE_ENTRY,entry+bytes(len(r255.build_rare_entry(len(r255.build_special_runtime())))-len(entry)))
    put(r260.PUBLISH_ENTRY,r260.build_publisher().replace(bytes.fromhex('F0A5'),bytes.fromhex('F001')))
    for offset,old,new in r441.patches():
        start=offset-21*16384
        assert image[start:start+len(old)]==old
        image[start:start+len(new)]=new
    put(0x4100,r442.NEW+r385.decider()[5:])
    put(0x7D00,r386.CODE)
    path=ROOT/'palettes/penta_palettes_v097.yaml'
    data=bytes(palettes.load_palettes_from_yaml(path)['bg_data'])
    bg0=data[:8]
    title,_=palettes.load_title_bg_palette(path,data)
    index=card._choose_discriminator(bg0,title)
    put(0x4000,card._build_private_helper(bg0,index,title[index]))
    put(0x7E00,r209.build_private_decider())
    wall=bytearray(r298.WALL_HELPER)
    assert wall[16:16+len(r386.OLD)]==r386.OLD
    wall[16:16+len(r386.OLD)]=bytes.fromhex('CD007D')+bytes(len(r386.OLD)-3)
    assert wall[:3]==bytes.fromhex('E5F0BA')
    wall[:3]=bytes.fromhex('C3C06C')
    put(0x6C80,wall)
    put(0x6CC0,r420.CODE)
    return bytes(image)


if __name__=='__main__':
    expected=expected_bank21()
    actual=Path(sys.argv[1]).read_bytes()[21*16384:22*16384]
    diffs=[(hex(0x4000+i),hex(a),hex(e)) for i,(a,e) in enumerate(zip(actual,expected)) if a!=e]
    print('Residuals',len(diffs),diffs[:150])
    assert actual==expected
