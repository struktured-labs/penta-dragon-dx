"""#67: source-built #43 startup barrier for single-flight restored replays.

Never launches an emulator. Build against the library resolved for the guarded
Qt frontend; missing build metadata is an error, not a fallback to an old tap.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TAP = Path(__file__).with_name("native_av_tap.c")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cmake_arguments(text: str) -> list[str]:
    values = dict(re.findall(r"^(C_DEFINES|C_INCLUDES) = (.*)$", text, re.M))
    if set(values) != {"C_DEFINES", "C_INCLUDES"}:
        raise ValueError("missing native core compile definitions/includes")
    # CMake escapes embedded quotes for the shell. shlex performs that same
    # conversion without evaluating shell substitutions or running a shell.
    return shlex.split(values["C_DEFINES"]) + shlex.split(values["C_INCLUDES"])


def prepare(output: Path, environment: dict[str, str]) -> dict:
    if any(environment.get(key) for key in
           ("LD_PRELOAD", "PENTA_NATIVE_AV_PREFIX", "ENTRY_NATIVE_START_GATE")):
        raise ValueError("native replay owns its preload, capture, and startup marker")
    spec = importlib.util.spec_from_file_location(
        "native_replay_singleflight", ROOT / "scripts/mgba_singleflight.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    frontend = guard.resolve_binary("qt").resolve()
    linked = subprocess.run(["ldd", str(frontend)], env=environment,
                            text=True, capture_output=True, check=True)
    libraries = re.findall(r"libmgba[^\s]* => (\S+)", linked.stdout)
    if len(libraries) != 1:
        raise ValueError("cannot uniquely resolve the guarded frontend's libmgba")
    library = Path(libraries[0]).resolve()
    build = library.parent
    flags = build / "CMakeFiles/mgba.dir/flags.make"
    arguments = cmake_arguments(flags.read_text())
    compiler = shutil.which("cc")
    if compiler is None:
        raise ValueError("native replay requires a C compiler")
    runtime = output.resolve() / "native-runtime"
    runtime.mkdir(exist_ok=False)
    adapter = runtime / "native-replay.so"
    dependencies = runtime / "dependencies.d"
    command = [compiler, "-shared", "-fPIC", "-O2", "-std=c11", *arguments,
               "-MD", "-MF", str(dependencies), str(TAP), "-ldl", "-o", str(adapter)]
    with (runtime / "build.log").open("x") as log:
        subprocess.run(command, env={**environment, "TMPDIR": str(runtime)},
                       stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=60)
    # Include every transitive header, including platform ABI declarations.
    dependency_text = dependencies.read_text().replace("\\\n", " ")
    headers = [Path(value).resolve() for value in
               shlex.split(dependency_text.split(":", 1)[1])]
    bindings = {str(path): digest(path) for path in
                [frontend, library, flags, TAP, Path(compiler).resolve(), *headers]}
    bulk = Path("/mnt/data/tmp")
    if not bulk.is_dir() or not os.access(bulk, os.W_OK):
        bulk = ROOT / "tmp"
    capture = Path(tempfile.mkdtemp(prefix="penta-lowhealth-native-", dir=bulk))
    marker = runtime / "ready"
    environment.update(LD_PRELOAD=str(adapter), PENTA_NATIVE_AV_PREFIX=str(capture / "native"),
                       ENTRY_NATIVE_START_GATE=str(marker))
    receipt = {"adapter_sha256": digest(adapter), "bindings": bindings,
               "command": command, "capture_directory": str(capture),
               "startup_marker": str(marker), "library": str(library)}
    (runtime / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
