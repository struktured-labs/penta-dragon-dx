"""#45 experimental live-palette return fade; timing not yet qualified.

Shares the menu palette backup at SVBK7:DF00 only during inactive Stage1
return. Does not change the stock eight-wait fade loop. Window acquisition
and palette work may still add latency; this is explicitly a visual trial.
"""
import argparse
import hashlib
import json
from pathlib import Path
from compose_ending_bgp_handoff_r518 import Asm

PARENT = '916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb'
BASE = 0x551c


# Re-pin (docs/audit/release-lock-20261001-repin.md): the release-lock chain
# defers #14 and #34. Parent 4d8f3fad... yields byte-identical
# changes (same offsets, preimages and values) as on the original 916ebb18...
REPINNED_PARENT = '4d8f3fad9cb57f24cdd442402a5b4d2a67f9aeea683e20328d4ed8fd02645f8e'


def payload(return_scoped=False, isolated=False, combined_entry=False, scheduled_write=False, fused_setup=False, card_tail=False):
    if card_tail and not fused_setup:
        raise ValueError('card tail requires fused setup')
    if fused_setup and not scheduled_write:
        raise ValueError('fused setup requires scheduled write')
    if scheduled_write and not combined_entry:
        raise ValueError('scheduled write requires combined entry')
    if combined_entry and not (return_scoped and isolated):
        raise ValueError('combined entry requires scoped isolated dispatch')
    a=Asm(BASE)
    a.db(0xE5,0xF8,5,0x7E)
    if card_tail:
        #75C7 also serves initial stage entry from4143. Its tail return4146
        # must run native0F33, not the unrelated credits fallback742A.
        a.db(0xFE,0x41)
        a.absolute(0xC2,'check_setup_hi')
        a.db(0x2B,0x7E,0xFE,0x46)
        a.absolute(0xCA,'native_card')
        a.absolute(0xC3,'fallback')
        a.label('check_setup_hi')
    a.db(0xFE,0x15)
    a.absolute(0xCA,'setup_hi')
    a.db(0xFE,0x0F)
    a.absolute(0xC2,'fallback')
    a.db(0x2B,0x7E,0xFE,0x92)
    a.absolute(0xCA,'shade')
    a.absolute(0xC3,'fallback')
    a.label('setup_hi')
    a.db(0x2B,0x7E,0xFE,0xDA)
    a.absolute(0xCA,'setup')
    if return_scoped:
        a.db(0xFE,0xDD)
        a.absolute(0xCA,'return_fade')
    if card_tail:
        a.db(0xFE,0xA2)
        a.absolute(0xCA,'card_fade')
    a.label('fallback')
    if isolated:
        a.db(0xE1,0xF1,0xC3,0x2A,0x74)
    else:
        a.db(0xE1,0xC3,0,0x47)
    a.label('setup')
    a.db(0xF0,0xBA,0xB7)
    a.absolute(0xC2,'native_setup')
    a.db(0xFA,0x80,0xD8,0xFE,2)
    a.absolute(0xC2,'native_setup')
    a.db(0xE1,0xF1,0xC5,0xD5,0xE5)
    a.absolute(0xCD,'backup')
    a.absolute(0xCD,'map00')
    a.db(0xE1,0xD1,0xC1,0xAF,0xE0,0x47,0xE0,0x48,0xE0,0x49,0xC3,0x9A,9)
    a.label('native_setup')
    a.db(0xE1,0xF1,0xAF,0xE0,0x47,0xE0,0x48,0xE0,0x49,0xC3,0x9A,9)
    a.label('shade')
    # Native0F7A also serves cold boot. Only its15DA call owns this backup.
    # Dispatcher HL, wrapper AF, hook return, native BC/DE/HL, caller return.
    a.db(0xF8,13,0x7E,0xFE,0x15)
    a.absolute(0xC2,'native_shade')
    a.db(0x2B,0x7E,0xFE,0xDD)
    a.absolute(0xC2,'native_shade')
    a.db(0xF0,0xBA,0xB7)
    a.absolute(0xC2,'native_shade')
    a.db(0xFA,0x80,0xD8,0xFE,2)
    a.absolute(0xC2,'native_shade')
    a.db(0xE1,0xF1,0x2A,0xE0,0x47,0xF5,0xC5,0xD5,0xE5)
    for mapping in (0,0x40,0x90,0xe4):
        a.db(0xFE,mapping)
        a.absolute(0xCA,f'shade{mapping:02x}')
    a.absolute(0xC3,'done')
    for mapping in (0,0x40,0x90,0xe4):
        a.label(f'shade{mapping:02x}')
        a.absolute(0xCD,f'map{mapping:02x}')
        a.absolute(0xC3,'done')
    a.label('done')
    a.db(0xE1,0xD1,0xC1,0xF1,0xC3,0x9A,9)
    a.label('native_shade')
    a.db(0xE1,0xF1,0x2A,0xE0,0x47,0xC3,0x9A,9)
    if return_scoped:
        a.label('return_fade')
        a.db(0xF0,0xBA,0xB7)
        a.absolute(0xC2,'native_fade')
        a.db(0xFA,0x80,0xD8,0xFE,2)
        a.absolute(0xC2,'native_fade')
        if card_tail:
            # Only1479's return147C follows the scoped secret card tail.
            # Preserve its live backup without reserving an unowned RAM latch.
            a.db(0xF8,6,0x2A,0xFE,0x7C)
            a.absolute(0xC2,'fresh_return')
            a.db(0x7E,0xFE,0x14)
            a.absolute(0xC2,'fresh_return')
            a.db(0xE1,0xF1,0xE5,0xD5,0xC5,0xAF,0xE0,0x49)
            a.absolute(0xC3,'fade_steps')
            a.label('fresh_return')
        a.db(0xE1,0xF1,0xE5,0xD5,0xC5,0xAF,0xE0,0x49)
        if combined_entry:
            a.absolute(0xCD,'backup')
            if not fused_setup or card_tail:
                a.absolute(0xCD,'map00')
        a.label('fade_steps')
        for mapping,obj in ((0,0),(0x40,0x40),(0x90,0x84),(0xe4,0xc4)):
            # Seven ordinary waits followed by window/map acquisition form
            # the intended eighth frame, rather than appending a ninth.
            # This is experimental scheduling, not proof of native cadence.
            a.db(0x06,7 if scheduled_write else 8)
            a.absolute(0xCD,'native_eight_waits')
            a.db(0x3E,mapping,0xE0,0x47)
            a.absolute(0xCD,f'map{mapping:02x}')
            a.db(0x3E,obj,0xE0,0x48)
        a.db(0xC1,0xD1,0xE1,0xAF,0x3E,1,0x3D,0x3E,0xC4,0xC3,0x9A,9)
        a.label('native_fade')
        # Replace the wrapper's saved AF with a synthetic0F7A return. Native
        # fade resets A/flags before use; original HL and caller15DD survive.
        a.db(0xF8,2,0x36,0x7A,0x23,0x36,0x0F,0xE1,0xC3,0x9A,9)
        a.label('native_eight_waits')
        a.absolute(0xCD,'native_wait')
        a.db(0x05)
        a.jr(0x20,'native_eight_waits')
        a.db(0xC9)
        a.label('native_wait')
        a.db(0xF0,0x41,0xE6,3,0xFE,3)
        a.jr(0x20,'native_wait')
        a.label('native_wait_end')
        a.db(0xF0,0x41,0xE6,3,0x3D)
        a.jr(0x20,'native_wait_end')
        a.db(0xC9)
    if card_tail:
        a.label('card_fade')
        a.db(0xF0,0xBA,0xB7)
        a.absolute(0xC2,'native_card')
        a.db(0xFA,0x80,0xD8,0xFE,0x18)
        a.absolute(0xC2,'native_card')
        a.db(0xF8,6,0x2A,0xFE,0x76)
        a.absolute(0xC2,'native_card')
        a.db(0x7E,0xFE,0x14)
        a.absolute(0xC2,'native_card')
        a.db(0xE1,0xF1,0xE5,0xD5,0xC5)
        a.absolute(0xCD,'backup')
        for mapping in (0xe4,0x90,0x40,0):
            # Three timer ticks plus the next safe publication window are
            # experimental scheduling of the native four-tick card step.
            a.db(0xAF,0xE0,0xD4)
            a.label(f'card_wait{mapping:02x}')
            a.db(0xF0,0xD4,0xFE,3)
            a.jr(0x38,f'card_wait{mapping:02x}')
            a.db(0x3E,mapping,0xE0,0x47)
            a.absolute(0xCD,f'map{mapping:02x}')
        a.db(0xAF,0xE0,0xD4,0xC1,0xD1,0xE1,0xC3,0x9A,9)
        a.label('native_card')
        a.db(0xF8,2,0x36,0x33,0x23,0x36,0x0F,0xE1,0xC3,0x9A,9)
    # No stack operation while SVBK7 is selected: native stack lives in bank1.
    a.label('backup')
    a.db(0xF0,0x68,0xF5)
    a.absolute(0xCD,'window')
    a.db(0x3E,7,0xE0,0x70,0x21,0,0xDF,0x06,0)
    a.label('read')
    for _ in range(8 if fused_setup else 1):
        a.db(0x78,0xE0,0x68,0xF0,0x69,0x22,0x04)
    a.db(0x78,0xFE,64)
    a.jr(0x20,'read')
    if fused_setup and not card_tail:
        # Keep interrupts masked and the saved BCPS on the bank1 stack.
        # Tail transfer only: no stack access while SVBK7 remains selected.
        a.absolute(0xC3,'map00_body')
    else:
        a.db(0x3E,1,0xE0,0x70,0xF1,0xE0,0x68,0xFB,0,0xC9)
    for mapping in (0,0x40,0x90,0xe4):
        a.label(f'map{mapping:02x}')
        a.db(0xF0,0x68,0xF5)
        a.absolute(0xCD,'window')
        a.label(f'map{mapping:02x}_body')
        a.db(0x3E,7,0xE0,0x70,0x3E,0x80,0xE0,0x68)
        for row in range(8):
            for color in range(4):
                ci=(mapping>>(2*color))&3
                if ci==0 and mapping!=0xe4:
                    a.db(0x3E,0xFF,0xE0,0x69,0x3E,0x7F,0xE0,0x69)
                else:
                    addr=0xDF00+row*8+ci*2
                    a.db(0x21,addr&255,addr>>8,0x2A,0xE0,0x69,0x7E,0xE0,0x69)
        a.db(0x3E,1,0xE0,0x70,0xF1,0xE0,0x68,0xFB,0,0xC9)
    # Acquire at visible142/143 before VBlank IRQ can consume the window.
    # Writes start at144; this deliberately shares the existing menu strategy.
    a.label('window')
    a.db(0xF0,0x44,0xFE,142)
    a.jr(0x38,'window')
    a.db(0xFE,144)
    a.jr(0x30,'window')
    a.db(0xF3,0xF0,0x44,0xFE,144)
    a.jr(0x30,'retry')
    a.label('wait144')
    a.db(0xF0,0x44,0xFE,144)
    a.jr(0x38,'wait144')
    a.db(0xC9)
    a.label('retry')
    a.db(0xFB,0)
    a.jr(0x18,'window')
    return a.finish()


