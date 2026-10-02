#!/usr/bin/env python3
"""Offline lookup equivalence diagnostic; not a visual/readiness gate."""
import argparse
import hashlib
import json
from pathlib import Path
SIZE=576+256+768+121

def analyze(data):
    if not data or len(data)%SIZE:raise ValueError('incomplete attribute snapshots')
    mismatches=[];helpers=set()
    for index in range(len(data)//SIZE):
        snapshot=data[index*SIZE:(index+1)*SIZE]
        source=snapshot[:576];lut=snapshot[576:832];plane=snapshot[832:1600]
        helpers.add(hashlib.sha256(snapshot[1600:]).hexdigest())
        for row in range(24):
            for col in range(24):
                expected=lut[source[row*24+col]];actual=plane[row*32+col]
                if actual!=expected:
                    mismatches.append(dict(record=index,row=row,col=col,
                                           expected=expected,actual=actual))
    return dict(records=len(data)//SIZE,mismatch_cells=len(mismatches),
                first_mismatch=mismatches[0] if mismatches else None,
                row_helper_sha256=sorted(helpers))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path);args=parser.parse_args()
    print(json.dumps(analyze(args.snapshot.read_bytes()),indent=2))
