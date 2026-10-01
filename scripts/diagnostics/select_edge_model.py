"""#34 executable input contract, not a ROM patch or emulator acceptance gate.

Keep FF93 as the latest raw sample. A separate pending Select bit carries a
rising edge across a slow game iteration. It is consumed atomically with the
native edge poll, never used as a replacement for held-button state. Multiple
presses between polls coalesce, as a one-bit edge interface cannot count them.
The eventual ROM implementation must prove RAM ownership, initialization,
interrupt exclusion and lifecycle flushing independently of this model.
"""
from dataclasses import dataclass

SELECT = 4


@dataclass
class SelectEdgeModel:
    raw: int = 0
    pending: int = 0

    def sample(self, buttons: int, *, enabled: bool = True) -> None:
        buttons &= 255
        if enabled:
            self.pending |= buttons & ~self.raw & SELECT
        else:
            self.pending = 0
        self.raw = buttons

    def consume(self, native_edges: int, mask: int = 255,
                *, enabled: bool = True) -> int:
        result = ((native_edges | self.pending) & mask) if enabled else 0
        self.pending = 0
        return result

    def boundary(self) -> None:
        # Discard queued input across menus/death/scene changes, retaining the
        # physical sample so a held button is not invented as a fresh press.
        self.pending = 0
