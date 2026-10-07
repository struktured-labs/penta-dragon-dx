"""Build historical observer fixtures from source; never require scratch ROMs.

Only static unit tests use these ROMs. No generated fixture confers emulator
qualification or savestate compatibility. The normal source builder retains
all intermediate identity checks and executes its traced double build.
"""
from contextlib import ExitStack
from functools import lru_cache
import hashlib
import importlib
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]


@lru_cache(maxsize=1)
def observer_fixtures():
    import build_r534_candidate as builder
    import r534_lineage_prefix as prefix
    import rebuild_r534_lineage as continuation

    wanted = {'r424', 'r435', 'r436', 'r440', 'r442', 'r453'}
    images = {}

    def record(name, expected, function):
        def wrapped(*args, **kwargs):
            output = function(*args, **kwargs)
            image = output[0] if isinstance(output, tuple) else output
            if hashlib.sha256(image).hexdigest() != expected:
                raise ValueError(f'{name}: generated observer fixture identity differs')
            if name in images and images[name] != image:
                raise ValueError(f'{name}: observer fixture double build differs')
            images[name] = image
            return output
        return wrapped

    with ExitStack() as stack:
        for step in prefix.STEPS:
            name = step.module.rsplit('_', 1)[-1]
            if name in wanted:
                module = importlib.import_module(step.module)
                stack.enter_context(patch.object(
                    module, 'build', record(name, step.output_sha256, module.build)))
        steps = tuple((name, expected, record(name, expected, compose)
                       if name in wanted else compose)
                      for name, expected, compose in continuation.STEPS)
        stack.enter_context(patch.object(continuation, 'STEPS', steps))
        scratch = ROOT / 'tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='observer-source-', dir=scratch) as work:
            builder.build(Path(work) / 'r534',
                          ROOT / 'palettes/penta_palettes_restart_parent.yaml')
    if set(images) != wanted:
        raise ValueError('source observer fixture inventory differs')
    return images
