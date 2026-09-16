"""Offline diagnostic of neutral-floor palettes; not a readiness oracle."""
import argparse
import csv
import json
from pathlib import Path


def summarize(rows):
    result = {}
    for row in rows:
        phase = row["stimulus_phase"]
        summary = result.setdefault(phase, dict(frames=0, bad_frames=0,
            maximum_bad_cells=0, first_bad_frame=None, last_bad_frame=None))
        tiles = bytes.fromhex(row["tile_bytes"])
        attrs = bytes.fromhex(row["attr_bytes"])
        if len(tiles) != len(attrs):
            raise ValueError("tile/attribute sample length mismatch")
        bad = sum(1 <= tile <= 4 and attr != 0
                  for tile, attr in zip(tiles, attrs))
        summary["frames"] += 1
        summary["maximum_bad_cells"] = max(summary["maximum_bad_cells"], bad)
        if bad:
            summary["bad_frames"] += 1
            if summary["first_bad_frame"] is None:
                summary["first_bad_frame"] = int(row["frame"])
            summary["last_bad_frame"] = int(row["frame"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    with args.trace.open() as handle:
        print(json.dumps(summarize(csv.DictReader(handle, delimiter="\t")), indent=2))
