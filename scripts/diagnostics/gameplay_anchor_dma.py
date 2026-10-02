"""Normalize combat anchors only after their real OAM DMA has completed."""
import hashlib,json,os,zlib
from pathlib import Path
from normalize_mgba_state_pc import png_chunks,normalize,retarget_rom_identity,GB_STATE_SIZE
from generate_stream_boss_states import run_until_marker

ROOT=Path(__file__).resolve().parents[2]
DMA_LOOP=bytes.fromhex('F0CB3CE601E0CBC6C0E0463E283D20FDC9')


def payload(path):
    chunks=[v for k,v in png_chunks(path.read_bytes()) if k==b'gbAs']
    if len(chunks)!=1: raise ValueError('requires one state payload')
    raw=zlib.decompress(chunks[0])
    if len(raw)!=GB_STATE_SIZE: raise ValueError('state size changed')
    return raw


def validate_dma_resume(raw):
    if len(raw)!=GB_STATE_SIZE: raise ValueError('state size changed')
    if not raw[0x17E]: return False
    pc=int.from_bytes(raw[0x2A:0x2C],'little')
    if not 0xFF80<=pc<0xFF90 or raw[0x380:0x391]!=DMA_LOOP:
        raise ValueError('active DMA outside authenticated native HRAM loop')
    # HRAM executes independently of the selected ROM bank. An IRQ may
    # interrupt a bank-13 helper; stop before its RET, then normalize bank 1.
    if int.from_bytes(raw[0x168:0x16A],'little')>=32:
        raise ValueError('DMA caller bank is outside the candidate')
    return True


def prepare(mgba,rom,source,output,timeout):
    output.mkdir(parents=True,exist_ok=True)
    identity=output/'identity.ss0'
    raw=payload(source)
    if raw[0x10:0x20]==rom.read_bytes()[0x134:0x144]:
        identity.write_bytes(source.read_bytes())
    else:
        retarget_rom_identity(source,identity,rom)
    settled=identity
    dma=validate_dma_resume(payload(identity))
    if dma:
        prefix=output/'dma-boundary';marker=prefix.with_suffix('.done')
        marker.unlink(missing_ok=True)
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy',
                 GAMEPLAY_DMA_OUT=str(prefix),GAMEPLAY_DMA_STATE=str(identity))
        run_until_marker([str(mgba),'--fastforward','--script',
                          str(ROOT/'scripts/diagnostics/probe_gameplay_dma_boundary.lua'),str(rom)],
                         env,ROOT,marker,timeout)
        if marker.read_text()!='complete': raise ValueError('DMA boundary incomplete')
        settled=prefix.with_suffix('.ss0')
        observed=payload(settled)
        if observed[0x17E]!=0 or int.from_bytes(observed[0x2A:0x2C],'little')!=0xFF90:
            raise ValueError('native DMA did not reach its completed return')
    result=output/'current.ss0'
    normalize(settled,result,0x016C,[(0xDF51,0)],rom,bank=1)
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    (output/'receipt.json').write_text(json.dumps(dict(source=str(source),source_sha256=digest(source),
        rom_sha256=digest(rom),native_dma_completed=dma,settled_sha256=digest(settled),
        normalized_sha256=digest(result)),indent=2)+'\n')
    return result
