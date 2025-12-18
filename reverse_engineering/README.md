# Penta Dragon DX - Reverse Engineering

## Current Status: Phase 1, Day 1

**Goal**: Find safe CGB palette injection point without crashing menu.

## What We Know

### The Problem
- Boot-time palette loading works BUT game overwrites palettes → beige/tan sprites
- VBlank hooks crash the menu initialization
- Input handler replacement crashes the menu
- Need to find a **post-menu, pre-gameplay** injection point

### Critical Findings

#### Functions That Crash Menu (DO NOT HOOK)
1. **0x0190**: Main initialization - direct crash
2. **0x06D6**: VBlank handler - crashes with any modification
3. **0x0824**: Input handler - crashes when replaced
4. **0x0150-0x0A0F**: Entire initialization sequence is unsafe

#### Promising Candidates (TO INVESTIGATE)
1. **0x3B69**: Level load function - called from gameplay, NOT from init
2. **0x40A0**: VRAM clear - called 2x during init, others during gameplay
3. **0x495D**: Called 9 times - most frequent function, needs investigation

### Call Graph Statistics
- **63 CALL instructions** traced in init sequence
- **4 JP instructions** (control flow branches)
- **0x495D**: Most called (9x) - likely utility function
- **0x40F1, 0x40A0**: Called multiple times - initialization helpers

## Project Structure

```
reverse_engineering/
├── analysis/
│   ├── initial_map.txt       # Memory map of critical addresses
│   ├── call_graph.txt         # Complete CALL/JP trace
│   └── trace_calls.py         # Call tracing script
├── disassembly/               # (To be populated)
├── notes/
│   └── PROJECT_PLAN.md        # 28-day project timeline
└── maps/                      # (To be populated)
```

## Next Steps (Days 2-3)

### Immediate Tasks
1. **Disassemble 0x3B69** - Verify it's gameplay-only
   - Check all callers
   - Verify not called during menu init
   - Test with one-time hook

2. **Trace 0x495D** - Most called function
   - Determine purpose (utility? critical?)
   - See if safe to hook or call

3. **Map WRAM usage** - Find safe flag location
   - Current candidate: C0A0
   - Verify not used by game
   - Test persistence

### Week 1 Goals
- [ ] Complete initialization call graph (ALL functions)
- [ ] Identify menu vs gameplay functions
- [ ] Test 0x3B69 hook with one-time loader
- [ ] If 0x3B69 fails, find alternative

## Testing Strategy

### Option 4 Test (Level Load Hook)
```
1. Hook 0x3B69 with one-time loader
2. Loader checks WRAM flag C0A0
3. If flag=0: Load palettes, set flag=1
4. If flag=1: Skip palette load
5. Always call original 40A0 function
```

**Expected Result:**
- Menu: Normal (no palette load, no crash)
- Level 1: Palettes load on first 0x3B69 call
- Level 2+: Flag already set, no reload

## Tools & Resources

### Analysis Tools
- **trace_calls.py**: Call graph analysis
- **Python**: ROM inspection and pattern matching
- **mGBA**: Testing and debugging

### Documentation
- PROJECT_PLAN.md: 28-day timeline
- initial_map.txt: Memory addresses
- call_graph.txt: CALL/JP targets

## Success Metrics

**Week 1:**
- ✅ Understand initialization sequence
- ✅ Identify safe post-menu function
- ⏳ Test one-time hook successfully

**Week 2:**
- Map complete menu flow
- Verify injection point
- Stable palette loading

**Week 3-4:**
- Production implementation
- Edge case testing
- Final documentation

## Contact
This is a 2-4 week deep dive. Progress will be tracked daily.

Last Updated: 2025-12-02
Phase: 1 (Initialization Analysis)
Day: 1
