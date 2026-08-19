#!/usr/bin/env python3
"""Build a collision-free production/Ted integration experiment.

The verified cached Ted implementation currently occupies addresses shared by
the production Stage-1 pipeline in bank 13.  This diagnostic preserves the
production ROM byte-for-byte, copies the complete verified bank-13 image into
new MBC1 bank 16, and redirects Ted's private fixed-bank caller through two
small, asserted-zero bank-1 caves.  It deliberately remains a prototype until
the full release matrix proves the expanded image.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arena_semantic_key import (
    HELPER_BANK as ARENA_SEMANTIC_HELPER_BANK,
    HELPER_ENTRY as ARENA_SEMANTIC_HELPER_ENTRY,
    PENTA_SEAM_ENTRY,
    build_helper as build_arena_semantic_helper,
    build_penta_seam_helper,
)

from ted_native_sparse_pose_data import (
    NON_PUBLISHABLE_POSES,
    POSE_COUNT,
    POSE_CONNECTOR_DATA,
    POSE_DATA,
    POSE_DECISION_TREE,
    POSE_TRANSITIONS,
)


BANK_SIZE = 0x4000
SOURCE_BANK = 13
EXPANDED_BANK = 16
TED_CALL_SITE = 0x028A
TRAMPOLINE_FRONT = 0x6FE4
TRAMPOLINE_TAIL = 0x7C91
TED_ENTRY = 0x5CDA
EXPANDED_ENTRY = 0x4000
NATIVE_POSE_BANK = 17
NATIVE_POSE_ENTRY = 0x4000
NATIVE_POSE_CONTINUATION = 0x6535
LATER_SCROLL_BANK = 18
STAGE1_CODE_BANK = 19
STAGE1_PURE_MAP_BANK_IMMEDIATE = 0x10E3
STAGE1_ART_LOADER_BANK_IMMEDIATE = 0x6A23
LATER_SCROLL_ENTRY = 0x6B99
LATER_SCROLL_HELPER = 0x4000
LATER_PUBLISH_ENTRY = 0x4298
LATER_PUBLISH_RETURN = 0x4298
LATER_PUBLISH_DISPATCH_STUB = 0x0033
ROOM_BG_REPAIR_LATER = 0x6B94
ROOM_BG_REPAIR_CLEAR = 0x6B9D
LATER_PICKUP_SWEEP = 0x54B4
BG_SWEEP = 0x6CD0
TED_SPARSE_SETUP = 0x6530
TED_SPARSE_FINISH = 0x6D4E
TED_SPARSE_ENTRY = 0x539E
TED_SPARSE_TILE = 0xD70A
TED_SPARSE_COUNT = 0xD71F
TED_SPARSE_RECORDS = 0xD720
TED_ANCHOR_ROW = 0xD706
TED_ANCHOR_COL = 0xD707
TED_ATTR_LUT = 0xC600


class Emitter:
    def __init__(self, base: int) -> None:
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        assert name not in self.labels
        self.labels[name] = self.base + len(self.code)

    def jp(self, label: str, opcode: int = 0xC3) -> None:
        self.db(opcode, 0, 0)
        self.fixups.append((len(self.code) - 2, label))

    def call(self, label: str) -> None:
        self.jp(label, 0xCD)

    def finish(self) -> bytes:
        for operand, label in self.fixups:
            target = self.labels[label]
            self.code[operand] = target & 0xFF
            self.code[operand + 1] = target >> 8
        return bytes(self.code)


def build_later_scroll_edge_bank() -> bytes:
    """Preserve prioritized room repair and service vertical scroll edges.

    Production bank 13 maps here only for Stage 2-7. Pending room rows retain
    the exact established 8,7,6,4,5-first order; once that counter reaches
    zero, a tile-aligned SCY change selects the newly exposed top/bottom row.
    The helper then maps bank 13 and tail-enters its existing semantic sweep,
    so no boss, Stage-1, or ordinary-frame full-map work is added.
    """
    a = Emitter(LATER_SCROLL_HELPER)
    a.db(0xFA, 0x4E, 0xDF, 0xB7)           # pending row count
    a.jp("edge", 0xCA)

    # Byte-for-byte semantics of build_later_pickup_sweep_order(), with the
    # final bank-13 tail entered through the fixed mapper.
    a.db(0x3D, 0xEA, 0x4E, 0xDF)
    a.db(0xF0, 0xBA, 0x3D, 0xFE, 0x06)
    a.jp("normal_sweep", 0xD2)
    a.db(0xFA, 0x4E, 0xDF, 0xD6, 0x0A)
    a.jp("row_ready", 0xD2)
    a.db(0xC6, 0x12)
    a.label("row_ready")
    a.db(0xFE, 0x03)
    a.jp("store_row", 0xDA)
    a.db(0xFE, 0x05)
    a.jp("store_row", 0xD2)
    a.db(0xEE, 0x07)                       # seeds 3/4 -> 4/3
    a.label("store_row")
    a.db(0xEA, 0x04, 0xDF)
    a.jp("normal_sweep")

    a.label("edge")
    a.db(0xC5)                             # preserve caller BC
    a.db(0xF0, 0x42, 0xE6, 0xF8, 0x47)   # B = aligned current SCY
    a.db(0xF0, 0xA5, 0xB8)                # cached SCY CP current
    a.jp("edge_idle", 0xCA)
    a.db(0x78, 0xE0, 0xA5)                # cache current, preserve CP flags
    a.db(0x3E, 0x11)                       # downward seed -> visible row 0
    a.jp("edge_ready", 0xDA)              # cached < current
    a.db(0x3D)                             # upward/wrap seed -> row 17
    a.label("edge_ready")
    a.db(0xEA, 0x04, 0xDF, 0xC1)

    a.label("normal_sweep")
    # Push the bank-13 BG sweep as the mapper return address. JP avoids
    # returning into the now-unmapped expanded bank.
    a.db(0x3E, 0x0D, 0x21, BG_SWEEP & 0xFF, BG_SWEEP >> 8, 0xE5)
    a.db(0xC3, 0x61, 0x00)

    a.label("edge_idle")
    a.db(0xC1)
    a.db(0x3E, 0x0D, 0x21)
    idle_return_operand = len(a.code)
    a.db(0x00, 0x00, 0xE5, 0xC3, 0x61, 0x00)
    # The mapper must return directly to a bank-13 RET. The room repair's
    # fixed clear tail ends in one and is unreachable for later scenes here.
    a.code[idle_return_operand] = (ROOM_BG_REPAIR_CLEAR + 4) & 0xFF
    a.code[idle_return_operand + 1] = (ROOM_BG_REPAIR_CLEAR + 4) >> 8

    code = a.finish()
    bank = bytearray([0xFF]) * BANK_SIZE
    helper_off = LATER_SCROLL_HELPER - 0x4000
    bank[helper_off:helper_off + len(code)] = code
    entry_off = LATER_SCROLL_ENTRY - 0x4000
    bank[entry_off:entry_off + 3] = bytes([
        0xC3, LATER_SCROLL_HELPER & 0xFF, LATER_SCROLL_HELPER >> 8,
    ])

    # The shared bank-1 map publisher is still the authority for the title,
    # Stage 1, and every arena.  Only persistent Stage 2-7 scenes enter this
    # private dispatcher.  Their changed layouts use two-cell atomic groups:
    # the three-cell production form is nearly safe, but exact headed traces
    # prove an occasional final attribute drops out in vertically-scrolled
    # rooms.  Two cells fit the shortest measured HBlank with margin.
    p = Emitter(LATER_PUBLISH_ENTRY)
    p.db(
        # Reproduce stock $4295's selector toggle exactly.
        0xFA, 0x0B, 0xDC, 0x3C, 0xE6, 0x01,
        0xEA, 0x0B, 0xDC,
        # Stage scenes $03-$08 are the six later dungeons.
        0xFA, 0x80, 0xD8, 0xD6, 0x03, 0xFE, 0x06,
    )
    p.jp("later", 0xDA)                  # JP C

    # All other callers retain the established bank-1 copier and its exact
    # destination selected by the just-written DC0B value.
    p.db(0xFA, 0x0B, 0xDC, 0xB7, 0x26, 0x98)
    p.jp("native_map", 0xCA)
    p.db(0x26, 0x9C)
    p.label("native_map")
    p.db(
        0x3E, 0x01,
        0x01, 0xA7, 0x42, 0xC5,
        0xC3, 0x61, 0x00,
    )

    p.label("later")
    p.db(0xFA, 0x0B, 0xDC, 0xB7, 0x26, 0x98)
    p.jp("map_selected", 0xCA)
    p.db(0x26, 0x9C)
    p.label("map_selected")
    p.db(
        0x2E, 0x00,                       # HL = selected VRAM map
        0xF3,                             # freeze bank/source contracts
        0xF0, 0xFF,                       # caller IE
        0xEA, 0x5A, 0xDF,
        0xE6, 0x04, 0xE0, 0xFF,           # admit Timer only
        0x11, 0xA0, 0xC1,                 # packed 24x24 source
    )

    p.label("row")
    p.db(0x3E, 0x0C, 0xE0, 0xE0)
    p.label("group")
    # Precompute attrs forward, then materialize them in D/E before the STAT
    # wait. Tile 0 uses a later-dungeon-private HRAM mailbox; tile 1 remains
    # in B and tile 0 is restored into C. The already-advanced packed-source
    # pointer is parked in DF30/31 while D/E hold attr 0/1. This removes POPs
    # from the VRAM-critical interval.
    p.db(
        0x06, 0xC6,
        0x1A, 0x13, 0xE0, 0xA8, 0x4F, 0x0A, 0xF5,
        0x1A, 0x13, 0x4F, 0x0A, 0xF5,
        0x41, 0xF0, 0xA8, 0x4F,
        0x7A, 0xEA, 0x30, 0xDF,
        0x7B, 0xEA, 0x31, 0xDF,
        0xF1, 0x5F,                       # E = attr 1
        0xF1, 0x57,                       # D = attr 0
        0x3E, 0x01, 0xE0, 0x4F,           # preselect attribute bank
        0x23, 0x23,                       # destination group end
    )

    # Enter a fresh HBlank, publish matching tile/attribute pairs, and leave
    # VBK zero.  The critical interval is deliberately branch/call free.
    p.label("stat3")
    p.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    p.jp("stat3", 0xC2)
    p.label("stat0")
    p.db(0xF0, 0x41, 0xE6, 0x03)
    p.jp("stat0", 0xC2)
    p.db(
        0x2B, 0x73,                       # attr 1 at group end - 1
        0x2B, 0x72,                       # attr 0 at group start
        0xAF, 0xE0, 0x4F,
        0x71, 0x23, 0x70, 0x23,           # tile 0, tile 1; group end
        0xFA, 0x30, 0xDF, 0x57,
        0xFA, 0x31, 0xDF, 0x5F,           # restore packed source DE
        0xF0, 0xE0, 0x3D, 0xE0, 0xE0,
    )
    p.jp("group", 0xC2)

    # One register-safe Timer opportunity per completed row, matching the
    # production atomic publisher's interrupt contract.
    p.db(
        0xE5, 0x21, 0x30, 0xDF, 0x72, 0x23, 0x73,
        0xFB, 0x00, 0xF3,
        0x5E, 0x2B, 0x56, 0xE1,
        0x7D, 0xC6, 0x08, 0x6F, 0x30, 0x01, 0x24,
        0x7B, 0xFE, 0xE0,
    )
    p.jp("row", 0xC2)

    # Restore IE before mapping bank 1.  The mapper returns through a tiny
    # bank-1 RETI stub at the same logical address as this expanded entry,
    # reproducing the atomic publisher's A=$01/F=$C0/IME return contract.
    p.db(
        0xFA, 0x5A, 0xDF, 0xE0, 0xFF,
        0x3E, 0x01,
        0x01, LATER_PUBLISH_RETURN & 0xFF, LATER_PUBLISH_RETURN >> 8,
        0xC5,
        0xC3, 0x61, 0x00,
    )

    publish = p.finish()
    publish_off = LATER_PUBLISH_ENTRY - 0x4000
    assert publish_off + len(publish) < entry_off
    assert bank[publish_off:publish_off + len(publish)] == bytes(
        [0xFF]
    ) * len(publish)
    bank[publish_off:publish_off + len(publish)] = publish

    return bytes(bank)


def decode_poses() -> list[tuple[tuple[int, int, int], ...]]:
    poses = []
    cursor = 0
    while cursor < len(POSE_DATA):
        count = POSE_DATA[cursor]
        cursor += 1
        pose = []
        for _ in range(count):
            tile, row, column = POSE_DATA[cursor:cursor + 3]
            pose.append((tile, row, column))
            cursor += 3
        poses.append(tuple(pose))
    assert cursor == len(POSE_DATA) and len(poses) == POSE_COUNT
    connector_cursor = 0
    complete = []
    for pose in poses:
        count = POSE_CONNECTOR_DATA[connector_cursor]
        connector_cursor += 1
        connectors = []
        for _ in range(count):
            tile, row, column = POSE_CONNECTOR_DATA[
                connector_cursor:connector_cursor + 3
            ]
            connectors.append((tile, row, column))
            connector_cursor += 3
        complete.append(tuple(sorted((*pose, *connectors))))
    assert connector_cursor == len(POSE_CONNECTOR_DATA)
    return complete


def build_native_pose_bank() -> bytes:
    """Build an O(1)-depth classifier and exact measured sparse-pose renderer."""
    poses = decode_poses()
    a = Emitter(NATIVE_POSE_ENTRY)
    # Emit the tree with an explicit root walker to keep every label unique.
    def walk(node: int | tuple[int, dict[int, object]], label: str) -> None:
        if isinstance(node, int):
            return
        offset, branches = node
        a.label(label)
        address = 0xC1A0 + offset
        a.db(0xFA, address & 0xFF, address >> 8)
        child_labels = []
        for value, child in branches.items():
            child_label = f"pose_{child}" if isinstance(child, int) else f"tree_{len(a.labels)}_{value:02x}"
            child_labels.append((child, child_label))
            a.db(0xFE, value)
            a.jp(child_label, 0xCA)
        a.jp("pose_1")
        for child, child_label in child_labels:
            if not isinstance(child, int):
                walk(child, child_label)

    walk(POSE_DECISION_TREE, "entry")
    for index in range(POSE_COUNT):
        a.label(f"pose_{index}")
        if index in NON_PUBLISHABLE_POSES:
            # These keys identify incomplete source-plane states, not complete
            # poses. Stock can retain them for bounded multi-publication runs;
            # hold the last complete pose rather than publish its alternating
            # sparse-absent physical map.
            a.jp("finish")
        else:
            a.db(0x3E, index)
            a.jp("render")

    # D71F is zero after every canonical body rebuild, otherwise pose+1.
    # Most publications repeat the same native pose and now return without
    # touching a single cache cell. Real transitions use a precomputed delta.
    a.label("render")
    a.db(0x4F,                              # C = new pose index
         0xFA, TED_SPARSE_COUNT & 0xFF, TED_SPARSE_COUNT >> 8,
         0x47,                              # B = old token (0 or pose+1)
         0x79, 0x3C, 0xB8)
    a.jp("finish", 0xCA)
    # Resolve row pointer for the old token.
    a.db(0x78, 0x87, 0x5F, 0x16, 0x00,
         0x21, 0x00, 0x00)
    a.fixups.append((len(a.code) - 2, "transition_rows"))
    a.db(0x19, 0x2A, 0x66, 0x6F)           # HL = row pointer
    # Index a byte-sized command ID, then resolve it through the compact
    # command-pointer table. This remains O(1) while avoiding a 4.9 KiB
    # matrix of duplicate 16-bit pointers.
    a.db(0x79, 0x5F, 0x16, 0x00, 0x19, 0x7E, 0x87, 0x5F, 0x16, 0x00,
         # There are 136 deduplicated commands.  ADD A,A therefore carries
         # for IDs 128-135; retain that carry in D instead of wrapping those
         # late Ted transitions to the first eight pointer-table bytes.
         0xCB, 0x12,                       # RL D -> high byte of ID * 2
         0x21, 0x00, 0x00)
    a.fixups.append((len(a.code) - 2, "command_pointers"))
    a.db(0x19, 0x2A, 0x66, 0x6F,
         0x46, 0x23)                       # B = command count
    a.db(0x78, 0xFE, 0xFF)
    a.jp("invalidate", 0xCA)
    # Commit the new token only after a real command has been selected.
    a.db(0x79, 0x3C,
         0xEA, TED_SPARSE_COUNT & 0xFF, TED_SPARSE_COUNT >> 8,
         0x78, 0xB7)
    a.jp("finish", 0xCA)
    a.label("render_loop")
    a.db(0x2A,                              # A = desired tile
         0x56, 0x23, 0x5E, 0x23)           # D/E = relative row/column
    a.call("write_cell")
    a.db(0x05)
    a.jp("render_loop", 0xC2)
    a.jp("finish")

    a.label("invalidate")
    # An unmeasured pose jump can occur only after a mismatched/stale state.
    # Force the next publication to rebuild its canonical plane; never guess
    # at a transition and never publish a partially-restored tendril pose.
    # FFA9 is the cached full-plane anchor key. FFA8 is merely the body-loop
    # counter scratch; clearing it did not invalidate anything, so the next
    # baseline transition accumulated new tendrils on the stale cache.
    a.db(0xAF,
         0xEA, TED_SPARSE_COUNT & 0xFF, TED_SPARSE_COUNT >> 8,
         0xE0, 0xA9)
    a.label("finish")
    a.db(0xC9)

    a.label("write_cell")
    # Preserve the command cursor and loop count. A is the exact desired tile
    # (native sparse art or canonical numbered/checker restoration).
    a.db(0xE5, 0xC5, 0xF5)
    a.db(0xFA, TED_ANCHOR_COL & 0xFF, TED_ANCHOR_COL >> 8,
         0x83, 0xE6, 0x1F, 0x5F)
    a.db(0xFA, TED_ANCHOR_ROW & 0xFF, TED_ANCHOR_ROW >> 8,
         0x82, 0xE6, 0x1F, 0x57)
    # DE = D000 + row*32 + column.
    a.db(0x7A, 0xE6, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x83, 0x6F,
         0x7A, 0x0F, 0x0F, 0x0F, 0xE6, 0x03, 0xC6, 0xD0, 0x67,
         0x54, 0x5D)
    a.db(0xF1, 0x12,                       # desired tile -> cache
         0x6F, 0x26, TED_ATTR_LUT >> 8, 0x7E,
         0xF5, 0x7A, 0xC6, 0x08, 0x57, 0xF1, 0x12,
         0xC1, 0xE1, 0xC9)

    # Canonical body lookup used when a sparse cell disappears.
    spans = ((0, 5), (-2, 6), (-2, 6), (-2, 6), (-2, 6), (-2, 7),
             (-3, 7), (-4, 7), (-4, 7), (-4, 7), (-3, 7), (-2, 6),
             (0, 6), (1, 5))
    canonical: dict[tuple[int, int], int] = {}
    tile = 2
    for row, (left, right) in enumerate(spans):
        for column in range(left, right):
            canonical[(row, column)] = tile
            tile += 1
    assert tile == 0x77

    pose_maps = [
        {(row if row < 16 else row - 32,
          column if column < 16 else column - 32): tile
         for tile, row, column in pose}
        for pose in poses
    ]

    def transition(old: int | None, new: int) -> bytes:
        before = {} if old is None else pose_maps[old]
        after = pose_maps[new]
        commands = bytearray()
        for position in sorted(set(before) | set(after)):
            if before.get(position) == after.get(position):
                continue
            row, column = position
            desired = after.get(position)
            if desired is None:
                desired = canonical.get(
                    position,
                    0x77 + 2 * (row & 1) + (column & 1),
                )
            commands.extend((desired, row & 0x1F, column & 0x1F))
        assert len(commands) // 3 < 0xFF
        return bytes([len(commands) // 3]) + bytes(commands)

    known_edges = set(POSE_TRANSITIONS)
    # The stock source advances every frame while publications occur roughly
    # every 5-7 frames.  The authoritative 920-frame publisher trace includes
    # one legitimate skipped transition not present in the per-frame corpus.
    known_edges.add((1, 4))
    # Every reset/rebuild starts from the canonical baseline. Empty-pose
    # transitions are also safe from every measured pose.
    command_for: dict[tuple[int, int], bytes] = {}
    for new in range(POSE_COUNT):
        command_for[(0, new)] = transition(None, new)
    for old in range(POSE_COUNT):
        command_for[(old + 1, 1)] = transition(old, 1)
    for old, new in known_edges:
        command_for[(old + 1, new)] = transition(old, new)

    command_labels: dict[bytes, str] = {}
    command_ids: dict[bytes, int] = {}
    pointer_labels: list[list[int]] = []
    for old_token in range(POSE_COUNT + 1):
        row_labels = []
        for new in range(POSE_COUNT):
            if old_token == new + 1:
                command = b"\x00"
            else:
                command = command_for.get((old_token, new), b"\xFF")
            if command not in command_labels:
                command_labels[command] = f"command_{len(command_labels)}"
                command_ids[command] = len(command_ids)
            row_labels.append(command_ids[command])
        pointer_labels.append(row_labels)
    assert len(command_ids) <= 0x100
    # Keep the late-cycle regression explicit: these five legitimate native
    # transitions occupy the high half of the byte-sized command-ID space.
    # Their two-byte pointer offsets must therefore preserve ADD's carry.
    assert [
        pointer_labels[old + 1][new]
        for old, new in ((44, 45), (45, 46), (46, 47), (47, 48), (48, 1))
    ] == [128, 130, 132, 134, 135]

    a.label("transition_rows")
    for old_token in range(POSE_COUNT + 1):
        a.db(0, 0)
        a.fixups.append((len(a.code) - 2, f"transition_row_{old_token}"))
    for old_token, row_ids in enumerate(pointer_labels):
        a.label(f"transition_row_{old_token}")
        a.db(*row_ids)
    a.label("command_pointers")
    for command in command_ids:
        a.db(0, 0)
        a.fixups.append((len(a.code) - 2, command_labels[command]))
    for command, label in command_labels.items():
        a.label(label)
        a.db(*command)
    if os.environ.get("PENTA_TED_POSE_LABELS") == "1":
        for name, address in sorted(a.labels.items(), key=lambda item: item[1]):
            print(f"ted_pose_label {name}={address:04X}")
    payload = bytearray(a.finish())
    continuation_offset = NATIVE_POSE_CONTINUATION - 0x4000
    assert len(payload) < continuation_offset, (len(payload), continuation_offset)
    payload.extend(bytes([0xFF]) * (continuation_offset - len(payload)))
    # CALL $4000 returns here with bank 17 still selected. Push the bank-16
    # sparse finish address as the mapper's synthetic return, then let the
    # stock helper update both FF99 and the MBC register before RET lands.
    continuation = bytes([
        0xCD, NATIVE_POSE_ENTRY & 0xFF, NATIVE_POSE_ENTRY >> 8,
        0x21, TED_SPARSE_FINISH & 0xFF, TED_SPARSE_FINISH >> 8,
        0xE5,
        0x3E, EXPANDED_BANK,
        0xC3, 0x61, 0x00,
    ])
    payload.extend(continuation)
    assert len(payload) <= BANK_SIZE, len(payload)
    return bytes(payload) + bytes([0xFF]) * (BANK_SIZE - len(payload))


def bank_offset(bank: int, address: int) -> int:
    assert 0x4000 <= address < 0x8000
    return bank * BANK_SIZE + address - 0x4000


def header_checksum(rom: bytearray) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


def combine(
    production_path: Path,
    verified_ted_path: Path,
    output: Path,
    *,
    native_pose_table: bool = False,
    native_layout_rom: Path | None = None,
    shalamar_native_exact_class: int | None = None,
) -> None:
    production = bytearray(production_path.read_bytes())
    ted = verified_ted_path.read_bytes()
    assert len(production) == len(ted) == 16 * BANK_SIZE
    assert production[0x0147] == ted[0x0147] == 0x03, "expected MBC1+RAM+battery"
    assert production[0x0148] == ted[0x0148] == 0x03, "expected 256 KiB inputs"

    # Add 16 banks because the ROM-size header encodes powers of two.  Only
    # bank 16 is populated; the remaining new banks stay $FF like blank ROM.
    production.extend(bytes([0xFF]) * (16 * BANK_SIZE))
    source = ted[SOURCE_BANK * BANK_SIZE:(SOURCE_BANK + 1) * BANK_SIZE]
    destination = EXPANDED_BANK * BANK_SIZE
    production[destination:destination + BANK_SIZE] = source
    if native_pose_table:
        entry_offset = destination + TED_SPARSE_ENTRY - 0x4000
        assert production[entry_offset:entry_offset + 3] == bytes.fromhex("C5 D5 E5")
        # The bank-17 delta publisher owns pose state directly. Bypass the
        # old restore-list path but retain its exact caller-save ABI.
        entry = bytes([
            0xC5, 0xD5, 0xE5,
            0xC3, TED_SPARSE_SETUP & 0xFF, TED_SPARSE_SETUP >> 8,
        ])
        production[entry_offset:entry_offset + len(entry)] = entry
        setup_offset = destination + TED_SPARSE_SETUP - 0x4000
        # Bank 17 owns the complete native pose publication, so replace the
        # whole ten-byte setup slot and keep the five-byte mapper call followed
        # by neutral padding.  The payload builder has two exact, intentional
        # source forms here: the bounded native sparse prelude, and the
        # canonical-limb build's already-retired tail jump plus zero padding.
        # Accept only those byte-locked forms before replacing either one.
        expected_native = bytes.fromhex("21 A0 C1 06 18 0E 18 C3 3C 62")
        expected_retired = bytes.fromhex("C3 3C 62 00 00 00 00 00 00 00")
        setup_source = bytes(
            production[setup_offset:setup_offset + len(expected_native)]
        )
        assert setup_source in (expected_native, expected_retired), (
            f"native-pose setup source changed: {setup_source.hex(' ')}"
        )
        # The bank-16 sparse entry has already restored the prior overlay.
        # The stock mapper returns at the same address in newly-selected bank
        # 17, whose aligned continuation calls its private renderer.
        setup = bytes([
            0x3E, NATIVE_POSE_BANK,
            0xCD, 0x61, 0x00,
        ])
        assert len(setup) == 5
        production[setup_offset:setup_offset + len(expected_native)] = (
            setup + bytes(len(expected_native) - len(setup))
        )
        pose_destination = NATIVE_POSE_BANK * BANK_SIZE
        production[pose_destination:pose_destination + BANK_SIZE] = (
            build_native_pose_bank()
        )

    # Every non-Stage-1 scene now owns a complete post-copy attribute
    # publisher and enters the $6B9D clear tail directly.  Keep the old
    # later-row body byte-exact but unreachable: the expanded-bank edge route
    # caused the measured systemic Stage 2-7 slowdown and raced Stage 4's
    # completed plane with stale data.
    scene_branch = bank_offset(SOURCE_BANK, ROOM_BG_REPAIR_LATER - 4)
    assert production[scene_branch:scene_branch + 4] == bytes.fromhex(
        "C3 9D 6B 00"
    )
    later_route = bank_offset(SOURCE_BANK, ROOM_BG_REPAIR_LATER)
    assert production[later_route:later_route + 9] == bytes.fromhex(
        "FA 4E DF B7 C8 3D C3 B4 54"
    )
    assert production[
        bank_offset(SOURCE_BANK, ROOM_BG_REPAIR_CLEAR):
        bank_offset(SOURCE_BANK, ROOM_BG_REPAIR_CLEAR) + 5
    ] == bytes.fromhex("AF EA 4E DF C9")
    edge_destination = LATER_SCROLL_BANK * BANK_SIZE
    assert production[
        edge_destination:edge_destination + BANK_SIZE
    ] == bytes([0xFF]) * BANK_SIZE

    if native_layout_rom is not None:
        # Bank 14 is native layout data as well as the historical home of the
        # Stage-1 hazard publisher. Troop proves that one alleged zero cave is
        # live *zero-valued data*: the stock map expander reads $6C88 through
        # bank 14, so injected row-compiler opcodes become bogus metatile IDs.
        #
        # Preserve the native mapper and its bank-stack behavior. Move the
        # complete patched Stage-1 bank image to expanded bank 19, restore
        # bank 14 byte-for-byte from stock, and retarget only the two proven
        # Stage-1 mapping sites. The bank-13 art-loader site also exists in
        # the byte-exact bank-16 Ted clone, so patch that dormant twin to keep
        # both copies internally consistent.
        native = native_layout_rom.read_bytes()
        assert len(native) == 16 * BANK_SIZE, "expected 256 KiB native ROM"
        native_bank = native[14 * BANK_SIZE:15 * BANK_SIZE]
        stage1_source = 14 * BANK_SIZE
        stage1_bank = bytes(production[
            stage1_source:stage1_source + BANK_SIZE
        ])
        stage1_destination = STAGE1_CODE_BANK * BANK_SIZE
        assert production[
            stage1_destination:stage1_destination + BANK_SIZE
        ] == bytes([0xFF]) * BANK_SIZE
        production[
            stage1_destination:stage1_destination + BANK_SIZE
        ] = stage1_bank
        production[stage1_source:stage1_source + BANK_SIZE] = native_bank

        mapping_sites = (
            STAGE1_PURE_MAP_BANK_IMMEDIATE,
            bank_offset(SOURCE_BANK, STAGE1_ART_LOADER_BANK_IMMEDIATE),
            bank_offset(EXPANDED_BANK, STAGE1_ART_LOADER_BANK_IMMEDIATE),
        )
        for site in mapping_sites:
            assert production[site] == 0x0E, (
                f"Stage-1 bank immediate changed at ROM ${site:06X}: "
                f"${production[site]:02X}"
            )
            production[site] = STAGE1_CODE_BANK

        # Receipt-lock the exact native mapper and the first known collision
        # that made Troop's source pointer jump from A400 to A798.
        assert production[0x30D8:0x30DD] == bytes.fromhex("3E 0E CD 61 00")
        collision = bank_offset(14, 0x6C88)
        assert native[collision] == 0x00
        assert stage1_bank[0x2C88] != native[collision]
        assert production[collision] == native[collision]
        assert production[
            stage1_source:stage1_source + BANK_SIZE
        ] == native_bank

    # The shared animated-arena cache executes from WRAM and briefly maps this
    # dedicated expansion bank to compute its two seven-cell sums. Never place
    # executable bytes back in bank 14: its apparent zero caves are native
    # boss/level-layout data.
    helper = build_arena_semantic_helper(
        shalamar_native_exact_class=shalamar_native_exact_class,
    )
    helper_destination = bank_offset(
        ARENA_SEMANTIC_HELPER_BANK, ARENA_SEMANTIC_HELPER_ENTRY
    )
    helper_bank_start = ARENA_SEMANTIC_HELPER_BANK * BANK_SIZE
    assert production[
        helper_bank_start:helper_bank_start + BANK_SIZE
    ] == bytes([0xFF]) * BANK_SIZE
    production[
        helper_destination:helper_destination + len(helper)
    ] = helper
    penta_seam_helper = build_penta_seam_helper()
    penta_seam_destination = bank_offset(
        ARENA_SEMANTIC_HELPER_BANK, PENTA_SEAM_ENTRY
    )
    assert production[
        penta_seam_destination:
        penta_seam_destination + len(penta_seam_helper)
    ] == bytes([0xFF]) * len(penta_seam_helper)
    production[
        penta_seam_destination:
        penta_seam_destination + len(penta_seam_helper)
    ] = penta_seam_helper

    # The shared map entry remains the native fixed selector.  The retired
    # bank-18 dispatcher was introduced before the complete post-copy
    # publishers existed; deterministic all-stage receipts show it costs
    # roughly 4-66% depending on the stage and is no longer required.
    assert production[
        LATER_PUBLISH_DISPATCH_STUB:LATER_PUBLISH_DISPATCH_STUB + 5
    ] == bytes.fromhex("7F CD 7B FE FF")
    assert production[0x4295:0x42A0] == bytes.fromhex(
        "FA 0B DC 3C E6 01 EA 0B DC 28 05"
    )
    assert production[0x42A0:0x42A7] == bytes.fromhex(
        "26 9C C3 A7 42 26 98"
    )
    # Ted's sole fixed-bank publication caller originally CALLs the shared
    # stock copier.  Route only that call into the private bank-1 trampoline.
    assert production[TED_CALL_SITE:TED_CALL_SITE + 3] == bytes.fromhex("CD 95 42")
    production[TED_CALL_SITE:TED_CALL_SITE + 3] = bytes([
        0xCD, TRAMPOLINE_FRONT & 0xFF, TRAMPOLINE_FRONT >> 8,
    ])

    # Stage loading also traverses $028A before Ted exists. Gate on Ted's exact
    # scene rather than borrowing FFA9, which is live production scheduler
    # state before the cached runtime has installed its private latch.
    front = bytes([
        0xFA, 0x80, 0xD8,
        0xFE, 0x10,
        0xC2, 0x95, 0x42,
        0xC3, TRAMPOLINE_TAIL & 0xFF, TRAMPOLINE_TAIL >> 8,
    ])
    # PUSH target + JP mapper makes the mapper's RET land directly in the new
    # bank. A tiny bank-local entry restores the fixed continuation's BC/DE
    # ABI before tail-entering the byte-identical verified payload.
    tail = bytes([
        0x3E, EXPANDED_BANK,
        0x21, EXPANDED_ENTRY & 0xFF, EXPANDED_ENTRY >> 8,
        0xE5,
        0xC3, 0x61, 0x00,
    ])
    expanded_entry = bytes([
        0xF3,
        0x01, 0x08, 0x00,
        0x11, 0xE0, 0xC3,
        0xC3, TED_ENTRY & 0xFF, TED_ENTRY >> 8,
    ])
    production[destination:destination + len(expanded_entry)] = expanded_entry
    front_off = bank_offset(1, TRAMPOLINE_FRONT)
    tail_off = bank_offset(1, TRAMPOLINE_TAIL)
    assert production[front_off:front_off + len(front)] == bytes(len(front))
    assert production[tail_off:tail_off + len(tail)] == bytes(len(tail))
    production[front_off:front_off + len(front)] = front
    production[tail_off:tail_off + len(tail)] = tail

    # A 512 KiB MBC1 image makes the game's RAM-bank writes participate in
    # switchable-ROM selection, changing ordinary Stage-1 banks. MBC5 retains
    # the same RAM-enable, low-ROM-bank, and RAM-bank write ranges used here,
    # but keeps ROM and RAM selection independent. SameBoy/mGBA and physical
    # flash cartridges support this standard mapper.
    production[0x0147] = 0x1B              # MBC5 + RAM + battery
    production[0x0148] = 0x04              # 512 KiB
    production[0x014D] = header_checksum(production)
    checksum = global_checksum(production)
    production[0x014E] = checksum >> 8
    production[0x014F] = checksum & 0xFF

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(production)
    suffix = ", bank 17 <- exact native sparse poses" if native_pose_table else ""
    if native_layout_rom is not None:
        suffix += ", bank 14 <- native layout, bank 19 <- Stage-1 code"
    print(
        f"wrote {output} ({len(production)} bytes), "
        f"bank 16 <- verified Ted bank 13{suffix}, "
        f"bank {ARENA_SEMANTIC_HELPER_BANK} <- arena semantic key helper"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("production", type=Path)
    parser.add_argument("verified_ted", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--native-pose-table", action="store_true")
    parser.add_argument("--native-layout-rom", type=Path)
    parser.add_argument(
        "--shalamar-native-exact-class",
        type=lambda value: int(value, 0),
        choices=range(16),
        help="retain native Shalamar work for one exact raw-key class",
    )
    args = parser.parse_args()
    combine(
        args.production, args.verified_ted, args.output,
        native_pose_table=args.native_pose_table,
        native_layout_rom=args.native_layout_rom,
        shalamar_native_exact_class=args.shalamar_native_exact_class,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
