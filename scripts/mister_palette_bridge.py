#!/usr/bin/env python3
"""Experimental, loopback-only palette/restart controller for Rivalmage.

No ROM code changes. Supports the primary BG0..6 and OBJ0..7 tables of the
explicitly pinned r536 ROM and listed successors, including the experimental
combined star candidate; scene-specific overrides are not edited here.
"""
import argparse
import fcntl
import hashlib
import http.server
import json
import re
import secrets
import shlex
import struct
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = 'b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350'
ROW_GUARD_PIN = 'e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b'
# Issue #19: keep current gameplay fixes when starting a palette session.
SARA_ATOMIC_PIN = '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5'
TED_MENU_PIN = '4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903'
STAR_PIN = 'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5'
# #19: offline-checked primary tables; not a hardware Apply/Resume qualification.
RETURN_FADE_PIN = '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b'
# Experimental late-return source build: primary-row editing only, not readiness.
LATE_RETURN_PIN = '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'
# #19: October playtest repairs; primary-table support is not hardware approval.
PLAYTEST_PIN = '6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228'
PLAYTEST_LAYOUT_PIN = '53e25cf01602fe9a4b9546d61845e1a9d17a581f2b2ad104734d92c280de5327'
# #19: exact title-retry candidate; offline support, not hardware qualification.
TITLE_RETRY_PIN = '126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941'
TITLE_RETRY_LAYOUT_PIN = 'f2a14a38e0fec9f8c1c7372d4a5ef65ad7465a06bbd544bc2ed4f5b371a9a9b5'
# Exact late-return layout with ONLY primary rows/global checksum normalized.
STAGE1_LAYOUT_PIN = '3521f83aaf36fdf9a5f82fdefd603e7b289fa9a58fa46447c17d441209cf83c2'
SOURCE = ROOT / 'tmp/stream-tonight/Penta Dragon DX v3.01.gbc'
WORK = ROOT / 'tmp/mister-palette-session'
NAMES = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6',
         'EnemyProjectile', 'SaraDragon', 'SaraWitch', 'SaraProjectileAndCrow',
         'Hornets', 'OrcGround', 'Humanoid', 'Catfish']