def build(parent, return_scoped=False, isolated=False, combined_entry=False, scheduled_write=False, fused_setup=False, card_tail=False):
    if card_tail and not fused_setup:
        raise ValueError('card tail requires fused setup')
    if fused_setup and not scheduled_write:
        raise ValueError('fused setup requires scheduled write')
    if scheduled_write and not combined_entry:
        raise ValueError('scheduled write requires combined entry')
    if combined_entry and not (return_scoped and isolated):
        raise ValueError('combined entry requires scoped isolated dispatch')
    if hashlib.sha256(parent).hexdigest() not in (PARENT, REPINNED_PARENT): raise ValueError('exact916e parent required')
    result=bytearray(parent)
    shade_hook=(0x15da,'CD7A0F','CD8942') if return_scoped else (0xf8f,'2AE047','CD8942')
    hooks=[shade_hook] if combined_entry else [(0x15d7,'CD0E0A','CD8942'),shade_hook]
    if card_tail:
        hooks.append((0x75f0,'C3330F','C38942'))
    if not isolated:
        hooks.append((20*0x4000+0x28f,'C30047',f'C3{BASE&255:02X}{BASE>>8:02X}'))
    else:
        # Original menu high-byte0A path executes exactly the same instructions.
        # Only redirect its existing taken JP NZ; HL is already saved on entry.
        site=20*0x4000+0x700
        if parent[site:site+7]!=bytes.fromhex('E5 F8 05 7E FE 0A C2'):
            raise ValueError('menu discriminator preimage differs')
        result[site+7:site+9]=(BASE+1).to_bytes(2,'little')
    for addr,old,new in hooks:
        if parent[addr:addr+3]!=bytes.fromhex(old): raise ValueError('hook preimage differs')
        result[addr:addr+3]=bytes.fromhex(new)
    code=payload(return_scoped,isolated,combined_entry,scheduled_write,fused_setup,card_tail);offset=20*0x4000+BASE-0x4000
    if len(code)>1984 or parent[offset:offset+len(code)]!=b'\xff'*len(code):
        raise ValueError('fade cave occupied')
    result[offset:offset+len(code)]=code
    result[0x14e:0x150]=((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--return-scoped',action='store_true',help='leave shared native fade bytes untouched')
    p.add_argument('--isolated',action='store_true',help='preserve original menu instruction path')
    p.add_argument('--combined-entry',action='store_true',help='keep native setup; back up live palette at scoped fade entry')
    p.add_argument('--scheduled-write',action='store_true',help='experimental: publish during the eighth wait instead of adding a ninth')
    p.add_argument('--fused-setup',action='store_true',help='experimental: unroll backup and whiten within its same acquired window')
    p.add_argument('--card-tail',action='store_true',help='experimental: fade the scoped secret-return card before dungeon loading')
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:
        p.error('fresh repository tmp output required')
    if a.isolated and not a.return_scoped: p.error('--isolated requires --return-scoped')
    if a.combined_entry and not (a.return_scoped and a.isolated): p.error('--combined-entry requires --return-scoped --isolated')
    if a.scheduled_write and not a.combined_entry: p.error('--scheduled-write requires --combined-entry')
    if a.fused_setup and not a.scheduled_write: p.error('--fused-setup requires --scheduled-write')
    if a.card_tail and not a.fused_setup: p.error('--card-tail requires --fused-setup')
    result=build(a.parent.read_bytes(),a.return_scoped,a.isolated,a.combined_entry,a.scheduled_write,a.fused_setup,a.card_tail);a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(result)
    receipt=dict(issue=45,experimental=True,release_qualified=False,parent_sha256=PARENT,return_scoped=a.return_scoped,isolated=a.isolated,combined_entry=a.combined_entry,scheduled_write=a.scheduled_write,fused_setup=a.fused_setup,card_tail=a.card_tail,
                 candidate_sha256=hashlib.sha256(result).hexdigest(),
                 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 limitations=['setup before15D7 remains visible','extra fade latency unqualified',
                              'bank7 palette backup lifetime needs all-route validation',
                              'shared0F7A uses native fallback outside15DA; cold timing unverified'])
    (a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
