# Penta Dragon DX - Deep Reverse Engineering Project

## Objective
Find safe injection point for CGB palette loading without crashing menu initialization.

## Timeline
- **Week 1-2**: Complete disassembly and initialization sequence mapping
- **Week 3**: Trace menu flow and identify safe post-menu point
- **Week 4**: Create and test injection solution

## Phase 1: Initialization Sequence Analysis (Days 1-7)

### Day 1-2: Boot Sequence Disassembly
- [x] Map boot entry at 0x0100-0x0150
- [ ] Trace execution from 0x0150 onwards
- [ ] Identify all CALL and JP targets in first 256 bytes
- [ ] Document register states at key points

### Day 3-4: Palette Initialization Functions
- [ ] Disassemble 0x5021 (palette init function)
- [ ] Disassemble 0xB8DE (palette function)
- [ ] Disassemble 0x0A0F (init function)
- [ ] Map all BGP/OBP0/OBP1 writes (FF47/FF48/FF49)
- [ ] Identify dependencies and call chains

### Day 5-6: Menu Initialization
- [ ] Trace menu setup from 0x0190 onwards
- [ ] Map all functions called during menu
- [ ] Identify VBlank behavior during menu
- [ ] Document timing-sensitive operations

### Day 7: Week 1 Review
- [ ] Complete initialization call graph
- [ ] Identify critical vs non-critical functions
- [ ] Mark known crash points with reasons

## Phase 2: Menu Flow Tracing (Days 8-14)

### Day 8-9: Menu State Machine
- [ ] Identify menu state variables (WRAM locations)
- [ ] Map state transitions
- [ ] Find "menu active" vs "gameplay active" flag

### Day 10-11: Input Handling
- [ ] Trace input handler at 0x0824
- [ ] Map menu input vs gameplay input paths
- [ ] Identify menu exit condition

### Day 12-13: Gameplay Transition
- [ ] Find exact point where menu ends
- [ ] Trace level load function at 0x3B69
- [ ] Verify it only runs post-menu

### Day 14: Week 2 Review
- [ ] Complete menu flow diagram
- [ ] Identify post-menu safe point
- [ ] Test hypothesis with debug ROM

## Phase 3: Safe Injection Point (Days 15-21)

### Day 15-16: Candidate Testing
- [ ] Test level load hook at 0x3B69
- [ ] Test other gameplay-only functions
- [ ] Verify no menu calls

### Day 17-18: Injection Design
- [ ] Design one-time loader with WRAM flag
- [ ] Ensure bank switching safety
- [ ] Minimize code footprint

### Day 19-20: Implementation
- [ ] Create injection ROM
- [ ] Test with menu
- [ ] Test with gameplay

### Day 21: Week 3 Review
- [ ] Verify stable injection
- [ ] Document solution
- [ ] Prepare for final testing

## Phase 4: Final Implementation (Days 22-28)

### Day 22-23: Integration
- [ ] Integrate with palette system
- [ ] Test all 64 colors
- [ ] Verify no crashes

### Day 24-25: Edge Cases
- [ ] Test save/load states
- [ ] Test multiple level transitions
- [ ] Test long gameplay sessions

### Day 26-27: Polish
- [ ] Optimize code size
- [ ] Add safety checks
- [ ] Document injection point

### Day 28: Project Complete
- [ ] Final ROM testing
- [ ] Documentation
- [ ] Success report

## Known Constraints

### Crash Points (DO NOT HOOK)
- **0x0150-0x0A0F**: Initialization sequence - menu crashes
- **0x06D6**: VBlank handler - crashes menu with any modification
- **0x0824**: Input handler - crashes when replaced

### Safe Areas (TO EXPLORE)
- **0x3B69**: Level load function - called post-menu
- **0x3CAF, 0x3D82, 0x409A**: Other post-init functions
- **Post-menu VBlank**: After menu fully initialized

### Technical Requirements
- One-time execution using WRAM flag (C0A0 or similar)
- Bank switching: Bank 13 for palette data
- Minimal code footprint (<100 bytes total)
- No interference with game timing

## Success Criteria
1. ✅ Menu loads without crash
2. ✅ Palette loads on first gameplay frame
3. ✅ Colors persist throughout gameplay
4. ✅ No crashes during normal play
5. ✅ Save/load states work correctly

## Tools
- **Disassembler**: mgbdis or manual analysis
- **Debugger**: BGB debugger (if needed)
- **Emulator**: mGBA for testing
- **Analysis**: Python scripts for pattern matching

## Current Status
- **Phase**: 1 - Initialization Analysis
- **Day**: 1
- **Next Action**: Begin boot sequence disassembly
