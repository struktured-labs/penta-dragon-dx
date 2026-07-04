#include <gb/gb.h>

#include "audio/music.h"

// D-dorian "glassy arp" exploration loop (~112 BPM, 8 frames/row,
// 32 rows). Freqs precomputed: x = 2048 - 131072/f.
#define N_C5  1798
#define N_D5  1825
#define N_E5  1849
#define N_F5  1860
#define N_G5  1881
#define N_A5  1899
#define N_B5  1915
#define N_C6  1923
#define N_D6  1936
#define REST  0

static const u16 melody[32] = {
    N_D5, N_A5, N_F5, N_A5,   N_C6, N_A5, N_F5, N_A5,
    N_D5, N_A5, N_F5, N_A5,   N_E5, N_G5, N_B5, N_G5,
    N_D5, N_A5, N_F5, N_A5,   N_C6, N_A5, N_F5, N_A5,
    N_G5, N_B5, N_D6, N_B5,   N_A5, N_F5, N_E5, N_C5,
};

// Wave-channel bass, one note per 4 rows. f = 65536/(2048-x).
#define B_D3  1601
#define B_C3  1547
#define B_G3  1713
#define B_A3  1750
static const u16 bassline[8] = {
    B_D3, B_D3, B_C3, B_C3, B_D3, B_D3, B_G3, B_A3,
};

// Triangle wavetable (32 4-bit samples)
static const u8 tri_wave[16] = {
    0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF,
    0xFE, 0xDC, 0xBA, 0x98, 0x76, 0x54, 0x32, 0x10,
};

// Boss loop — E minor, driving (~144 BPM => 6 frames/row)
#define N_FS5 1871
#define N_E6  1943
static const u16 boss_melody[32] = {
    N_E5, N_E5, N_G5, N_E5,   N_B5, N_A5, N_G5, N_A5,
    N_E5, N_E5, N_G5, N_E5,   N_D6, N_B5, N_A5, N_G5,
    N_E5, N_G5, N_B5, N_E6,   N_D6, N_B5, N_A5, N_G5,
    N_FS5,N_A5, N_D6, N_A5,   N_B5, N_G5, N_FS5,N_E5,
};
#define B_E3  1650
#define B_B3  1783
static const u16 boss_bass[8] = {
    B_E3, B_E3, B_G3, B_G3, B_A3, B_A3, B_E3, B_B3,
};

// Title — A minor, sparse/haunting (~90 BPM => 10 frames/row)
static const u16 title_melody[32] = {
    N_A5, REST, N_C6, REST,   N_E6, REST, N_C6, REST,
    N_B5, REST, N_G5, REST,   N_A5, REST, REST, REST,
    N_A5, REST, N_D6, REST,   N_C6, REST, N_A5, REST,
    N_G5, REST, N_E5, REST,   N_A5, REST, REST, REST,
};
static const u16 title_bass[8] = {
    B_A3, B_A3, B_G3, B_G3, B_C3, B_C3, B_D3, B_A3,
};

// Victory — bright, ascending (reuses boss tempo)
static const u16 vic_melody[32] = {
    N_C5, N_E5, N_G5, N_C6,   N_G5, N_C6, N_E6, N_C6,
    N_D5, N_G5, N_B5, N_D6,   N_B5, N_D6, N_D6, REST,
    N_C5, N_E5, N_G5, N_C6,   N_E6, N_C6, N_G5, N_E5,
    N_C6, N_C6, N_C6, REST,   N_C6, REST, REST, REST,
};

// Gameover — descending dirge (slow)
static const u16 go_melody[32] = {
    N_A5, REST, N_G5, REST,   N_F5, REST, N_E5, REST,
    N_D5, REST, N_C5, REST,   N_D5, REST, REST, REST,
    N_A5, REST, N_G5, REST,   N_E5, REST, N_D5, REST,
    N_C5, REST, N_C5, REST,   REST, REST, REST, REST,
};

static u8 playing;
static u8 frame_div;
static u8 row;
static u8 frames_per_row = 8;
static const u16 *cur_melody = melody;
static const u16 *cur_bass   = bassline;

static void load_wave(void) {
    u8 i;
    NR30_REG = 0x00;                       // DAC off while loading
    for (i = 0; i < 16; ++i) {
        *((volatile u8 *)(0xFF30 + i)) = tri_wave[i];
    }
    NR30_REG = 0x80;                       // DAC on
}

void music_play_caverns(void) {
    load_wave();
    cur_melody = melody;
    cur_bass   = bassline;
    frames_per_row = 8;
    playing  = 1;
    frame_div = 0;
    row      = 0;
}

void music_play_boss(void) {
    load_wave();
    cur_melody = boss_melody;
    cur_bass   = boss_bass;
    frames_per_row = 6;      // faster tempo
    playing  = 1;
    frame_div = 0;
    row      = 0;
}

void music_play_title(void) {
    load_wave();
    cur_melody = title_melody;
    cur_bass   = title_bass;
    frames_per_row = 10;     // slow, haunting
    playing  = 1;
    frame_div = 0;
    row      = 0;
}

void music_play_victory(void) {
    load_wave();
    cur_melody = vic_melody;
    cur_bass   = boss_bass;
    frames_per_row = 6;
    playing  = 1;
    frame_div = 0;
    row      = 0;
}

void music_play_gameover(void) {
    load_wave();
    cur_melody = go_melody;
    cur_bass   = title_bass;
    frames_per_row = 12;     // dirge
    playing  = 1;
    frame_div = 0;
    row      = 0;
}

void music_stop(void) {
    playing = 0;
    NR22_REG = 0x00; NR24_REG = 0x80;      // melody off
    NR30_REG = 0x00;                       // wave DAC off
}

void music_tick(void) {
    if (!playing) return;
    if (frame_div++ < frames_per_row) return;
    frame_div = 0;

    {
        u16 note = cur_melody[row];
        if (note != REST) {
            NR21_REG = 0x80;               // duty 50%
            NR22_REG = 0x63;               // vol 6, decay 3 — soft pluck
            NR23_REG = (u8)(note & 0xFF);
            NR24_REG = (u8)(0x80 | (note >> 8));
        }
    }
    if ((row & 0x03) == 0) {
        u16 b = cur_bass[row >> 2];
        NR31_REG = 0x00;
        NR32_REG = 0x40;                   // 50% output level
        NR33_REG = (u8)(b & 0xFF);
        NR34_REG = (u8)(0x80 | (b >> 8));
    }
    row = (u8)((row + 1) & 0x1F);
}
