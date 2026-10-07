"""#54/#62 release gate: all nine headers, native common timing, corrupt control."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import build_clean_stage_headers as layout
import playtest_successor_lineage as lineage

ROOT=Path(__file__).resolve().parents[2]
STOCK_SHA='2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30'


def corrupt_control(rom):
    if not lineage.is_candidate(rom):
        raise ValueError('exact combined playtest candidate required')
    result=bytearray(rom)
    # Deliberately replay the original defect: the two code helpers become
    # header bytes. Do not patch the real candidate or change its code path.
    for address in (0x7C91,0x7CAE):
        destination=layout.offset(layout.CLEAN_TABLE)+address-0x7BB3
        result[destination:destination+9]=rom[address:address+9]
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();stock=ROOT/'rom/Penta Dragon (J).gb'
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents:
        p.error('fresh repository-local tmp output required')
    if hashlib.sha256(stock.read_bytes()).hexdigest()!=STOCK_SHA:
        p.error('stock header oracle identity differs')
    control=corrupt_control(a.rom.read_bytes());out.mkdir(parents=True)
    broken=out/'deliberately-corrupt-headers.gb';broken.write_bytes(control)
    (out/'control.json').write_text(json.dumps({
        'kind':'deliberate header-data corruption, not a played historical ROM',
        'candidate_sha256':hashlib.sha256(a.rom.read_bytes()).hexdigest(),
        'control_sha256':hashlib.sha256(control).hexdigest(),
        'expected_failed_records':[7,8],
    },indent=2)+'\n')
    return subprocess.run([
        sys.executable,str(Path(__file__).with_name('verify_clean_stage_headers.py')),
        '--original',str(stock),'--parent',str(broken),
        '--candidate',str(a.rom.resolve()),'--output',str(out/'contracts'),
        '--require-native-common-timing',
    ],cwd=ROOT,check=False).returncode


if __name__=='__main__':raise SystemExit(main())
