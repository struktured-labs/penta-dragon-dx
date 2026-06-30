#include "core/rng.h"

u32 rng_state = 0xDEADBEEFUL;

void rng_seed(u32 seed) {
    rng_state = (seed == 0UL) ? 0xDEADBEEFUL : seed;
}

u32 rng_next(void) {
    u32 x = rng_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    rng_state = x;
    return x;
}

u8 rng_next_u8(void) {
    return (u8)(rng_next() & 0xFFUL);
}

u8 rng_range(u8 n) {
    if (n == 0) return 0;
    return rng_next_u8() % n;
}

u16 rng_range16(u16 n) {
    if (n == 0) return 0;
    return (u16)(rng_next() & 0xFFFFUL) % n;
}
