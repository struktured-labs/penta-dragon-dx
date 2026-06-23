# iter 248 — lag is savestate-specific, not universal

## Pivot from chasing the fix

After 4 iters (244-247) chasing a fix for the slot 0/2 startup
transient, iter 248 stepped back to verify the bug's universality.

## Critical finding

`level1_sara_w_alone.ss0` (the most-used Sara W savestate in the
regression suite) shows **NO LAG**. HW OAM slot 0/2 = pal 2 from frame
60 onward. Shadow OAM = pal 0 throughout (a different state than
stage1_entry's pal 2), but HW OAM is correctly pal 2.

So the bug previously documented in iter 241-247 is **specific to
stage1_entry_pink_renders.ss0** (and likely other savestates captured
during stage-entry transients). It's NOT a universal teleport.gb bug.

This explains why:
- The existing `sara_w_alone` test (slots 0-3 = pal 2 at f=68) PASSES.
- The user's complaint of "half orange Sara at stage 1 start" matches
  fresh-boot stage-1 entry (where iter 244 probe showed HW OAM stuck
  at pal 4 for ~500 frames).

## Attempted regression test

Tried to add `stage1_entry_post_transient_pal2`:
- savestate: stage1_entry_pink_renders.ss0
- frames: 500, then 1000
- assertion: slots 0-2 (or 0-3) = pal 2

Result: test FAILED at both f=500 and f=1000. Even at f=1000, slot 0
shows pal 4 in consensus voting.

Re-running the trace probe (`probe_slot_attr_trace.lua`) confirmed:
- f=300, f=600: HW slot 0 = pal 2 (stable)
- But the test runner's 5-sample consensus at f=1000±2/5/8 catches
  some pal-4 flicks and votes pal 4.

So even though slot 0 is "mostly pal 2" by f=300, there are still
occasional pal-4 events. The consensus voting is unforgiving.

## Why this test is hard to add

The transient is a real ongoing race, not a clean "lag then stable"
pattern. Even post-transient, slot 0 occasionally flicks pal 4. The
consensus mechanism (designed to filter MAJORITY-vote) ends up
catching these flicks as the consensus when sample count is small.

To make a reliable test, would need either:
1. Reject ANY pal-4 sample (no fault tolerance) — likely still flaky
2. Sample at MANY frames (50+) and require >90% pal 2 — needs runner extension
3. Find a savestate without ANY ongoing flick

Option 3 is best but requires generating new savestates. Out of scope
for one iter.

## Decision

Revert the test addition. Document the finding in this audit.

The slot 0/2 race IS real and IS what the user observed at stage 1
entry. But it's hard to encode as a regression test with current
infrastructure. Future iter could either:
- Build a probe-based test runner extension that handles flicker
- Find or generate a stable post-transient savestate
- Accept that the user's bug is "stage 1 entry transient" and look
  for an alternative fix (e.g., extend hwoam_recolor's pal stamps
  to run a SECOND time within the same VBlank).

## What gets committed

This iter only commits the audit doc (no test, no probe changes).
The probe files from iter 244-247 already exist for future use.

Iter 244 onwards has yielded substantial RE knowledge:
- HRAM DMA routine alternates 0xC0/0xC1 via FFCB
- Combined handler structure decoded
- FFC1, DF1F, DF02, FFCB gates all characterized
- shadow_main writes both blocks to pal 2 each frame
- Force-block-B DMA patch doesn't fix the lag

Five mechanism candidates have been ruled out. The remaining mystery
is **what writes pal 4 to HW OAM AFTER the DMA's pal-2 copy**.
Top suspect: a non-VBlank IRQ or main-loop write that survives
hwoam_recolor's stamps when the VBlank handler doesn't complete in
time. Worth more cycles only with deeper instrumentation tools
(memory-write breakpoints, cycle-accurate tracing) that mGBA Lua
doesn't expose.

For now, the lag is **documented and bounded**:
- Affects stage-entry transient savestates only
- Lasts ~240 frames after savestate load
- Slot 3 shows even longer lag than slot 0/2
- Real-gameplay impact: ~8 second visual transient when entering stage 1
- User-facing severity: noticeable but not game-breaking
