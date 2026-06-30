// xorshift32 — must match tools/crates/quintra-procgen/src/rng.rs bit-for-bit.
#ifndef QUINTRA_CORE_RNG_H
#define QUINTRA_CORE_RNG_H

#include "core/types.h"

extern u32 rng_state;

void  rng_seed(u32 seed);
u32   rng_next(void);
u8    rng_next_u8(void);
u8    rng_range(u8 n);          // uniform [0, n)
u16   rng_range16(u16 n);

#endif
