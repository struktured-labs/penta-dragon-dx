// Penta Dragon DX Remake — Sound Effects
//
// Register values extracted from the original Penta Dragon (J) ROM.
// The original game's sound engine lives at bank 3 (0xC000-0xFFFF in ROM file):
//   - SFX trigger: RST 38 (opcode 0xFF) with SFX ID in A → writes to [D887]
//   - SFX data: pointer table at 0x4748, data streams of (count, NR10-NR14) tuples
//   - Music uses all 4 channels; SFX temporarily takes Ch1 (and sometimes Ch4)
//
// Key SFX IDs from original:
//   0x26 = Sara W shoot       0x27 = Sara D shoot variant
//   0x0E = Player damage      0x1E = Enemy death (noise)
//   0x1A = Explosion (tone+noise)  0x04 = Menu select
//   0x09 = Menu cursor        0x25 = Life lost / HP change
//
// Channel allocation (matching original):
//   Channel 1 (square + sweep): shoot, player_hit (SFX share with music)
//   Channel 2 (square):         pickup arpeggio (our addition, not in original)
//   Channel 4 (noise):          enemy_hit / enemy_death
//   Channel 3 (wave):           reserved for future music

#include "sound.h"
#include <gb/gb.h>
#include <gb/hardware.h>

// --- Note frequency table (GB format: 2048 - 131072/freq) ---
// Subset of useful notes for SFX. Values are 11-bit GB frequency codes.
#define NOTE_C4   1046U
#define NOTE_D4   1102U
#define NOTE_E4   1155U
#define NOTE_F4   1205U
#define NOTE_G4   1253U
#define NOTE_A4   1297U
#define NOTE_B4   1339U
#define NOTE_C5   1379U
#define NOTE_D5   1417U
#define NOTE_E5   1452U
#define NOTE_F5   1486U
#define NOTE_G5   1517U
#define NOTE_A5   1546U
#define NOTE_B5   1575U
#define NOTE_C6   1602U

// Frequencies extracted from original ROM SFX data
#define FREQ_SHOOT   0x7E0U   // 2016 — original shoot frequency
#define FREQ_DMGHI   0x67DU   // 1661 — player hit phase 1
#define FREQ_DMGLO   0x7F8U   // 2040 — player hit phase 2

// Helper to build an envelope byte without overflow warnings
#define SFX_ENV(vol, dir, len) ((uint8_t)(((vol) << 4) | (dir) | (len)))

// Pickup arpeggio state machine
static uint8_t pickup_phase;     // 0 = idle, 1-3 = note phases
static uint8_t pickup_timer;     // frames remaining in current phase

// Player hit multi-phase state machine
static uint8_t hit_phase;        // 0 = idle, 1 = phase 1, 2 = phase 2
static uint8_t hit_timer;        // frames remaining in current phase

// ---------- Initialization ----------

void sound_init(void) {
    // Turn on the sound hardware (bit 7 of NR52)
    NR52_REG = AUDENA_ON;

    // Master volume: max on both left and right (0x77 — matches original)
    NR50_REG = 0x77;

    // Route all 4 channels to both speakers (0xFF — matches original)
    NR51_REG = 0xFF;

    // Reset state machines
    pickup_phase = 0;
    pickup_timer = 0;
    hit_phase = 0;
    hit_timer = 0;
}

// ---------- Sound Effects ----------

void sound_shoot(void) {
    // Channel 1: Sara's projectile firing sound
    //
    // Extracted from original ROM SFX 0x26 (data at 0xCA09):
    //   0F 2F 00 D1 E0 87
    //   Count=15, NR10=0x2F, NR11=0x00, NR12=0xD1, NR13=0xE0, NR14=0x87
    //
    // Original: 12.5% duty, fast downward sweep (time=1, decrease, shift=7),
    // vol=13 with fast decay (period=1), starting at freq 2016.
    // Very short and sharp — a quick "pew" with rapid pitch descent.

    // NR10: Sweep time=1, subtract (decrease), shift=7
    //   → frequency drops by f/(2^7) each sweep step = ~1.6% per step
    //   → with time=1, sweeps every 7.8ms (fast)
    NR10_REG = 0x2F;

    // NR11: 12.5% duty cycle (very thin/buzzy), no length counter
    NR11_REG = 0x00;

    // NR12: Volume=13, decrease, period=1 (fastest envelope decay)
    NR12_REG = 0xD1;

    // NR13/NR14: Frequency 0x7E0 (2016), trigger
    NR13_REG = 0xE0;
    NR14_REG = 0x87;
}

void sound_enemy_hit(void) {
    // Channel 4: Enemy death noise burst
    //
    // Extracted from original ROM SFX 0x1E (data at 0xC997):
    //   Phase 1: 03 00 C1 6D 80  (3 frames, harsh noise)
    //   Phase 2: 0F 00 C1 32 80  (15 frames, smoother noise)
    //
    // Original uses a two-phase noise: first a short harsh crunch,
    // then a longer lower rumble. We approximate with the louder
    // first phase since we can't easily do multi-phase in one call.
    // The sound_update() function handles phase 2.

    // NR41: Length=0 (unused, continuous mode)
    NR41_REG = 0x00;

    // NR42: Volume=12, decrease, period=1 (fast decay)
    //   Original: 0xC1 = vol 12, decrease, period 1
    NR42_REG = 0xC1;

    // NR43: Polynomial counter — original phase 1: 0x6D
    //   shift=6, 15-bit mode, divider=5
    //   → rough/crunchy noise texture
    NR43_REG = 0x6D;

    // NR44: Trigger, continuous
    NR44_REG = 0x80;

    // Start phase 2 timer (will fire in sound_update after 3 frames)
    // Phase 2 is a smoother noise tail
    // We skip the multi-phase for simplicity — the initial burst is
    // the most recognizable part of the sound.
}

