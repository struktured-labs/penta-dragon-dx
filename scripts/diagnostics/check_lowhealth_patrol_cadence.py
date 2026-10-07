"""#66 diagnostic: existing strict settled-motion check on a low-health patrol.

Preserves nested failures. Does not qualify the initial encounter, full scene,
audio, or a release; the copied world fields are not complete machine state.
"""
import argparse
import hashlib
import json
from pathlib import Path
from verify_stage7_state_patrol import parse_trace, settled_metric


def inspect(folder):
    traces, images, bindings = {}, [], {}
    manifest = folder/'manifest.json'
    nested = json.loads(manifest.read_text())
    for family in ('original', 'dx'):
        for rep in ('a', 'b'):
            result = folder/f'stage7-{family}-{rep}-loop-patrol/result.json'
            data = json.loads(result.read_text())
            if data.get('health_assistance') != 109 or data.get('frames') != 4000:
                raise ValueError('requires complete 4000-frame HP109 patrol')
            trace = Path(str(result)+'.coordinate.tsv')
            image = Path(str(result)+'.world.bin')
            traces[f'{family}_{rep}'] = parse_trace(trace, result)
            images.append(image.read_bytes())
            for path in (result, trace, image):
                bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(images[0]) != 516 or any(image != images[0] for image in images):
        raise ValueError('copied world fields differ')
    for family in ('original', 'dx'):
        if traces[family+'_a']['canonical_sha256'] != traces[family+'_b']['canonical_sha256']:
            raise ValueError('nondeterministic replay')
    metric = settled_metric(traces, .02, 24, 20)
    return dict(scope=__doc__, release_qualified=False,
                settled_cadence_passed=metric['strict_target_met'], metric=metric,
                endpoint_counts={k:len(v['endpoint_events']) for k,v in traces.items()},
                initial_and_terminal_unmatched_work_qualified=False,
                nested_status=nested.get('status'), nested_failures=nested.get('failures'),
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                bindings=bindings,
                analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                metric_tool_sha256=hashlib.sha256(Path(__file__).with_name('verify_stage7_state_patrol.py').read_bytes()).hexdigest())


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = inspect(args.folder)
    with args.output.open('x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps(result['metric'], indent=2))
    raise SystemExit(0 if result['settled_cadence_passed'] else 1)
