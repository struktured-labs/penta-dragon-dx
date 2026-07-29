#!/usr/bin/env python3
"""
MiSTer FPGA automation for Penta Dragon DX.

Handles ROM deployment, game launching, screenshots, save states, input
injection, and backup to blackmage. Designed for remote CLI use by Claude
or the user.

Usage:
    uv run python scripts/mister.py deploy                        # Build + deploy ROM to MiSTer
    uv run python scripts/mister.py launch                         # Launch game on MiSTer (GBC mode)
    uv run python scripts/mister.py reload                         # Deploy + launch in one step
    uv run python scripts/mister.py screenshot [label]             # Take and fetch screenshot
    uv run python scripts/mister.py fetch_screenshot               # Fetch latest screenshot (no new capture)
    uv run python scripts/mister.py press START                    # Send button press
    uv run python scripts/mister.py press A A START                # Send multiple presses
    uv run python scripts/mister.py navigate START A DOWN A        # Press with 0.3s delays (menu nav)
    uv run python scripts/mister.py savestate save [slot]          # Save state (slot 1-4)
    uv run python scripts/mister.py savestate load [slot]          # Load state
    uv run python scripts/mister.py savestate fetch [slot]         # Download state file
    uv run python scripts/mister.py backup [version]               # Backup ROM+states to blackmage
    uv run python scripts/mister.py status                         # Show MiSTer core/game state
    uv run python scripts/mister.py play [seconds]                 # Launch, wait, screenshot sequence
    uv run python scripts/mister.py reset                          # Reset current core (reload game)
    uv run python scripts/mister.py pause                          # Toggle pause on
    uv run python scripts/mister.py unpause                        # Toggle pause off
    uv run python scripts/mister.py osd                            # Toggle OSD menu (F12)
    uv run python scripts/mister.py game_start                     # Macro: launch + DOWN→A→A→A to gameplay
    uv run python scripts/mister.py capture_gameplay [secs] [label] # Launch + play + periodic screenshots
    uv run python scripts/mister.py deploy_and_test [version]      # Build + deploy + launch + screenshot
    uv run python scripts/mister.py release_sweep_start MANIFEST   # Start hash-bound physical release sweep
    uv run python scripts/mister.py release_checkpoint HW NAME confirm
    uv run python scripts/mister.py release_sweep_finish HW        # Seal pass after every confirmation
    uv run python scripts/mister.py list_states                    # List save states on MiSTer
    uv run python scripts/mister.py clean_old_roms                 # Remove old versioned ROMs from MiSTer
    uv run python scripts/mister.py cheats list                     # Show all available cheats
    uv run python scripts/mister.py cheats build                    # Build cheat zip locally
    uv run python scripts/mister.py cheats deploy                   # Build + deploy cheats to MiSTer
    uv run python scripts/mister.py clean                          # Clean MiSTer screenshots

Environment:
    MISTER_HOST: MiSTer SSH hostname (default: MiSTer)
    MISTER_USER: MiSTer SSH user (default: root)
    BLACKMAGE_HOST: Backup host (default: struktured@blackmage)
    MISTER_RESERVATION_ID: Active reservation identifier for this MiSTer
    MISTER_RESERVATION_CHECKER: Local checker command that exits 0 only while
        MISTER_RESERVATION_ID owns an active reservation for MISTER_HOST

The reservation checker receives MISTER_RESERVATION_ID and
MISTER_RESERVATION_HOST in its environment. Hardware commands fail closed
before SSH/SCP unless the checker confirms the reservation. This script does
not acquire reservations; use the shared reservation service first.
"""

import struct
import subprocess
import sys
import time
import shlex
import zipfile
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

# === Configuration ===

import os
MISTER_HOST = os.environ.get("MISTER_HOST", "MiSTer")
MISTER_USER = "root"
BLACKMAGE_USER = "struktured"
BLACKMAGE_HOST = "blackmage"

# Paths on MiSTer
MISTER_ROM_DIR = "/media/fat/games/GBC"
MISTER_ROM_NAME = "penta_dragon_dx_FIXED.gbc"
MISTER_ROM_PATH = f"{MISTER_ROM_DIR}/{MISTER_ROM_NAME}"
MISTER_SCREENSHOTS_DIR = "/media/fat/screenshots"
MISTER_SAVESTATES_DIR = "/media/fat/savestates"
MISTER_CMD = "/dev/MiSTer_cmd"
MISTER_MGL_PATH = "/tmp/penta.mgl"
MISTER_CORE = "_Console/Gameboy"

# Paths on local machine
PROJECT_ROOT = Path(__file__).parent.parent
LOCAL_ROM = PROJECT_ROOT / "rom" / "working" / "penta_dragon_dx_FIXED.gb"
LOCAL_TMP = PROJECT_ROOT / "tmp"
LOCAL_SCREENSHOTS = LOCAL_TMP / "mister_screenshots"
LOCAL_SAVESTATES = LOCAL_TMP / "mister_savestates"
LOCAL_RELEASE_SWEEPS = LOCAL_TMP / "mister_release_sweeps"
LOCAL_RELEASE_PATCH = PROJECT_ROOT / "rom" / "penta_dragon_dx.ips"
RELEASE_PATCH_VERIFIER = (
    PROJECT_ROOT / "scripts" / "diagnostics" / "verify_release_patch.py"
)

REQUIRED_HARDWARE_CHECKPOINTS = (
    "gbc_core",
    "deployed_rom_hash",
    "title",
    "opening_route",
    "game_start_route",
    "stage_intro",
    "stage1_gameplay",
    "item_menu",
    "later_stage",
    "boss_arena",
    "death_gameover",
)

# Paths on blackmage
BLACKMAGE_BACKUP_DIR = "~/penta-dragon-dx-backups"

# MGL template - CRITICAL: <setname>GBC</setname> forces CGB mode
# Without this, the Gameboy core loads in DMG mode and CGB-only ROMs freeze
MGL_TEMPLATE = """<mistergamedescription>
\t<rbf>{core}</rbf>
\t<setname>GBC</setname>
\t<file delay="2" type="f" index="1" path="{rom_path}"/>
</mistergamedescription>"""

# Keyboard event device on MiSTer (Dell KB216)
KEYBOARD_EVENT = "/dev/input/event0"  # Dell KB216 keyboard (event3=MiSTer virtual)

# Key codes (Linux input event codes)
KEY_MAP = {
    # Gameboy buttons -> keyboard keys (MiSTer default mapping)
    "UP": 103,      # KEY_UP
    "DOWN": 108,     # KEY_DOWN
    "LEFT": 105,     # KEY_LEFT
    "RIGHT": 106,    # KEY_RIGHT
    "A": 56,         # KEY_LEFTALT (MiSTer default: A = Left Alt)
    "B": 29,         # KEY_LEFTCTRL (MiSTer default: B = Left Ctrl)
    "START": 28,     # KEY_ENTER
    "SELECT": 57,    # KEY_SPACE
    "L": 42,         # KEY_LEFTSHIFT
    "R": 54,         # KEY_RIGHTSHIFT
    # OSD
    "OSD": 88,       # KEY_F12
}


class ReservationError(RuntimeError):
    """Raised before MiSTer access when no active reservation is confirmed."""


