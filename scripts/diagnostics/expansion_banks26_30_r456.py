"""Independent source-generated banks 26..30; candidate read only by CLI check."""
import hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
from build_aligned_tile_dma_r432 import service as tile_copy
from build_stationary_copy_r415 import HELPER as stationary
from compose_stage1_wide_copy_r445 import emit,PATTERNS
from build_stage1_coordinate_wait_r427 import CODE as coordinate
from build_stage1_precompile_wall_r309 import HELPER as wall
from build_stage1_bulk_context_r426 import service as bulk


def expected_banks():
    banks={b:bytearray(b'\xff'*16384) for b in range(26,31)}
    def put(b,address,code):
        start=address-0x4000
        assert banks[b][start:start+len(code)]==b'\xff'*len(code)
        banks[b][start:start+len(code)]=code
    put(26,0x6C80,tile_copy())
    put(27,0x6C80,stationary)
    put(28,0x6C80,emit(PATTERNS['5'],exit_c0=True,r5_table=None,class_gate=True,ei_gap=True,fused=True))
    put(29,0x6C80,coordinate)
    assert wall.count(bytes.fromhex('F0BD'))==1 and wall.endswith(bytes.fromhex('3E01C9'))
    code=wall.replace(bytes.fromhex('F0BD'),bytes.fromhex('F0E5'))[:-3]+bytes.fromhex('C3006D')
    put(30,0x6C80,code)
    put(30,0x6D00,bulk())
    return {b:bytes(v) for b,v in banks.items()}


if __name__=='__main__':
    banks=expected_banks()
    candidate=Path(sys.argv[1]).read_bytes()
    for b,expected in banks.items():
        actual=candidate[b*16384:(b+1)*16384]
        differences=[hex(0x4000+i) for i,(a,e) in enumerate(zip(actual,expected)) if a!=e]
        print(b,hashlib.sha256(expected).hexdigest(),len(differences),differences[:10])
        assert actual==expected
