"""Reconstruct the bank23 DMA dispatcher and relocated palette data from source."""
from pathlib import Path
import sys,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
from build_deferred_dma_pipeline_r397 import Asm,sync_wait_dma
from build_later_stage_deferred_dma_r443 import SYNC_PREFIX
from compose_boss_sync_dma_r454 import service as domain_guard
from compose_arena_palette_storage_r455 import dispatch,loader,TABLE_BUILDERS
from build_stage1_timer_safe_gdma_r370 import SERVICE_CODE
from build_interrupt_checked_vblank_r373 import OLD_WAIT
from build_six_line_dma_r403 import WAIT


def expected_bank23():
    image=bytearray(b'\xff'*16384)
    def put(address,code):image[address-0x4000:address-0x4000+len(code)]=code
    put(0x6C80,bytes.fromhex('C3006E')+bytes(7))
    put(0x6C8A,bytes.fromhex('C3206D')+bytes(len(SYNC_PREFIX)-3))
    put(0x6C8A+len(SYNC_PREFIX),SERVICE_CODE.replace(OLD_WAIT,WAIT))
    put(0x6D20,domain_guard());put(0x6E00,dispatch());put(0x6E40,loader())
    for page,fn in TABLE_BUILDERS.items():put(page<<8,bytes(fn()))
    return bytes(image)


if __name__=='__main__':
    expected=expected_bank23()
    actual=Path(sys.argv[1]).read_bytes()[23*16384:24*16384]
    diffs=[(hex(0x4000+i),hex(a),hex(e)) for i,(a,e) in enumerate(zip(actual,expected)) if a!=e]
    print(hashlib.sha256(expected).hexdigest(),len(diffs),diffs[:40])