void sound_player_hit(void) {
    // Channel 1 + Channel 4: Player damage — combined tone + noise
    //
    // Extracted from original ROM SFX 0x0E (data at 0xC8B1 / 0xC8BE):
    //   Ch1 Phase 1: 11 17 80 F8 7D 86  (17 frames, sustained high tone)
    //   Ch1 Phase 2: 28 2E 80 E0 F8 87  (40 frames, descending tone)
    //   Ch4 Phase 1: 0B 00 F7 78 80     (11 frames, harsh noise crash)
    //
    // The original plays a sustained high tone that descends while
    // simultaneously playing a noise crash. We play phase 1 immediately
    // and use sound_update() to transition to phase 2.

    // --- Channel 1: sustained descending tone ---
    // Phase 1: NR10=0x17, NR11=0x80, NR12=0xF8, NR13=0x7D, NR14=0x86
    //   sweep: time=0 (disabled initially), increase, shift=7
    //   duty: 50%, vol=15, increase, period=0 (sustained — no envelope change)
    //   freq=0x67D (1661)
    NR10_REG = 0x17;
    NR11_REG = 0x80;
    NR12_REG = 0xF8;
    NR13_REG = 0x7D;
    NR14_REG = 0x86;

    // --- Channel 4: noise crash ---
    // Phase 1: NR42=0xF7, NR43=0x78
    //   vol=15, decrease, period=7 (slow decay)
    //   shift=7, 15-bit mode, div=0 → deep rumbling noise
    NR41_REG = 0x00;
    NR42_REG = 0xF7;
    NR43_REG = 0x78;
    NR44_REG = 0x80;

    // Start multi-phase timer for Ch1 phase 2
    hit_phase = 1;
    hit_timer = 17;  // Phase 1 lasts 17 frames
}

void sound_pickup(void) {
    // Start the 3-note ascending arpeggio on channel 2.
    // NOTE: This SFX is our own addition — the original game doesn't have
    // a distinct pickup jingle via the SFX system (items may trigger
    // SFX 0x25 which is a simple blip). We keep our custom arpeggio
    // as it provides better feedback in the remake.
    pickup_phase = 1;
    pickup_timer = 0;  // will trigger first note immediately in sound_update

    // Play the first note right away
    // Note 1: E5
    NR21_REG = AUDLEN_DUTY_50;
    NR22_REG = SFX_ENV(12, AUDENV_DOWN, 5);
    NR23_REG = NOTE_E5 & 0xFF;
    NR24_REG = AUDHIGH_RESTART | ((NOTE_E5 >> 8) & 0x07);

    pickup_timer = 6;  // hold for 6 frames (~100ms at 60fps)
}

void sound_boss_warning(void) {
    // Low rumbling warning — Ch4 noise + Ch1 low tone
    NR41_REG = 0x00;
    NR42_REG = 0xA3;  // vol=10, decrease, period=3
    NR43_REG = 0x61;  // shift=6, 7-bit, div=1 (deep rumble)
    NR44_REG = 0x80;

    NR10_REG = 0x00;
    NR11_REG = 0xC0;  // 75% duty
    NR12_REG = 0x71;  // vol=7, decrease, period=1
    NR13_REG = 0x00;  // Low frequency
    NR14_REG = 0x82;
}

// ---------- Per-frame update ----------

void sound_update(void) {
    // --- Player hit multi-phase (Ch1 phase 2) ---
    if (hit_phase != 0) {
        if (hit_timer > 0) {
            hit_timer--;
        } else if (hit_phase == 1) {
            // Transition to phase 2: descending sweep
            // Original: 28 2E 80 E0 F8 87
            //   NR10=0x2E: sweep time=1, decrease, shift=6
            //   NR11=0x80: 50% duty
            //   NR12=0xE0: vol=14, decrease, period=0 (sustained)
            //   freq=0x7F8 (2040) — higher pitch, then sweep down
            NR10_REG = 0x2E;
            NR11_REG = 0x80;
            NR12_REG = 0xE0;
            NR13_REG = 0xF8;
            NR14_REG = 0x87;

            hit_phase = 2;
            hit_timer = 40;  // Phase 2 lasts 40 frames
        } else {
            // Phase 2 done
            hit_phase = 0;
            hit_timer = 0;
        }
    }

    // --- Pickup arpeggio (Ch2) ---
    if (pickup_phase == 0) {
        return;
    }

    if (pickup_timer > 0) {
        pickup_timer--;
        return;
    }

    // Timer expired — advance to next note
    pickup_phase++;

    if (pickup_phase == 2) {
        // Note 2: A5 (ascending)
        NR21_REG = AUDLEN_DUTY_50;
        NR22_REG = SFX_ENV(12, AUDENV_DOWN, 5);
        NR23_REG = NOTE_A5 & 0xFF;
        NR24_REG = AUDHIGH_RESTART | ((NOTE_A5 >> 8) & 0x07);
        pickup_timer = 6;
    } else if (pickup_phase == 3) {
        // Note 3: C6 (highest, resolve)
        NR21_REG = AUDLEN_DUTY_75;
        NR22_REG = SFX_ENV(14, AUDENV_DOWN, 4);
        NR23_REG = NOTE_C6 & 0xFF;
        NR24_REG = AUDHIGH_RESTART | ((NOTE_C6 >> 8) & 0x07);
        pickup_timer = 8;
    } else {
        // Done — arpeggio complete
        pickup_phase = 0;
        pickup_timer = 0;
    }
}
