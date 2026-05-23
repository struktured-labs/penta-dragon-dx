# Bank-Switched CALL Pattern (Penta Dragon DX engine)

The game uses a consistent "bank-switched CALL" pattern for invoking
functions across ROM banks. This document captures the mechanism.

## Pattern

A static caller (e.g. one of the 9 boss arena routines) does:

```
CALL 0x063E    ; or some other "thunk" address in bank 0
```

The thunk at `0x063E` is just an unconditional `JP <target>`:

```
0x063E:  C3 CF 02     JP 0x02CF
```

The actual setup at `0x02CF` follows a 3-step pattern:

```
0x02CF:  EF              RST 0x28              ; bank-switch entry
0x02D0:  CD 0F 2E        CALL 0x2E0F           ; actual function
0x02D3:  C3 55 0D        JP 0x0D55             ; cleanup + RET
```

## Step-by-step

1. **CALL 0x063E** pushes return address, jumps to thunk
2. **JP 0x02CF** (thunk) jumps to bank-switched dispatcher
3. **RST 0x28** = `RST 28h` jumps to fixed address 0x0028
   - 0x0028 holds `C3 9A 09` = `JP 0x099A`
   - 0x099A is presumably the bank-switch helper (saves current bank,
     possibly loads a new bank from a stack-passed argument)
4. **CALL 0x2E0F** runs the actual function (after bank switch)
5. **JP 0x0D55** returns via cleanup:
   ```
   0x0D55:  F5             PUSH AF
   0x0D56:  3E 02          LD A, 2
   0x0D58:  CD 61 00       CALL 0x0061         ; MBC bank → 2
   0x0D5B:  F1             POP AF
   0x0D5C:  C9             RET                 ; return to original caller
   ```

## Why this pattern

The game has features in different ROM banks (audio in bank 3, level
data in bank 13, etc.). Functions in those banks can't be called
directly via a simple `CALL` because the calling bank may need to
remain mapped during the call OR may need to be restored after.

This pattern:
- Saves caller's bank context (via RST 0x28)
- Switches to the target bank
- Executes the function
- Restores caller's bank context via the 0x0D55 cleanup
- Returns to original caller via the cleanup's RET

## Where this is used

- All 9 boss arena routines call thunks `0x063E` (→ 0x2E0F) and
  `0x06A7` (→ 0x2E1E) early in their prologue.
- Other game subsystems likely use the same pattern for cross-bank
  calls. Worth searching for `CD <thunk_addr>` instances to map.

## Identified thunks (0x063E–0x067A region, bank 0)

```
0x063E: → 0x02CF  (thunks to 0x2E0F + cleanup)
0x0641: → 0x02DD  (thunks to 0x492B + cleanup)
0x0644: → 0x02E4  (thunks to 0x0515)
0x0647: → 0x02EB  (thunks to 0x1004)
0x064A: → 0x02F2  (thunks to 0x04A5)
0x064D: → 0x02F9  (thunks to 0x309B)
0x0650: → 0x0300
0x0653: → 0x0307
... etc through 0x065C ...
0x065F: → 0x09A2  (different target — direct, no RST 28h dispatch)
0x0662: → 0x09A8
0x0665: → 0x09B3
...
```

The thunks at 0x063E–0x065C use the RST 28h pattern.
The thunks at 0x065F+ jump directly to a different region (0x09xx) —
likely a different category of helper.

## Future investigation

- Decode 0x099A (RST 28h target) to confirm bank-switch behavior
- Decode 0x0061 (used in 0x0D55 cleanup) to confirm MBC bank store
- Cross-reference thunks to find all bank-switched function calls
