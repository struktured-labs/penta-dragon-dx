"""Source title/ISR generators plus the checked-in title text layout."""
from pathlib import Path
import hashlib,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
import build_title_nightfall_port as title
from build_later_stage_deferred_dma_r443 import isr_service
from build_v302_title_fix import map_title_string_to_tiles,TITLE_FOOTER


def expected_bank25():
    # build_v302_title_fix title-list construction, with the parser's +1
    # row/column translation. No candidate or saved title image is read.
    txt=lambda s:[0 if c==' ' else 0x80+ord(c)-65 for c in s]
    records=[(4,8,[0xC1,0xC2,0xC3,0xC4,0xC5]),
             (5,8,[0xD1,0xD2,0xD3,0xD4,0xD5]),
             (6,8,[0xC6,0xC7,0xC8,0xC9,0xD6]),
             (7,4,txt('PENTA DRAGON DX')),
             (9,5,txt('OPENING START')),(11,5,txt('GAME    START')),
             (15,1,[0xC0]),
             (16,1,[0xD0,0xD7,0xD8,0xD9,0,0x89,0x80,0x8F,0x80,0x8D,0,0x80,0x91,0x93,0,0x8C,0x84,0x83,0x88,0x80]),
             (18,1,map_title_string_to_tiles(TITLE_FOOTER))]
    attrs,_=title.title.build_attribute_image(records)
    palettes=title.title.build_palette_block(title.title.SCHEMES['Nightfall'])
    service=title.r366.build_title_service()
    assert service.endswith(title.R366_TAIL)
    service=service[:-len(title.R366_TAIL)]+title.R367_TAIL
    service=title.build_title_service_v2(service,title.MERGE_SERVICE_ADDR)
    image=bytearray(b'\xff'*16384)
    for addr,code in ((0x6000,bytes(attrs)),(0x6240,palettes),
                      (0x6C80,title.MERGE_HEADS['v6']+isr_service()),(0x6D00,service)):
        image[addr-0x4000:addr-0x4000+len(code)]=code
    return bytes(image)


if __name__=='__main__':
    expected=expected_bank25()
    actual=Path(sys.argv[1]).read_bytes()[25*16384:26*16384]
    diffs=[hex(0x4000+i) for i,(a,e) in enumerate(zip(actual,expected)) if a!=e]
    print(hashlib.sha256(expected).hexdigest(),len(diffs),diffs[:20])
    assert actual==expected
