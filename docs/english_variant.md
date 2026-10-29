# English variant (HTI translation on Penta Dragon DX)

`scripts/build_english_variant.py` layers the HTI v1.00 English translation
(`penta.ips`, sha256 `9ac36c13…051d`) onto a Penta Dragon DX build. Nothing is
committed as a ROM; users supply the stock ROM, the DX build and the IPS:

    python scripts/build_english_variant.py --original "Penta Dragon (J).gb" \
        --dx penta_dragon_dx.gb --ips penta.ips --output penta_dragon_dx_en.gb

What it does:

* applies every IPS record, refusing any that overlaps a byte DX changed;
* mirrors the HTI font edits in bank 0E into DX's bank-13 cinema copy;
* merges the title text so the DX `DX V3.01 STRUK LABS` row is kept and the
  HTI `©` row replaces the kana copyright (same table length);
* adds two translation-credit pages at the end of the ending dialogue, right
  after Lisa's last line and before the staff roll, so they show in every
  normal playthrough:

      English version / by HTI / Hacking  Hiryuu
      Translation / Tyrome Williams / Help  Kero Hazel

  The script grows by 90 bytes into the unreferenced fill after the stock end
  marker (bank 0F 0x5138–0x53FF); the builder asserts that fill is untouched;
* fixes header and global checksums and writes `<output>.receipt.json`.

The DX title screen only renders its palette-assigned rows, so the credit is
not on the title (checked by VRAM poke on every row).

## Credits

English translation: HTI — hacking Hiryuu, translation Tyrome Williams,
help Kero Hazel (HTI v1.00, 2003).

## Verification (2026-10-29)

* attract-mode lockstep vs the Japanese DX build, frames 0–26000: identical
  except in the title-text windows; it matches byte for byte again after each window;
* natural Penta Dragon kill → ending (credit pages on screen) → staff roll →
  title → GAME START → stage play;
* Stage-7 state patrol and natural kills of the other bosses.
