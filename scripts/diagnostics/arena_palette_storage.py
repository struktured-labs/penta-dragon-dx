"""Exact palette-table layout for the reviewed data/code separation overlay."""
import hashlib

PALETTE_STORAGE_SHA256 = "6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9"


def arena_palette_table(rom: bytes, target: int) -> bytes:
    if not 0 <= target <= 8:
        raise ValueError("invalid arena target")
    relocated = hashlib.sha256(rom).hexdigest() in {
        PALETTE_STORAGE_SHA256,
        "8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4",
        "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722",
        # Experimental Troop cadence overlay: bank 20 only, LUT bank unchanged.
        "40bca0a0cc736eb002754bd0e80bbe6d0bd2105bdda5d69b6942b8bfd7715b78",
        "dfe2bfb2d3f248c7d14963b8615245ec45702f578ac12f6efdfeabd6f367e37b",
        "3e2421bcd94b747c810b42246c6da1d2019cad1e068eb0326012222dbe106306",
        # r462 combines only the two source-owned bank-20 boss repairs.
        "5c775d6cdaf259576593c14863410746c8d8077cc231fcf37bd9f604bcbde413",
        # r475 is the exact disjoint union of r462 and the bank13/28 Stage-7
        # repair; its relocated arena data and loader are inherited bytewise.
        "59384e3c0ea5508ade2ff8d08af2f3012c4eff1f5f9cf1cebb2f04273cd1693f",
        # r515 adds only ending/story handoff code. The relocated bank-23
        # Riff/Crystal/Troop tables and their loader remain inherited; its
        # later Angela overlap is intentionally caught by the per-table gate.
        "30f85499221a057ea80dc82f2a49f10e8857ecfa6b18d546cc169ab25c551879",
        # r516 moves that ending guard into bank 20, preserving every arena
        # table while keeping the relocated tables and loader byte-exact.
        "8f04ebe80ea96ea01d0c46d24f80c7b0b417e1bf967dcd576543ad264deaa230",
        # r517 keeps the same table-safe placement and restores ROM-source
        # reads to their originating bank before the native publisher tail.
        "e3eb4d99a8b88ecdc61ca02b0823f97d8a0e773054c00349b4e1939513965932",
        # r518 adds only the completed-page E7 ending reveal rule.
        "918d95a88349aa2bb29c5a52285c79d5dba7a014848e5ccf41bae46890961808",
        # r519 synchronizes the stock epilogue pre-fade reset in bank 1/20;
        # every relocated arena table remains inherited byte-for-byte.
        "9b368aaef0e48757fb0bfed108e30f20490150f329e78b6001ed0b53fa7f7af9",
        # r520 preserves caller AF across r519's return-address dispatcher.
        "6e56a1589072b878df4135e02950c617cb8c87aace4b53fe58dc554b429f7261",
        # r521 bypasses the inherited POP HLs after restoring dispatch state.
        "37c9e9eccd78013727e1657075e37f02c4e7dc3534eb05baee9f7890fe3246ba",
        # r522 gates the additional black CRAM work to completed epilogue text.
        "9172cdc991afb93c1ae10cc46a3b81503ca0872f6a3f34a6ee44f581bbff09e7",
        # r523 branches from r518 through a private cycle-equivalent dispatcher.
        "e6559ff3c4687d58b43e90f67f55bd35be62a644e855caee41d968509a65aceb",
        # r524 retains r518 credit-path cycles and uses an unreachable branch.
        "e2ffa7e6c91cb630066524c49c00b56243f9bc61b137bab367b97a441c95224a",
        # r525 makes the inherited repeated-row CRAM fill atomic in VBlank.
        "9ec2fb605c5e4e98a945aee422c8a95284192d8c44b88bcab783c3d3b09d837b",
        # r526 instead retries only the final repeated-row color pair while
        # preserving every relocated arena table byte-for-byte.
        "16dcaa83d2d21d33357f332415810afad9b0a83e79f9aee4163789d77e3576cd",
        # r527 performs that pair retry through the inherited phase wait.
        "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b",
        # r528 changes only palette-publisher code outside the arena tables.
        "e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50",
        # r529 corrects r528's register-restore order in the same code spans.
        "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208",
        # r530 atomically waits/writes and returns through the coherent mapper.
        "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30",
        # r531 adds the reviewed VBlank fast path to the same publisher.
        "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855",
        # r532 masks IE while preserving IME in the same publisher path.
        "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821",
        # r533 changes only the neutral story-row route in bank 13.
        "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba",
        # r534 changes only the private Stage-4 cache key in bank 22.
        "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b",
        # Menu/title-only overlay; relocated arena data/loader unchanged.
        "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3",
        "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576",
        "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350",  # r536: inherited observer/data ABI
        "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b",  # title row guard: unchanged gameplay observer/data ABI
        "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d",  # death/restart successor: unchanged arena storage
        "b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96",
        "ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63",
    } and target in (1, 2, 5)
    bank = 23 if relocated else 13
    offset = bank * 0x4000 + 0x3200 + target * 0x100
    table = rom[offset:offset + 0x100]
    if relocated:
        # Independent builder-derived data, not an acceptance mask over the
        # observed active table or code bytes in the old source location.
        from compose_arena_palette_storage_r455 import TABLE_BUILDERS
        expected = bytes(TABLE_BUILDERS[0x72 + target]())
        if table != expected:
            raise ValueError("relocated arena data differs from its builder")
    return table