OFFSETS = list(range(0x36800, 0x36838, 8)) + list(range(0x36840, 0x36880, 8))
LABELS = [
    ('Dungeon floor & default scenery', 'BG0 · Shared with void, structural transitions and some text.'),
    ('Health & restoration pickups', 'BG1 · Health 1 and Health 2; includes their neutral shadows.'),
    ('Extra life & rare/score pickups', 'BG2 · Extra Life, Wild Card, P item and Orb.'),
    ('Poison & slow cures', 'BG3 · Status-cure pickups; also used as the Stage 6 base-world palette.'),
    ('Shield, arrows & teleport', 'BG4 · Also the Stage 2 base-world palette. Separate title overrides are not edited.'),
    ('Rotating spike bodies & power pickups', 'BG5 · Rings, shafts, connectors and end caps—not protruding teeth. Shared with Spiral, Turbo, Flash, Rock and Dragon pickups; the experimental star build also uses this for the five-point star. Later scenes reuse the slot for lava.'),
    ('Walls & spike supports/shadows', 'BG6 · Also the Stage 4 base-world palette. Not the rotating teeth.'),
    ('Enemy shots & effects', 'OBJ0 · Primary projectile/effect palette; dragon-shot overrides are separate.'),
    ('Sara — dragon form', 'OBJ1 · Normal dragon form, not the bonus-stage jet override.'),
    ('Sara — witch form', 'OBJ2 · Normal witch form, not the bonus-stage jet override.'),
    ('Sara’s shots & crows', 'OBJ3 · Shared primary palette: editing it affects both.'),
    ('Hornets / insect family', 'OBJ4 · Primary insect palette; special actor overrides are separate.'),
    ('Orcs / ground-enemy family', 'OBJ5 · Primary ground-enemy palette.'),
    ('Humanoid enemy family', 'OBJ6 · Soldier/moth family; boss and special actor overrides are separate.'),
    ('Catfish / special-enemy base palette', 'OBJ7 · YAML base-row name; scene-specific routing and boss overrides may replace it.'),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(colors):
    if not isinstance(colors, list) or len(colors) != 4:
        raise ValueError('Exactly four #RRGGBB colors required')
    result = bytearray()
    for color in colors:
        if not isinstance(color, str) or len(color) != 7 or color[0] != '#':
            raise ValueError('Use #RRGGBB')
        value = int(color[1:], 16)
        r, g, b = (value >> 16) & 255, (value >> 8) & 255, value & 255
        result += struct.pack('<H', (r * 31 + 127) // 255 |
                              ((g * 31 + 127) // 255) << 5 |
                              ((b * 31 + 127) // 255) << 10)
    return bytes(result)


def decode(row):
    return ['#%02x%02x%02x' % tuple(((v >> s) & 31) * 255 // 31
            for s in (0, 5, 10)) for v in struct.unpack('<4H', row)]


def primary_layout_digest(rom):
    if len(rom) != 1048576:
        return None
    normalized = bytearray(rom)
    for offset in OFFSETS:
        normalized[offset:offset+8] = bytes(8)
    normalized[0x14E:0x150] = bytes(2)
    return sha(normalized)


def stage1_layout_supported(rom):
    return primary_layout_digest(rom) in (STAGE1_LAYOUT_PIN, PLAYTEST_LAYOUT_PIN,
                                        TITLE_RETRY_LAYOUT_PIN)


def labels_for_rom(rom):
    """Keep stable API keys, but describe this exact layout's projectile roles."""
    labels = list(LABELS)
    if primary_layout_digest(rom) in (PLAYTEST_LAYOUT_PIN, TITLE_RETRY_LAYOUT_PIN):
        labels[7] = ('Sara’s weapon shots & effects',
                     'OBJ0 · Player weapon primary palette; dragon-shot overrides are separate. Historical API key: EnemyProjectile.')
        labels[10] = ('Enemy bullets & crows',
                      'OBJ3 · Enemy bullet tile 0F now shares this primary row with crows and other actors using OBJ3. Historical API key: SaraProjectileAndCrow.')
    return labels


def stage1_owned_positions(rom, state):
    """#39 fixed primary slots for settled Stage1 on exact supported layouts.

    MiSTer B0CA: header8 + registers512 + WRAM32768 + VRAM16384 +
    OAM160 + HRAM128. Physical WRAM bank1 contains D880/DF4C.
    Never infer ownership from equal row bytes alone.
    """
    if not stage1_layout_supported(rom):
        return None
    wram, hram = 520, 49832
    if (state[wram+0x1880] != 2 or state[wram+0x1F4C] != 0
            or any(state[hram+address-0xFF80] != expected for address, expected in (
                (0xFFB7, 2), (0xFFBA, 0), (0xFFC1, 1), (0xFFBF, 0),
                (0xFFD0, 0), (0xFFE4, 0), (0xFFC0, 0)))):
        return None
    positions = [96+i*8 for i in range(7)] + [160+i*8 for i in range(8)]
    # Require the whole primary installation, not an intermediate fade/override.
    if any(state[pos:pos+8] != rom[offset:offset+8]
           for pos, offset in zip(positions, OFFSETS)):
        return None
    return positions


def dungeon_owned_positions(rom, state):
    """Return active slots per primary owner for qualified dungeon contexts."""
    stage1 = stage1_owned_positions(rom, state)
    if stage1 is not None:
        return [[pos] for pos in stage1]
    if not stage1_layout_supported(rom):
        return None
    wram, hram = 520, 49832
    if (state[wram+0x1880] != 3 or state[wram+0x1F4C] != 0
            or any(state[hram+address-0xFF80] != expected for address, expected in (
                (0xFFB7, 3), (0xFFBA, 1), (0xFFC1, 1), (0xFFBF, 0),
                (0xFFD0, 0), (0xFFE4, 0), (0xFFC0, 0)))):
        return None
    positions = [96+i*8 for i in range(7)] + [160+i*8 for i in range(8)]
    # Exact layout bank13:7BAC selects $6820 for Stage2 BG0. BG4 owns both
    # that scenery copy and its normal pickup slot; primary Dungeon is inactive.
    owners = [4] + list(range(1, 15))
    if any(state[pos:pos+8] != rom[OFFSETS[owner]:OFFSETS[owner]+8]
           for pos, owner in zip(positions, owners)):
        return None
    return [[pos for pos, owner in zip(positions, owners) if owner == index]
            for index in range(15)]


def validate_edit(rom, index, colors, *, allow_alias=False):
    """Reject ROM-only errors before saving a device checkpoint (#39)."""
    if type(index) is not int or not 0 <= index < len(NAMES):
        raise ValueError('Unknown primary palette')
    if len(rom) not in (524288, 1048576):
        raise ValueError('Unsupported ROM size')
    # #19: expanded secret-CHR descendants retain MBC5 and the primary rows.
    # Starting identity is authenticated by Bridge; subsequent palette edits
    # have distinct hashes but must retain the expansion header contract.
    if len(rom) == 1048576 and rom[0x147:0x149] != bytes((0x1B, 0x05)):
        raise ValueError('Unsupported expanded ROM header')
    offset = OFFSETS[index]
    old, new = rom[offset:offset + 8], encode(colors)
    if index >= 7 and new[:2] != old[:2]:
        raise ValueError('Keep transparent OBJ color 0 unchanged')
    if old == new:
        raise ValueError('No color change after Game Boy color quantization')
    # #39: equal bytes do not establish row ownership after sequential edits.
    # Multiple active copies of ONE unique primary row are legitimate, but
    # matching two different primary definitions would alter the wrong palette.
    peers = range(0, 7) if index < 7 else range(7, len(OFFSETS))
    aliases = [NAMES[i] for i in peers if i != index
               and rom[OFFSETS[i]:OFFSETS[i] + 8] == old]
    if aliases and not allow_alias:
        raise ValueError('Ambiguous active palette: shares colors with '
                         + ', '.join(aliases)
                         + '; use Undo to separate these rows before editing')
    return offset, old, new


def patch(rom, state, index, colors):
    # Local Gameboy core: 8-byte header, 64 x 8-byte register block, then RAM.
    if len(state) != 181040 or struct.unpack_from('<I', state, 4)[0] != 0xB0CA:
        raise ValueError('Unsupported MiSTer Gameboy savestate layout')
    owned = dungeon_owned_positions(rom, state)
    offset, old, new = validate_edit(rom, index, colors, allow_alias=owned is not None)
    changed_rom, changed_state = bytearray(rom), bytearray(state)
    changed_rom[offset:offset + 8] = new
    checksum = sum(changed_rom[:0x14e]) + sum(changed_rom[0x150:])
    changed_rom[0x14e:0x150] = struct.pack('>H', checksum & 65535)
    # Only matching active palette rows are converted. Never force a base
    # palette over a boss/story/fade override. BG registers 11..18, OBJ19..26.
    start = 96 if index < 7 else 160
    matches = []
    positions = owned[index] if owned is not None else range(start, start + 64, 8)
    for pos in positions:
        if state[pos:pos + 8] == old:
            changed_state[pos:pos + 8] = new
            matches.append(pos)
    if not matches:
        raise ValueError('This primary palette is not active here; choose another or move to gameplay')
    return bytes(changed_rom), bytes(changed_state), matches


class Bridge:
    def __init__(self, source=SOURCE):
        WORK.mkdir(parents=True, exist_ok=True)
        self.rom = Path(source).read_bytes()
        self.source_pin = sha(self.rom)
        if self.source_pin not in (PIN, ROW_GUARD_PIN, SARA_ATOMIC_PIN, TED_MENU_PIN, STAR_PIN, RETURN_FADE_PIN, LATE_RETURN_PIN, PLAYTEST_PIN, TITLE_RETRY_PIN):
            raise ValueError('Starting ROM does not match an exact supported pin')
        self.stem = 'Penta-Dragon-DX-' + self.source_pin[:12]
        self.history = []

    def ssh(self, command):
        return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o',
                               'ConnectTimeout=5', 'rivalmage', command],
                              check=True, capture_output=True, timeout=20).stdout

    def check(self):
        if self.ssh('hostname').strip() != b'rivalmage':
            raise ValueError('Wrong machine')
        if self.ssh('cat /tmp/CORENAME').strip() != b'GBC':
            raise ValueError('Rivalmage must be running the GBC core')
        # This checks the owned ROM file, not a claim that the core exposes
        # active-ROM identity. Do not manually change games during a session.
        remote = '/media/fat/games/GBC/' + self.stem + '.gbc'
        if self.ssh('sha256sum ' + shlex.quote(remote)).split()[0].decode() != sha(self.rom):
            raise ValueError('Remote ROM changed')

    def copy(self, source, target):
        subprocess.run(['scp', '-O', '-q', '-o', 'BatchMode=yes', '-o',
                        'ConnectTimeout=5', str(source), str(target)],
                       check=True, capture_output=True, timeout=20)

    def state_path(self, stem=None):
        return '/media/fat/savestates/GBC/' + (stem or self.stem) + '_4.ss'

    def checkpoint(self, directory):
        self.check()
        remote = self.state_path()
        before = None
        if self.ssh('test -f ' + shlex.quote(remote) + ' && echo yes || true').strip():
            self.copy('rivalmage:' + remote, directory / 'previous-slot4.ss')
            before = (directory / 'previous-slot4.ss').read_bytes()
        self.ssh('python3 /media/fat/linux/sileval_inject.py combo leftalt f4')
        # Require two stable, nonempty reads rather than assuming key delivery
        # means the file write has completed.
        previous = None
        for _ in range(12):
            time.sleep(.25)
            data = self.ssh('cat ' + shlex.quote(remote))
            if data and data == previous and data != before:
                (directory / 'checkpoint.ss').write_bytes(data)
                return data
            previous = data
        raise ValueError('Savestate did not stabilize; no reload performed')

    def load(self, stem):
        self.ssh('printf "%s\\n" ' + shlex.quote('load_core /media/fat/' + stem + '.mgl') + ' > /dev/MiSTer_cmd')
        time.sleep(3)
        if self.ssh('cat /tmp/CORENAME').strip() != b'GBC':
            raise ValueError('GBC core did not start')
        self.ssh('python3 /media/fat/linux/sileval_inject.py combo f4')

    def apply(self, index, colors):
        # A known layout may resolve an alias after checkpointing. patch still
        # rejects it before upload/reload if actual scene ownership is unknown.
        validate_edit(self.rom, index, colors, allow_alias=stage1_layout_supported(self.rom))
        directory = WORK / ('edit-' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
        directory.mkdir()
        state = self.checkpoint(directory)
        new_rom, new_state, matches = patch(self.rom, state, index, colors)
        stem = 'Penta-Palette-' + sha(new_rom)[:16] + '-' + secrets.token_hex(3)
        rom_path, state_path = directory / 'candidate.gbc', directory / 'resume.ss'
        rom_path.write_bytes(new_rom)
        state_path.write_bytes(new_state)
        mgl = directory / 'candidate.mgl'
        mgl.write_text('<mistergamedescription><rbf>_Console/Gameboy</rbf><setname>GBC</setname>'
                       f'<file delay="2" type="f" index="1" path="{stem}.gbc"/>'
                       '</mistergamedescription>\n')
        remote_rom = '/media/fat/games/GBC/' + stem + '.gbc'
        remote_mgl = '/media/fat/' + stem + '.mgl'
        # Every candidate gets a unique namespace, leaving release ROM/saves intact.
        self.copy(rom_path, 'rivalmage:' + remote_rom)
        self.copy(state_path, 'rivalmage:' + self.state_path(stem))
        self.copy(mgl, 'rivalmage:' + remote_mgl)
        # #44: the launcher chooses the ROM, so verify it before any reload too.
        for path, data in [(remote_rom, new_rom), (self.state_path(stem), new_state),
                           (remote_mgl, mgl.read_bytes())]:
            if self.ssh('sha256sum ' + shlex.quote(path)).split()[0].decode() != sha(data):
                raise ValueError('Upload hash mismatch; no reload performed')
        self.history.append((self.stem, self.rom))
        receipt = dict(old_rom_sha256=sha(self.rom), new_rom_sha256=sha(new_rom),
                       checkpoint_sha256=sha(state), resume_sha256=sha(new_state),
                       palette=NAMES[index], state_palette_offsets=matches,
                       palette_ownership=(f'settled-stage{state[49832+0x3A]+1}-fixed-slots'
                           if dungeon_owned_positions(self.rom, state) is not None
                           else 'unique-primary-row-byte-matching'),
                       status='uploaded; restore not yet confirmed')
        (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        self.stem, self.rom = stem, new_rom
        phase = 'load'
        try:
            self.load(stem)
            phase = 'confirmation-checkpoint'
            confirmation = directory / 'confirmation'
            confirmation.mkdir()
            observed = self.checkpoint(confirmation)
            phase = 'palette-readback'
            if any(observed[pos:pos+8] != new_state[pos:pos+8] for pos in matches):
                raise ValueError('Restored palette was replaced by a scene override; use Undo')
            receipt['status'] = 'palette readback passed; visual gameplay confirmation pending'
            receipt['readback_sha256'] = sha(observed)
            (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        except Exception as error:
            # #48: a terminal failure must not remain a pending receipt. Keep
            # history for explicit Undo, and preserve the original exception
            # even if storage also fails while recording the failure.
            receipt.update(status='restore failed; Undo available',
                           failure_phase=phase, error_type=type(error).__name__,
                           error=str(error))
            try:
                (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2))
            except OSError as receipt_error:
                error.add_note(f'Could not persist failure receipt: {receipt_error}')
            raise
        return 'Palette readback passed on MiSTer. Confirm picture/position; Undo returns to the prior checkpoint.'

    def undo(self):
        if not self.history:
            raise ValueError('No previous edit in this session')
        stem, rom = self.history[-1]
        self.load(stem)
        self.stem, self.rom = stem, rom
        self.history.pop()
        return 'Previous ROM and checkpoint restore requested.'


def serve(port, resume_edit=None, source=SOURCE):
    bridge, token = Bridge(source), secrets.token_urlsafe(24)
    lock = (WORK / 'controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if resume_edit is not None:
        directory = resume_edit.resolve()
        if not directory.is_relative_to(WORK.resolve()):
            raise ValueError('Resume directory must be in the session artifact directory')
        receipt = json.loads((directory / 'receipt.json').read_text())
        rom = (directory / 'candidate.gbc').read_bytes()
        match = re.search(r'path="(Penta-Palette-[a-f0-9-]+)\.gbc"', (directory / 'candidate.mgl').read_text())
        if (receipt['old_rom_sha256'] != bridge.source_pin or sha(rom) != receipt['new_rom_sha256']
                or not match or not receipt['status'].startswith('palette readback passed')):
            raise ValueError('Only a verified single-edit session can be resumed')
        bridge.history.append((bridge.stem, bridge.rom))
        bridge.stem, bridge.rom = match[1], rom
        bridge.check()  # Read-only: UI restart must not reload the game.
    class Handler(http.server.BaseHTTPRequestHandler):
        def send_json(self, data, status=200):
            payload = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == '/palettes':
                return self.send_json([dict(name=n, label=label, description=description,
                                           colors=decode(bridge.rom[o:o+8]))
                                       for n, o, (label, description) in zip(NAMES, OFFSETS, labels_for_rom(bridge.rom))])
            if self.path != '/':
                return self.send_json({'error': 'Not found'}, 404)
            page = '''<!doctype html><meta charset="utf-8"><title>Rivalmage Palette Lab</title>
<style>body{background:#161622;color:#eee;font:18px system-ui;max-width:900px;margin:35px auto}section{padding:12px;border-bottom:1px solid #555}input{width:70px;height:40px}button{padding:10px;margin:8px}#status{white-space:pre-wrap}</style>
<h1>Rivalmage Palette Lab</h1><p>Experimental • GBC • slot 4 reserved • primary palettes only.</p>
<p>Do not change games manually during this session. Apply saves here, reloads, then restores.
Scene overrides and BG7 are not supported. Changes stay in session ROMs, not the release YAML.</p>
<button id="undo">Undo &amp; Resume</button><p id="status">Ready to edit. Hardware visual confirmation required.</p><main></main>
<script>const token=TOKEN; async function action(body){document.querySelectorAll('button').forEach(b=>b.disabled=true);document.querySelector('#status').textContent='Saving / transferring / restoring…';try{let r=await fetch('/action',{method:'POST',headers:{'Content-Type':'application/json','X-Palette-Token':token},body:JSON.stringify(body)});let d=await r.json();document.querySelector('#status').textContent=d.message||d.error;await refresh()}catch(e){document.querySelector('#status').textContent=String(e)}finally{document.querySelectorAll('button').forEach(b=>b.disabled=false)}}
async function refresh(){let rows=await(await fetch('/palettes')).json();let main=document.querySelector('main');main.replaceChildren();rows.forEach((r,index)=>{let s=document.createElement('section');let label=document.createElement('div');label.textContent=r.label+' ('+r.name+')';s.append(label);let help=document.createElement('p');help.textContent=r.description;help.style.fontSize='14px';help.style.color='#bfc3d9';s.append(help);r.colors.forEach((c,i)=>{let el=document.createElement('input');el.type='color';el.value=c;el.disabled=index>=7&&i===0;el.setAttribute('aria-label',r.label+' color '+i);s.append(el)});let b=document.createElement('button');b.textContent='Apply & Resume';b.onclick=()=>action({action:'apply',index,colors:[...s.querySelectorAll('input')].map(e=>e.value)});s.append(b);main.append(s)})}document.querySelector('#undo').onclick=()=>action({action:'undo'});refresh();</script>'''.replace('TOKEN', json.dumps(token))
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(page.encode())

        def do_POST(self):
            if self.path != '/action' or self.headers.get('X-Palette-Token') != token:
                return self.send_json({'error': 'Forbidden'}, 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(length))
                if body.get('action') == 'apply':
                    message = bridge.apply(body['index'], body['colors'])
                elif body.get('action') == 'undo':
                    message = bridge.undo()
                else:
                    raise ValueError('Unknown action')
                self.send_json({'message': message})
            except Exception as exc:
                self.send_json({'error': str(exc)}, 400)
    # Single-threaded: hardware operations cannot overlap.
    print(f'Palette lab: http://127.0.0.1:{port}', flush=True)
    http.server.HTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8078)
    parser.add_argument('--resume-edit', type=Path, help='Preserve a verified single-edit session across a UI restart')
    parser.add_argument('--source', type=Path, default=SOURCE,
                        help='Exact supported base ROM already deployed under its hash-qualified stem')
    args = parser.parse_args()
    serve(args.port, args.resume_edit, args.source)