def require_mister_reservation() -> None:
    """Fail closed unless an external checker confirms the active reservation.

    The repository intentionally does not implement reservation acquisition:
    that belongs to the shared reservation service. The configured checker is
    invoked without a shell and receives the reservation ID and exact target
    host in its environment. A zero exit status is the only success signal.
    """
    reservation_id = os.environ.get("MISTER_RESERVATION_ID", "").strip()
    checker_spec = os.environ.get("MISTER_RESERVATION_CHECKER", "").strip()

    missing = []
    if not reservation_id:
        missing.append("MISTER_RESERVATION_ID")
    if not checker_spec:
        missing.append("MISTER_RESERVATION_CHECKER")
    if missing:
        raise ReservationError(
            "MiSTer reservation required; missing "
            + " and ".join(missing)
            + ". Acquire the shared MiSTer reservation, then configure its "
              "checker. No MiSTer connection was attempted."
        )

    try:
        checker_command = shlex.split(checker_spec)
    except ValueError as exc:
        raise ReservationError(
            f"Invalid MISTER_RESERVATION_CHECKER: {exc}. "
            "No MiSTer connection was attempted."
        ) from exc
    if not checker_command:
        raise ReservationError(
            "MISTER_RESERVATION_CHECKER is empty after parsing. "
            "No MiSTer connection was attempted."
        )

    checker_env = os.environ.copy()
    checker_env["MISTER_RESERVATION_ID"] = reservation_id
    checker_env["MISTER_RESERVATION_HOST"] = MISTER_HOST
    try:
        result = subprocess.run(
            checker_command,
            cwd=str(PROJECT_ROOT),
            env=checker_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReservationError(
            f"MiSTer reservation checker could not run: {exc}. "
            "No MiSTer connection was attempted."
        ) from exc

    if result.returncode != 0:
        raise ReservationError(
            "MiSTer reservation is absent, expired, owned by someone else, "
            f"or does not cover host {MISTER_HOST!r}. "
            "No MiSTer connection was attempted."
        )


def ssh(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command on MiSTer via SSH."""
    require_mister_reservation()
    full_cmd = ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=accept-new", f"{MISTER_USER}@{MISTER_HOST}", cmd]
    return subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)


def ssh_check(cmd: str, timeout: int = 30) -> str:
    """Run a command on MiSTer, raise on failure, return stdout."""
    result = ssh(cmd, timeout)
    if result.returncode != 0:
        raise RuntimeError(f"SSH command failed: {cmd}\nstderr: {result.stderr}")
    return result.stdout.strip()


def scp_to_mister(local_path: Path, remote_path: str) -> None:
    """Copy a file to MiSTer."""
    require_mister_reservation()
    cmd = ["scp", "-o", "StrictHostKeyChecking=accept-new", str(local_path), f"{MISTER_USER}@{MISTER_HOST}:{remote_path}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"SCP to MiSTer failed: {result.stderr}")
    print(f"  Copied {local_path.name} -> MiSTer:{remote_path}")


def scp_from_mister(remote_path: str, local_path: Path) -> None:
    """Copy a file from MiSTer."""
    require_mister_reservation()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["scp", "-o", "StrictHostKeyChecking=accept-new", f"{MISTER_USER}@{MISTER_HOST}:{remote_path}", str(local_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"SCP from MiSTer failed: {result.stderr}")
    print(f"  Copied MiSTer:{remote_path} -> {local_path}")


def mister_cmd(command: str) -> None:
    """Send a command to MiSTer via /dev/MiSTer_cmd."""
    ssh(f'echo {shlex.quote(command)} > {MISTER_CMD}')


def get_corename() -> str:
    """Get the currently running core name."""
    return ssh_check("cat /tmp/CORENAME 2>/dev/null || echo UNKNOWN")


def get_rom_md5() -> str:
    """Get MD5 of ROM on MiSTer."""
    out = ssh_check(f"md5sum {MISTER_ROM_PATH} 2>/dev/null || echo MISSING")
    return out.split()[0] if "MISSING" not in out else "MISSING"


# === Commands ===

def cmd_status():
    """Show MiSTer state."""
    print("MiSTer Status:")
    print(f"  Core:     {get_corename()}")
    print(f"  ROM MD5:  {get_rom_md5()}")

    # Local ROM md5
    if LOCAL_ROM.exists():
        import hashlib
        local_md5 = hashlib.md5(LOCAL_ROM.read_bytes()).hexdigest()
        print(f"  Local MD5: {local_md5}")
        remote_md5 = get_rom_md5()
        print(f"  In sync:  {'YES' if local_md5 == remote_md5 else 'NO - deploy needed'}")

    # Screenshot count
    out = ssh("find /media/fat/screenshots -name '*.png' 2>/dev/null | wc -l")
    print(f"  Screenshots: {out.stdout.strip()}")

    # Save states
    out = ssh(f"ls {MISTER_SAVESTATES_DIR}/GBC/ 2>/dev/null")
    states = [f for f in out.stdout.strip().split('\n') if f and 'penta' in f.lower()]
    print(f"  Save states: {len(states)} ({', '.join(states) if states else 'none'})")


def cmd_deploy():
    """Deploy ROM to MiSTer."""
    if not LOCAL_ROM.exists():
        print(f"ERROR: Local ROM not found: {LOCAL_ROM}")
        print("Build first: uv run python scripts/create_vblank_colorizer_v266.py")
        sys.exit(1)

    import hashlib
    local_md5 = hashlib.md5(LOCAL_ROM.read_bytes()).hexdigest()
    remote_md5 = get_rom_md5()

    if local_md5 == remote_md5:
        print(f"ROM already up to date on MiSTer (md5: {local_md5[:8]}...)")
        return

    print(f"Deploying ROM to MiSTer...")
    print(f"  Local:  {local_md5[:8]}...")
    print(f"  Remote: {remote_md5[:8]}..." if remote_md5 != "MISSING" else "  Remote: not present")
    scp_to_mister(LOCAL_ROM, MISTER_ROM_PATH)
    new_md5 = get_rom_md5()
    if new_md5 != local_md5:
        print(f"ERROR: MD5 mismatch after deploy! {new_md5} != {local_md5}")
        sys.exit(1)
    print(f"  Verified: {new_md5[:8]}...")


def cmd_launch():
    """Launch game on MiSTer via MGL (forces GBC mode)."""
    print("Launching Penta Dragon DX on MiSTer...")

    # Write MGL file
    mgl = MGL_TEMPLATE.format(core=MISTER_CORE, rom_path=MISTER_ROM_PATH)
    ssh(f"cat > {MISTER_MGL_PATH} << 'MGLEOF'\n{mgl}\nMGLEOF")

    # Load via MGL
    mister_cmd(f"load_core {MISTER_MGL_PATH}")
    print("  Sent load_core command, waiting for core to initialize...")
    time.sleep(6)

    corename = get_corename()
    print(f"  Core name: {corename}")
    if corename == "GBC":
        print("  Game launched successfully in GBC mode!")
    else:
        raise RuntimeError(
            f"launch failed closed: expected CORENAME=GBC, got {corename!r}"
        )


def cmd_reload():
    """Deploy + launch in one step."""
    cmd_deploy()
    cmd_launch()


def cmd_screenshot(label: str = None):
    """Take a screenshot on MiSTer and fetch it locally."""
    corename = get_corename()
    alternate = "GAMEBOY" if corename == "GBC" else "GBC"
    screenshot_dirs = [
        f"{MISTER_SCREENSHOTS_DIR}/{corename}",
        f"{MISTER_SCREENSHOTS_DIR}/{alternate}",
    ]

    # Snapshot both plausible directories before capture. Falling back to an
    # arbitrary old image can falsely make a failed release screenshot pass.
    before_by_dir = {}
    for directory in screenshot_dirs:
        listing = ssh(f"ls {directory}/ 2>/dev/null").stdout.strip().split("\n")
        before_by_dir[directory] = {name for name in listing if name}

    # Take screenshot
    mister_cmd("screenshot")
    time.sleep(2)

    candidates = []
    for directory in screenshot_dirs:
        listing = ssh(f"ls {directory}/ 2>/dev/null").stdout.strip().split("\n")
        after = {name for name in listing if name}
        candidates.extend((name, directory) for name in after - before_by_dir[directory])

    if not candidates:
        print("ERROR: Could not capture screenshot")
        return None

    remote_file, screenshot_dir = sorted(candidates)[-1]
    remote_path = f"{screenshot_dir}/{remote_file}"

    # Generate local filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    suffix = f"_{label}" if label else ""
    local_name = f"mister_{timestamp}{suffix}.png"
    local_path = LOCAL_SCREENSHOTS / local_name

    scp_from_mister(remote_path, local_path)
    print(f"  Screenshot: {local_path}")
    return local_path


def cmd_press(*buttons: str):
    """Send button presses to MiSTer via keyboard event injection."""
    if not buttons:
        print("Usage: mister.py press START|A|B|UP|DOWN|LEFT|RIGHT|SELECT|L|R|OSD")
        print(f"Available buttons: {', '.join(KEY_MAP.keys())}")
        return

    # Build a Python script to run on MiSTer
    key_presses = []
    for btn in buttons:
        btn_upper = btn.upper()
        if btn_upper not in KEY_MAP:
            print(f"Unknown button: {btn}. Available: {', '.join(KEY_MAP.keys())}")
            return
        key_presses.append((btn_upper, KEY_MAP[btn_upper]))

    script_lines = [
        "import struct, os, time",
        "EV_KEY, EV_SYN, SYN_REPORT = 1, 0, 0",
        "def send_key(fd, key, value):",
        "    t = time.time(); sec = int(t); usec = int((t - sec) * 1e6)",
        "    os.write(fd, struct.pack('llHHi', sec, usec, EV_KEY, key, value))",
        "    os.write(fd, struct.pack('llHHi', sec, usec, EV_SYN, SYN_REPORT, 0))",
        f"fd = os.open('{KEYBOARD_EVENT}', os.O_WRONLY)",
    ]
    for name, code in key_presses:
        script_lines.extend([
            f"send_key(fd, {code}, 1)  # {name} down",
            "time.sleep(0.08)",
            f"send_key(fd, {code}, 0)  # {name} up",
            "time.sleep(0.15)",
        ])
    script_lines.append("os.close(fd)")
    script_lines.append(f"print('Sent: {' '.join(b[0] for b in key_presses)}')")

    script = "\n".join(script_lines)
    result = ssh(f"python3 -c {shlex.quote(script)}")
    if result.returncode == 0:
        print(f"  Pressed: {' '.join(b[0] for b in key_presses)}")
    else:
        print(f"  ERROR: {result.stderr}")


def cmd_savestate(action: str = "save", slot: str = "1"):
    """Manage save states on MiSTer.

    MiSTer save states are triggered via OSD keyboard shortcuts:
      Alt+F1-F4 = save to slot 1-4
      F1-F4 = load from slot 1-4
    """
    slot_num = int(slot)
    if slot_num < 1 or slot_num > 4:
        print("Slot must be 1-4")
        return

    # F1=59, F2=60, F3=61, F4=62 in Linux input event codes
    f_key = 58 + slot_num
    alt_key = 56  # KEY_LEFTALT

    corename = get_corename()
    state_dir = f"{MISTER_SAVESTATES_DIR}/{corename}"
    rom_stem = MISTER_ROM_NAME.rsplit('.', 1)[0]
    state_file = f"{state_dir}/{rom_stem}_{slot_num}.ss"

    if action == "save":
        print(f"Saving state to slot {slot_num}...")
        # Send Alt+F{slot} for save
        script = f"""
import struct, os, time
EV_KEY, EV_SYN = 1, 0
def ev(fd, t, c, v):
    now = time.time(); s = int(now); u = int((now-s)*1e6)
    os.write(fd, struct.pack('llHHi', s, u, t, c, v))
    os.write(fd, struct.pack('llHHi', s, u, EV_SYN, 0, 0))
fd = os.open('{KEYBOARD_EVENT}', os.O_WRONLY)
ev(fd, EV_KEY, {alt_key}, 1)  # Alt down
time.sleep(0.05)
ev(fd, EV_KEY, {f_key}, 1)    # F{slot_num} down
time.sleep(0.1)
ev(fd, EV_KEY, {f_key}, 0)    # F{slot_num} up
time.sleep(0.05)
ev(fd, EV_KEY, {alt_key}, 0)  # Alt up
os.close(fd)
print('Sent Alt+F{slot_num}')
"""
        ssh(f"python3 -c {shlex.quote(script)}")
        time.sleep(1)
        # Verify
        result = ssh(f"ls -la {state_file} 2>/dev/null")
        if result.stdout.strip():
            print(f"  Saved: {state_file}")
        else:
            print(f"  WARNING: State file not found at {state_file}")
            # Check alternate naming
            result = ssh(f"ls -lt {state_dir}/ 2>/dev/null | head -5")
            print(f"  Recent files: {result.stdout.strip()}")

    elif action == "load":
        print(f"Loading state from slot {slot_num}...")
        # Send F{slot} for load
        script = f"""
import struct, os, time
EV_KEY, EV_SYN = 1, 0
def ev(fd, t, c, v):
    now = time.time(); s = int(now); u = int((now-s)*1e6)
    os.write(fd, struct.pack('llHHi', s, u, t, c, v))
    os.write(fd, struct.pack('llHHi', s, u, EV_SYN, 0, 0))
fd = os.open('{KEYBOARD_EVENT}', os.O_WRONLY)
ev(fd, EV_KEY, {f_key}, 1)    # F{slot_num} down
time.sleep(0.1)
ev(fd, EV_KEY, {f_key}, 0)    # F{slot_num} up
os.close(fd)
print('Sent F{slot_num}')
"""
        ssh(f"python3 -c {shlex.quote(script)}")
        print(f"  Sent load state slot {slot_num}")

    elif action == "fetch":
        print(f"Fetching save state from slot {slot_num}...")
        local_path = LOCAL_SAVESTATES / f"mister_slot{slot_num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ss"
        try:
            scp_from_mister(state_file, local_path)
            print(f"  Downloaded: {local_path}")
        except RuntimeError:
            print(f"  ERROR: State file not found: {state_file}")

    else:
        print(f"Unknown action: {action}. Use save/load/fetch")


def cmd_backup(version: str = None):
    """Backup ROM, save states, and screenshots to blackmage."""
    # Guard before creating anything on the backup host.
    require_mister_reservation()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_str = f"_v{version}" if version else ""
    backup_name = f"penta_dragon_dx{version_str}_{timestamp}"
    remote_dir = f"{BLACKMAGE_BACKUP_DIR}/{backup_name}"

    print(f"Backing up to {BLACKMAGE_USER}@{BLACKMAGE_HOST}:{remote_dir}")

    # Create backup dir on blackmage
    bm_ssh = lambda cmd: subprocess.run(
        ["ssh", f"{BLACKMAGE_USER}@{BLACKMAGE_HOST}", cmd],
        capture_output=True, text=True, timeout=30
    )
    bm_scp = lambda src, dst: subprocess.run(
        ["scp", src, f"{BLACKMAGE_USER}@{BLACKMAGE_HOST}:{dst}"],
        capture_output=True, text=True, timeout=60
    )

    bm_ssh(f"mkdir -p {remote_dir}/screenshots {remote_dir}/savestates")

    # 1. Backup local ROM
    if LOCAL_ROM.exists():
        print("  Backing up ROM...")
        result = bm_scp(str(LOCAL_ROM), f"{remote_dir}/{MISTER_ROM_NAME}")
        if result.returncode == 0:
            print(f"    ROM: OK")
        else:
            print(f"    ROM: FAILED - {result.stderr}")

    # 2. Fetch and backup save states from MiSTer
    corename = get_corename()
    state_dir = f"{MISTER_SAVESTATES_DIR}/{corename}"
    states = ssh(f"ls {state_dir}/ 2>/dev/null").stdout.strip().split('\n')
    states = [s for s in states if s and 'penta' in s.lower()]

    for state_name in states:
        print(f"  Backing up save state: {state_name}")
        local_tmp = LOCAL_TMP / state_name
        try:
            scp_from_mister(f"{state_dir}/{state_name}", local_tmp)
            result = bm_scp(str(local_tmp), f"{remote_dir}/savestates/{state_name}")
            if result.returncode == 0:
                print(f"    {state_name}: OK")
            local_tmp.unlink(missing_ok=True)
        except RuntimeError as e:
            print(f"    {state_name}: FAILED - {e}")

    # 3. Fetch and backup screenshots from MiSTer
    for sc_dir in ["GBC", "GAMEBOY"]:
        sc_path = f"{MISTER_SCREENSHOTS_DIR}/{sc_dir}"
        shots = ssh(f"ls {sc_path}/ 2>/dev/null").stdout.strip().split('\n')
        shots = [s for s in shots if s and 'penta' in s.lower()]
        for shot_name in shots:
            print(f"  Backing up screenshot: {shot_name}")
            local_tmp = LOCAL_TMP / shot_name
            try:
                scp_from_mister(f"{sc_path}/{shot_name}", local_tmp)
                result = bm_scp(str(local_tmp), f"{remote_dir}/screenshots/{shot_name}")
                if result.returncode == 0:
                    print(f"    {shot_name}: OK")
                local_tmp.unlink(missing_ok=True)
            except RuntimeError as e:
                print(f"    {shot_name}: FAILED - {e}")

    # 4. Backup local save states too
    local_states = list(Path("save_states_for_claude").glob("*.ss0"))
    if local_states:
        bm_ssh(f"mkdir -p {remote_dir}/save_states_for_claude")
        for ss in local_states[:5]:  # Just the most recent 5
            result = bm_scp(str(ss), f"{remote_dir}/save_states_for_claude/{ss.name}")
            if result.returncode == 0:
                print(f"    local state {ss.name}: OK")

    print(f"\nBackup complete: {BLACKMAGE_USER}@{BLACKMAGE_HOST}:{remote_dir}")


def cmd_play(seconds: str = "10"):
    """Launch game, wait, then take a screenshot."""
    wait = int(seconds)
    cmd_launch()
    print(f"Waiting {wait}s for game to render...")
    time.sleep(wait)
    path = cmd_screenshot("gameplay")
    if path:
        print(f"\nGameplay screenshot: {path}")


def cmd_clean_screenshots():
    """Clean up screenshots on MiSTer."""
    for d in ["GBC", "GAMEBOY"]:
        ssh(f"rm -f {MISTER_SCREENSHOTS_DIR}/{d}/*.png 2>/dev/null")
    print("Cleaned MiSTer screenshots")


def cmd_reset():
    """Reset the current core on MiSTer by reloading the game via MGL."""
    print("Resetting game on MiSTer...")
    # Reloading the MGL re-initializes the core and reloads the ROM fresh
    mgl = MGL_TEMPLATE.format(core=MISTER_CORE, rom_path=MISTER_ROM_PATH)
    ssh(f"cat > {MISTER_MGL_PATH} << 'MGLEOF'\n{mgl}\nMGLEOF")
    mister_cmd(f"load_core {MISTER_MGL_PATH}")
    print("  Sent load_core command (game will restart fresh)")
    time.sleep(4)
    corename = get_corename()
    print(f"  Core: {corename}")
    if corename == "GBC":
        print("  Reset successful.")
    else:
        print(f"  WARNING: Expected CORENAME=GBC, got {corename}")


def cmd_pause():
    """Toggle pause ON on MiSTer via OSD P key (keycode 25)."""
    print("Sending pause toggle (P key)...")
    _send_raw_key(25, "P (pause)")


def cmd_unpause():
    """Toggle pause OFF on MiSTer via OSD P key (keycode 25).

    Note: pause and unpause both send the same P key toggle.
    They are separate commands for readability in scripts.
    """
    print("Sending unpause toggle (P key)...")
    _send_raw_key(25, "P (unpause)")


def _send_raw_key(keycode: int, label: str = "key"):
    """Send a single raw key press/release to MiSTer keyboard event device."""
    script = "\n".join([
        "import struct, os, time",
        "EV_KEY, EV_SYN = 1, 0",
        "def ev(fd, c, v):",
        "    t = time.time(); s = int(t); u = int((t-s)*1e6)",
        "    os.write(fd, struct.pack('llHHi', s, u, EV_KEY, c, v))",
        "    os.write(fd, struct.pack('llHHi', s, u, EV_SYN, 0, 0))",
        f"fd = os.open('{KEYBOARD_EVENT}', os.O_WRONLY)",
        f"ev(fd, {keycode}, 1)",
        "time.sleep(0.08)",
        f"ev(fd, {keycode}, 0)",
        "os.close(fd)",
        f"print('Sent {label}')",
    ])
    result = ssh(f"python3 -c {shlex.quote(script)}")
    if result.returncode == 0:
        print(f"  Sent: {label}")
    else:
        print(f"  ERROR: {result.stderr}")


def cmd_osd():
    """Open/close the OSD menu on MiSTer (F12 key, keycode 88)."""
    print("Toggling OSD menu (F12)...")
    _send_raw_key(88, "F12 (OSD)")


def cmd_navigate(*buttons: str):
    """Send button presses with 0.3s delays between them for menu navigation.

    Like press, but with longer inter-press delays suitable for navigating
    OSD menus and game menus where timing matters.
    """
    if not buttons:
        print("Usage: mister.py navigate START A DOWN DOWN A")
        print(f"Available buttons: {', '.join(KEY_MAP.keys())}")
        return

    # Validate all buttons first
    for btn in buttons:
        if btn.upper() not in KEY_MAP:
            print(f"Unknown button: {btn}. Available: {', '.join(KEY_MAP.keys())}")
            return

    print(f"Navigating: {' -> '.join(b.upper() for b in buttons)} (0.3s between presses)")

    # Build a single SSH script with 0.3s delays between presses
    key_presses = [(btn.upper(), KEY_MAP[btn.upper()]) for btn in buttons]

    script_lines = [
        "import struct, os, time",
        "EV_KEY, EV_SYN = 1, 0",
        "def ev(fd, c, v):",
        "    t = time.time(); s = int(t); u = int((t-s)*1e6)",
        "    os.write(fd, struct.pack('llHHi', s, u, EV_KEY, c, v))",
        "    os.write(fd, struct.pack('llHHi', s, u, EV_SYN, 0, 0))",
        f"fd = os.open('{KEYBOARD_EVENT}', os.O_WRONLY)",
    ]
    for i, (name, code) in enumerate(key_presses):
        if i > 0:
            script_lines.append("time.sleep(0.3)")  # 0.3s delay between presses
        script_lines.extend([
            f"ev(fd, {code}, 1)  # {name} down",
            "time.sleep(0.08)",
            f"ev(fd, {code}, 0)  # {name} up",
        ])
    script_lines.append("os.close(fd)")
    names_str = " -> ".join(b[0] for b in key_presses)
    script_lines.append(f"print('Navigate: {names_str}')")

    script = "\n".join(script_lines)
    result = ssh(f"python3 -c {shlex.quote(script)}", timeout=60)
    if result.returncode == 0:
        print(f"  Navigation complete: {' -> '.join(b[0] for b in key_presses)}")
    else:
        print(f"  ERROR: {result.stderr}")


def cmd_game_start():
    """Macro: launch game, wait for title screen, navigate menus to reach gameplay.

    Verified sequence (matches mgba Lua automation):
      1. Launch game via MGL (6s wait for core init)
      2. Wait 8s for title screen to appear
      3. Press DOWN (move cursor from OPENING START to GAME START)
      4. Press A (select GAME START → level select screen)
      5. Wait 2s for level select to load
      6. Press A (start level from level select)
      7. Press A again (confirm)
      8. Wait 2s
      9. Take screenshot to verify gameplay

    NOTE: MiSTer remote input injection via /dev/input/event* is currently
    broken (framework uses EVIOCGRAB). This macro documents the correct
    sequence but may not work until input injection is fixed.
    """
    print("=== Game Start Macro ===")

    # Step 1: Launch
    cmd_launch()

    # Step 2: Wait for title screen
    print("Waiting 8s for title screen...")
    time.sleep(8)

    # Step 3: DOWN to move cursor to GAME START
    print("Pressing DOWN (cursor → GAME START)...")
    cmd_press("DOWN")
    time.sleep(0.5)

    # Step 4: A to select GAME START
    print("Pressing A (select GAME START)...")
    cmd_press("A")
    time.sleep(2)

    # Step 5: A to start level from level select
    print("Pressing A (level select → start level)...")
    cmd_press("A")
    time.sleep(1)

    # Step 6: A again (confirm)
    print("Pressing A (confirm)...")
    cmd_press("A")
    time.sleep(2)

    # Step 7: Verification screenshot
    print("Taking verification screenshot...")
    path = cmd_screenshot("game_start")
    if path:
        print(f"\n=== Game started! Screenshot: {path} ===")
    else:
        raise RuntimeError("game-start verification screenshot capture failed")


def cmd_capture_gameplay(seconds: str = "10", label: str = "gameplay"):
    """Launch game, navigate to gameplay, take periodic screenshots.

    Args:
        seconds: Total capture duration in seconds (default: 10)
        label: Label prefix for screenshot files (default: gameplay)
    """
    duration = int(seconds)
    interval = 2  # Screenshot every 2 seconds

    print(f"=== Capture Gameplay: {duration}s, label={label} ===")

    # Start the game
    cmd_game_start()

    # Take periodic screenshots
    screenshots = []
    elapsed = 0
    shot_num = 0
    while elapsed < duration:
        time.sleep(interval)
        elapsed += interval
        shot_num += 1
        shot_label = f"{label}_{shot_num:03d}"
        print(f"  Capturing screenshot {shot_num} at {elapsed}s...")
        path = cmd_screenshot(shot_label)
        if path:
            screenshots.append(path)

    print(f"\n=== Capture complete: {len(screenshots)} screenshots ===")
    for p in screenshots:
        print(f"  {p}")


def cmd_deploy_and_test(version: str = None):
    """Full pipeline: build -> deploy -> launch -> wait -> screenshot -> backup.

    Args:
        version: Optional version string for the build script (e.g., "262").
                 If not provided, skips the build step and just deploys
                 whatever ROM is currently in rom/working/.
    """
    # Guard before an optional build or any hardware-facing pipeline step.
    require_mister_reservation()
    print("=== Deploy and Test Pipeline ===")

    # Step 1: Build (if version provided)
    if version:
        build_script = PROJECT_ROOT / "scripts" / f"create_vblank_colorizer_v{version}.py"
        if not build_script.exists():
            print(f"ERROR: Build script not found: {build_script}")
            sys.exit(1)
        print(f"Step 1: Building v{version}...")
        result = subprocess.run(
            ["uv", "run", "python", str(build_script)],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"  BUILD FAILED:\n{result.stderr}")
            sys.exit(1)
        print(f"  Build complete.")
    else:
        print("Step 1: Skipping build (no version specified)")

    # Step 2: Deploy
    print("Step 2: Deploying ROM...")
    cmd_deploy()

    # Step 3: Launch
    print("Step 3: Launching game...")
    cmd_launch()

    # Step 4: Wait for rendering
    print("Step 4: Waiting 10s for game to render...")
    time.sleep(10)

    # Step 5: Screenshot
    print("Step 5: Taking screenshot...")
    version_label = f"v{version}" if version else "test"
    path = cmd_screenshot(f"deploy_test_{version_label}")

    # Step 6: Backup (optional, only if version given)
    if version:
        print(f"Step 6: Backing up v{version}...")
        try:
            cmd_backup(version)
        except Exception as e:
            print(f"  Backup failed (non-fatal): {e}")

    if not path:
        raise RuntimeError("deploy-and-test screenshot capture failed")
    print(f"\n=== Deploy and test complete! Screenshot: {path} ===")


def cmd_fetch_screenshot():
    """Fetch the latest screenshot from MiSTer without taking a new one.

    Finds the most recent .png in the MiSTer screenshots directory and
    downloads it locally.
    """
    print("Fetching latest screenshot from MiSTer...")

    # Check both possible screenshot directories
    latest_file = None
    latest_dir = None
    latest_mtime = 0

    for sc_dir in ["GBC", "GAMEBOY"]:
        sc_path = f"{MISTER_SCREENSHOTS_DIR}/{sc_dir}"
        result = ssh(f"ls -t {sc_path}/*.png 2>/dev/null | head -1")
        if result.returncode == 0 and result.stdout.strip():
            filepath = result.stdout.strip()
            # Get mtime for comparison
            mtime_result = ssh(f"stat -c %Y {shlex.quote(filepath)} 2>/dev/null")
            if mtime_result.returncode == 0 and mtime_result.stdout.strip():
                mtime = int(mtime_result.stdout.strip())
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_file = filepath.split('/')[-1]
                    latest_dir = sc_path

    if not latest_file or not latest_dir:
        print("  No screenshots found on MiSTer.")
        return None

    remote_path = f"{latest_dir}/{latest_file}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_name = f"mister_{timestamp}_fetched.png"
    local_path = LOCAL_SCREENSHOTS / local_name

    scp_from_mister(remote_path, local_path)
    print(f"  Fetched: {remote_path}")
    print(f"  Local:   {local_path}")
    return local_path


def cmd_list_states():
    """List save states available on MiSTer for the current game."""
    print("Save states on MiSTer:")

    for coredir in ["GBC", "GAMEBOY", "Gameboy"]:
        state_dir = f"{MISTER_SAVESTATES_DIR}/{coredir}"
        result = ssh(f"ls -la {state_dir}/ 2>/dev/null")
        if result.returncode == 0 and result.stdout.strip():
            files = [
                line for line in result.stdout.strip().split('\n')
                if line and not line.startswith('total')
            ]
            if files:
                print(f"\n  {state_dir}/:")
                for f in files:
                    print(f"    {f}")

    # Also check the active corename directory
    corename = get_corename()
    if corename not in ["GBC", "GAMEBOY", "Gameboy", "UNKNOWN"]:
        state_dir = f"{MISTER_SAVESTATES_DIR}/{corename}"
        result = ssh(f"ls -la {state_dir}/ 2>/dev/null")
        if result.returncode == 0 and result.stdout.strip():
            files = [
                line for line in result.stdout.strip().split('\n')
                if line and not line.startswith('total')
            ]
            if files:
                print(f"\n  {state_dir}/:")
                for f in files:
                    print(f"    {f}")


# === Cheat System ===
# MiSTer .gg format: 4 x 32-bit LE ints per entry [flag, address, compare, replace]
# flag=0 means unconditional write, flag=1 means compare-then-write
# Multiple entries concatenated. Files go in a zip named to match the ROM.

MISTER_CHEATS_DIR = "/media/fat/cheats"
LOCAL_CHEATS = LOCAL_TMP / "cheats"

# All known cheats from reverse engineering (see reverse_engineering/notes/game_memory_map.md)
CHEATS = {
    # Health
    "Infinite Health": [
        (0xDCDD, 0x17),   # Main HP = 23
        (0xDCDC, 0xFF),   # Sub-counter = max
    ],
    # Mini-bosses (FFBF 1-2)
    "Mini-Boss 1 Gargoyle": [(0xFFBF, 0x01)],
    "Mini-Boss 2 Spider": [(0xFFBF, 0x02)],
    # Bosses (FFBF 3-8)
    "Boss 3 Crimson": [(0xFFBF, 0x03)],
    "Boss 4 Ice": [(0xFFBF, 0x04)],
    "Boss 5 Void": [(0xFFBF, 0x05)],
    "Boss 6 Poison": [(0xFFBF, 0x06)],
    "Boss 7 Knight": [(0xFFBF, 0x07)],
    "Boss 8 Angela": [(0xFFBF, 0x08)],
    # Sara form
    "Sara Dragon Form": [(0xFFBE, 0x01)],
    "Sara Witch Form": [(0xFFBE, 0x00)],
    # Powerups
    "Powerup Spiral": [(0xFFC0, 0x01)],
    "Powerup Shield": [(0xFFC0, 0x02)],
    "Powerup Turbo": [(0xFFC0, 0x03)],
    # Room warps (FFBD + FFE5 mirror)
    "Room 1": [(0xFFBD, 0x01), (0xFFE5, 0x01)],
    "Room 2": [(0xFFBD, 0x02), (0xFFE5, 0x02)],
    "Room 3": [(0xFFBD, 0x03), (0xFFE5, 0x03)],
    "Room 4": [(0xFFBD, 0x04), (0xFFE5, 0x04)],
    "Room 5": [(0xFFBD, 0x05), (0xFFE5, 0x05)],
    "Room 6": [(0xFFBD, 0x06), (0xFFE5, 0x06)],
    "Room 7": [(0xFFBD, 0x07), (0xFFE5, 0x07)],
    # Bonus stage
    "Bonus Stage": [(0xFFD0, 0x01)],
    # Menu navigation fix — forces cursor to GAME START (DCFD=1)
    "Force GAME START": [(0xDCFD, 0x01)],
}


def make_gg(entries: list[tuple[int, int]]) -> bytes:
    """Create a .gg binary from a list of (address, value) pairs."""
    data = b""
    for addr, val in entries:
        # flag=0 (unconditional), address (LE), compare=0, replace (LE)
        data += struct.pack("<IIII", 0, addr, 0, val)
    return data


def cmd_cheats(action: str = "build"):
    """Generate and deploy MiSTer cheat codes for Penta Dragon DX.

    Actions:
        build  - Generate cheat zip locally (default)
        deploy - Generate and deploy to MiSTer
        list   - Show all available cheats
    """
    if action == "deploy":
        # Guard before even creating the local deployment artifact.
        require_mister_reservation()

    if action == "list":
        print("Available cheats for Penta Dragon DX:")
        for name, entries in CHEATS.items():
            desc = ", ".join(f"[{a:04X}]={v:02X}" for a, v in entries)
            print(f"  {name:30s}  {desc}")
        return

    # Build the zip
    LOCAL_CHEATS.mkdir(parents=True, exist_ok=True)
    rom_stem = MISTER_ROM_NAME.rsplit(".", 1)[0]
    zip_path = LOCAL_CHEATS / f"{rom_stem}.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, entries in CHEATS.items():
            gg_data = make_gg(entries)
            zf.writestr(f"{name}.gg", gg_data)

    cheat_count = len(CHEATS)
    print(f"Built {zip_path.name} ({cheat_count} cheats, {zip_path.stat().st_size} bytes)")

    if action == "deploy":
        # Try both possible cheat directories
        for cheat_dir in ["GBC", "Gameboy"]:
            remote_dir = f"{MISTER_CHEATS_DIR}/{cheat_dir}"
            ssh(f"mkdir -p {remote_dir}")

        # Deploy to GBC (primary)
        remote_path = f"{MISTER_CHEATS_DIR}/GBC/{rom_stem}.zip"
        scp_to_mister(zip_path, remote_path)
        print(f"  Deployed to MiSTer:{remote_path}")

        # Also copy to Gameboy dir in case core looks there
        remote_path2 = f"{MISTER_CHEATS_DIR}/Gameboy/{rom_stem}.zip"
        scp_to_mister(zip_path, remote_path2)
        print(f"  Deployed to MiSTer:{remote_path2}")

        print(f"\nTo use: OSD (F12) -> Cheats -> toggle individual cheats on/off")
    elif action != "build":
        print(f"Unknown action: {action}. Use build/deploy/list")


def cmd_clean_old_roms():
    """Clean old versioned ROMs from MiSTer GBC directory, keeping only FIXED.

    Removes any penta_dragon_dx_*.gbc files that are NOT the main FIXED ROM.
    This saves space on the MiSTer SD card.
    """
    print("Cleaning old ROMs from MiSTer...")

    # List all penta dragon ROMs
    result = ssh(f"ls -la {MISTER_ROM_DIR}/penta_dragon_dx_*.gbc 2>/dev/null")
    if result.returncode != 0 or not result.stdout.strip():
        print("  No penta dragon ROMs found.")
        return

    lines = [l for l in result.stdout.strip().split('\n') if l and not l.startswith('total')]
    keep_name = MISTER_ROM_NAME
    removed = 0
    kept = 0

    for line in lines:
        # Extract filename from ls -la output (last field)
        parts = line.split()
        if not parts:
            continue
        filename = parts[-1].split('/')[-1]

        if filename == keep_name:
            print(f"  KEEP: {filename}")
            kept += 1
        else:
            print(f"  REMOVE: {filename}")
            ssh(f"rm -f {MISTER_ROM_DIR}/{shlex.quote(filename)}")
            removed += 1

    print(f"\n  Kept {kept} ROM(s), removed {removed} old ROM(s).")


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def md5_file(path: Path) -> str:
    value = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must contain one JSON object: {path}")
    return value


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def verify_release_sweep_inputs(emulator_manifest_path: Path) -> tuple[dict, str]:
    """Validate the exact local ROM/IPS/emulator evidence before hardware use."""
    if not LOCAL_ROM.is_file():
        raise RuntimeError(f"release ROM not found: {LOCAL_ROM}")
    if not LOCAL_RELEASE_PATCH.is_file():
        raise RuntimeError(f"release IPS not found: {LOCAL_RELEASE_PATCH}")
    if not emulator_manifest_path.is_file():
        raise RuntimeError(
            f"emulator release manifest not found: {emulator_manifest_path}"
        )

    local_md5 = md5_file(LOCAL_ROM)
    emulator = load_json_object(emulator_manifest_path, "emulator manifest")
    required_values = {
        "status": "emulator-pass",
        "scope": "full",
        "failures": 0,
        "rom_md5": local_md5,
        "source_rom_md5_after": local_md5,
        "tested_rom_md5_after": local_md5,
        "rom_hashes_intact": True,
    }
    for key, expected in required_values.items():
        if emulator.get(key) != expected:
            raise RuntimeError(
                f"emulator manifest {key} does not match {expected!r}"
            )

    results = emulator.get("results")
    if not isinstance(results, list) or len(results) != 30:
        raise RuntimeError("hardware sweep requires all 30 emulator gate results")
    incomplete = [
        item.get("name", "<invalid>")
        for item in results
        if not isinstance(item, dict)
        or item.get("status") != "passed"
        or item.get("returncode") != 0
    ]
    if incomplete:
        raise RuntimeError(f"emulator manifest has incomplete gates: {incomplete}")

    patch_result = subprocess.run(
        [
            sys.executable,
            str(RELEASE_PATCH_VERIFIER),
            str(LOCAL_ROM),
            "--patch",
            str(LOCAL_RELEASE_PATCH),
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if patch_result.returncode != 0:
        detail = patch_result.stdout.strip() or patch_result.stderr.strip()
        raise RuntimeError(f"release IPS preflight failed: {detail}")
    return emulator, local_md5


def validate_local_png(path: Path) -> None:
    try:
        header = path.read_bytes()[:24]
    except OSError as exc:
        raise RuntimeError(f"could not read MiSTer screenshot {path}: {exc}") from exc
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"MiSTer screenshot is not a valid PNG: {path}")


def find_checkpoint(manifest: dict, name: str) -> dict:
    checkpoints = manifest.get("checkpoints")
    if not isinstance(checkpoints, list):
        raise RuntimeError("hardware manifest has no checkpoint list")
    matches = [
        item
        for item in checkpoints
        if isinstance(item, dict) and item.get("name") == name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"hardware checkpoint {name!r} is absent or duplicated"
        )
    return matches[0]


def verify_live_sweep_identity(manifest: dict) -> None:
    """Recheck reservation, core, deployed ROM, and local evidence."""
    require_mister_reservation()
    if manifest.get("schema") != "penta-dragon-dx-mister-release-v1":
        raise RuntimeError("unsupported MiSTer release manifest schema")
    if manifest.get("status") not in {
        "hardware-sweep-incomplete",
        "hardware-pass",
    }:
        raise RuntimeError(
            f"invalid hardware sweep status: {manifest.get('status')!r}"
        )
    if manifest.get("mister_host") != MISTER_HOST:
        raise RuntimeError("hardware sweep is bound to a different MiSTer host")
    if md5_file(LOCAL_ROM) != manifest.get("rom_md5"):
        raise RuntimeError("local release ROM changed during the hardware sweep")
    if sha256_file(LOCAL_ROM) != manifest.get("rom_sha256"):
        raise RuntimeError("local release ROM SHA-256 changed during the sweep")
    if sha256_file(LOCAL_RELEASE_PATCH) != manifest.get("release_patch_sha256"):
        raise RuntimeError("release IPS changed during the hardware sweep")

    emulator_path = Path(manifest.get("emulator_manifest", ""))
    if (
        not emulator_path.is_file()
        or sha256_file(emulator_path)
        != manifest.get("emulator_manifest_sha256")
    ):
        raise RuntimeError("emulator release manifest changed during the sweep")

    corename = get_corename()
    if corename != "GBC":
        raise RuntimeError(
            f"hardware sweep requires active CORENAME=GBC, got {corename!r}"
        )
    remote_md5 = get_rom_md5()
    if remote_md5 != manifest.get("rom_md5"):
        raise RuntimeError(
            "MiSTer deployed ROM no longer matches the release candidate"
        )


def cmd_release_sweep_start(emulator_manifest: str = ""):
    """Deploy and start a reservation-backed, hash-bound physical sweep."""
    if not emulator_manifest:
        raise RuntimeError(
            "usage: mister.py release_sweep_start EMULATOR_MANIFEST"
        )
    emulator_path = Path(emulator_manifest).resolve()
    emulator, local_md5 = verify_release_sweep_inputs(emulator_path)

    # The main dispatcher already checked the reservation. Recheck at every
    # hardware boundary through cmd_deploy/cmd_launch/cmd_screenshot as well.
    cmd_deploy()
    if get_rom_md5() != local_md5:
        raise RuntimeError("MiSTer ROM hash differs immediately after deployment")
    cmd_launch()
    time.sleep(10)
    title_screenshot = cmd_screenshot("release_title_unconfirmed")
    if title_screenshot is None:
        raise RuntimeError("release sweep could not capture the title screen")
    validate_local_png(title_screenshot)

    now = utc_now()
    checkpoint_rows = [
        {"name": name, "status": "pending"} for name in REQUIRED_HARDWARE_CHECKPOINTS
    ]
    for name, evidence in (
        ("gbc_core", {"core": "GBC"}),
        ("deployed_rom_hash", {"remote_md5": local_md5}),
    ):
        row = next(item for item in checkpoint_rows if item["name"] == name)
        row.update({"status": "passed", "confirmed_at": now, "evidence": evidence})
    title = next(item for item in checkpoint_rows if item["name"] == "title")
    title.update(
        {
            "status": "captured-pending-human",
            "captured_at": now,
            "evidence": {
                "screenshot": str(title_screenshot.resolve()),
                "screenshot_sha256": sha256_file(title_screenshot),
            },
        }
    )

    reservation_id = os.environ["MISTER_RESERVATION_ID"].strip()
    manifest = {
        "schema": "penta-dragon-dx-mister-release-v1",
        "status": "hardware-sweep-incomplete",
        "started_at": now,
        "finished_at": None,
        "mister_host": MISTER_HOST,
        "reservation_id_sha256": hashlib.sha256(
            reservation_id.encode("utf-8")
        ).hexdigest(),
        "rom_md5": local_md5,
        "rom_sha256": sha256_file(LOCAL_ROM),
        "release_patch_sha256": sha256_file(LOCAL_RELEASE_PATCH),
        "emulator_manifest": str(emulator_path),
        "emulator_manifest_sha256": sha256_file(emulator_path),
        "emulator_gates_passed": len(emulator["results"]),
        "checkpoints": checkpoint_rows,
        "instructions": (
            "Navigate with the physical controller. Capture each checkpoint "
            "with release_checkpoint and pass literal 'confirm' only after "
            "visually inspecting the live MiSTer output."
        ),
    }
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    sweep_dir = LOCAL_RELEASE_SWEEPS / f"{timestamp}_{local_md5[:8]}"
    manifest_path = sweep_dir / "manifest.json"
    write_json_atomic(manifest_path, manifest)
    print(f"PASS: MiSTer release sweep started: {manifest_path}")
    print("PENDING: title visual confirmation and eight physical game checkpoints")
    print(
        "Next: python3 scripts/mister.py release_checkpoint "
        f"{manifest_path} title confirm"
    )


def cmd_release_checkpoint(
    hardware_manifest: str = "",
    checkpoint_name: str = "",
    confirmation: str = "",
):
    """Capture one physical checkpoint; pass 'confirm' after visual review."""
    if not hardware_manifest or not checkpoint_name:
        raise RuntimeError(
            "usage: mister.py release_checkpoint "
            "HARDWARE_MANIFEST CHECKPOINT [confirm]"
        )
    if confirmation and confirmation.lower() != "confirm":
        raise RuntimeError("the only accepted confirmation token is 'confirm'")

    path = Path(hardware_manifest).resolve()
    manifest = load_json_object(path, "hardware manifest")
    if manifest.get("status") != "hardware-sweep-incomplete":
        raise RuntimeError("only an incomplete hardware sweep can be updated")
    checkpoint = find_checkpoint(manifest, checkpoint_name)
    if checkpoint_name in {"gbc_core", "deployed_rom_hash"}:
        raise RuntimeError(f"{checkpoint_name} is verified automatically")

    verify_live_sweep_identity(manifest)
    screenshot = cmd_screenshot(f"release_{checkpoint_name}")
    if screenshot is None:
        raise RuntimeError(f"could not capture checkpoint {checkpoint_name}")
    validate_local_png(screenshot)

    now = utc_now()
    checkpoint.clear()
    checkpoint.update(
        {
            "name": checkpoint_name,
            "status": "passed" if confirmation else "captured-pending-human",
            "captured_at": now,
            "evidence": {
                "screenshot": str(screenshot.resolve()),
                "screenshot_sha256": sha256_file(screenshot),
            },
        }
    )
    if confirmation:
        checkpoint["confirmed_at"] = now
        checkpoint["confirmation"] = "explicit-human"
    manifest["last_updated_at"] = now
    write_json_atomic(path, manifest)
    print(
        f"{'PASS' if confirmation else 'PENDING'}: checkpoint "
        f"{checkpoint_name} captured at {screenshot}"
    )
    if not confirmation:
        print("Re-run with the final argument 'confirm' after visual inspection.")


def cmd_release_sweep_finish(hardware_manifest: str = ""):
    """Seal hardware-pass only when every physical checkpoint is confirmed."""
    if not hardware_manifest:
        raise RuntimeError(
            "usage: mister.py release_sweep_finish HARDWARE_MANIFEST"
        )
    path = Path(hardware_manifest).resolve()
    manifest = load_json_object(path, "hardware manifest")
    if manifest.get("status") != "hardware-sweep-incomplete":
        raise RuntimeError("hardware sweep is not in an incomplete state")
    verify_live_sweep_identity(manifest)

    names = [
        item.get("name")
        for item in manifest.get("checkpoints", [])
        if isinstance(item, dict)
    ]
    if len(names) != len(REQUIRED_HARDWARE_CHECKPOINTS) or set(names) != set(
        REQUIRED_HARDWARE_CHECKPOINTS
    ):
        raise RuntimeError("hardware sweep checkpoint set is incomplete or altered")
    incomplete = [
        item.get("name")
        for item in manifest["checkpoints"]
        if item.get("status") != "passed"
    ]
    if incomplete:
        raise RuntimeError(
            f"cannot seal hardware pass; incomplete checkpoints: {incomplete}"
        )
    for item in manifest["checkpoints"]:
        if item["name"] not in {"gbc_core", "deployed_rom_hash"}:
            screenshot = Path(item.get("evidence", {}).get("screenshot", ""))
            expected = item.get("evidence", {}).get("screenshot_sha256")
            if not screenshot.is_file() or sha256_file(screenshot) != expected:
                raise RuntimeError(
                    f"checkpoint evidence changed or is missing: {item['name']}"
                )

    manifest["status"] = "hardware-pass"
    manifest["finished_at"] = utc_now()
    write_json_atomic(path, manifest)
    print(f"PASS: sealed hash-bound MiSTer hardware manifest {path}")


# === Main ===

def command_requires_reservation(command: str, args: list[str]) -> bool:
    """Return whether the CLI invocation can contact or affect MiSTer."""
    if command == "reservation_check":
        return False
    if command == "cheats":
        action = args[0].lower() if args else "build"
        return action == "deploy"
    return True


def cmd_reservation_check():
    """Validate the configured reservation without contacting MiSTer."""
    require_mister_reservation()
    print(f"MiSTer reservation verified for host {MISTER_HOST!r}.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "status": lambda: cmd_status(),
        "deploy": lambda: cmd_deploy(),
        "launch": lambda: cmd_launch(),
        "reload": lambda: cmd_reload(),
        "screenshot": lambda: cmd_screenshot(*args),
        "fetch_screenshot": lambda: cmd_fetch_screenshot(),
        "press": lambda: cmd_press(*args),
        "navigate": lambda: cmd_navigate(*args),
        "savestate": lambda: cmd_savestate(*args),
        "backup": lambda: cmd_backup(*args[0:1]) if args else cmd_backup(),
        "play": lambda: cmd_play(*args[0:1]) if args else cmd_play(),
        "clean": lambda: cmd_clean_screenshots(),
        "reset": lambda: cmd_reset(),
        "pause": lambda: cmd_pause(),
        "unpause": lambda: cmd_unpause(),
        "osd": lambda: cmd_osd(),
        "game_start": lambda: cmd_game_start(),
        "capture_gameplay": lambda: cmd_capture_gameplay(*args[:2]),
        "deploy_and_test": lambda: cmd_deploy_and_test(*args[:1]) if args else cmd_deploy_and_test(),
        "list_states": lambda: cmd_list_states(),
        "clean_old_roms": lambda: cmd_clean_old_roms(),
        "cheats": lambda: cmd_cheats(*args[:1]) if args else cmd_cheats(),
        "reservation_check": lambda: cmd_reservation_check(),
        "release_sweep_start": (
            lambda: cmd_release_sweep_start(*args[:1])
            if args
            else cmd_release_sweep_start()
        ),
        "release_checkpoint": lambda: cmd_release_checkpoint(*args[:3]),
        "release_sweep_finish": (
            lambda: cmd_release_sweep_finish(*args[:1])
            if args
            else cmd_release_sweep_finish()
        ),
    }

    if command in commands:
        try:
            if command_requires_reservation(command, args):
                require_mister_reservation()
            commands[command]()
        except ReservationError as e:
            print(f"RESERVATION BLOCKED: {e}", file=sys.stderr)
            sys.exit(2)
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(commands.keys())}")
        sys.exit(1)


if __name__ == "__main__":
    main()
