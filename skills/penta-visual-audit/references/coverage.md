# Coverage contract

The canonical inventory is `docs/audit/visual_audit_catalog.json`. The site builder must create exactly the declared count for every category; missing evidence becomes an explicit red card, never a silently shortened section.

## Current inventory

| Category | Required items | Minimum proof |
| --- | ---: | --- |
| Stages | 7 | 20 OG and 20 DX scripted samples per stage |
| Bosses | 9 | 4 paired OG/DX material phases plus passing geometry gates |
| Minibosses | 16 | One full native five-entity descriptor each; two complete identical replays; selectors 9–16 must prove the ROM's 9→1 … 16→8 YAML palette aliases |
| Pickups | 19 | Exact semantic tile matches in candidate-bound live states; composite arrow receipts also require distinct native glyphs, a complete scene, and a stable south edge |
| Heroes | 2 | Sara W and Sara D spotlight identity/OAM/name proof |
| Regular monsters | 36 | Every remaining spotlight identity with OAM/name proof |
| Projectiles/effects | 8 | Targeted live OAM observation, screenshot, palette slot, replay |
| Opening | 33 | Every inventoried panel |
| Pre-final | 43 | Every inventoried panel |
| Ending | 10 | Deterministic A/B inventories and displayed A panels |
| Story keyframes | 12 | Opening, pre-final, post-final, credits, end, epilogue anchors |
| Secret/bonus | 3 | Live secret jet route phases |
| Menus | 10 | Two deterministic passes across five pages |
| Hazards | 24 | Natural/miniboss spike phases and low-health samples |
| Title | 16 | Title/showcase and cursor samples |
| Death/game over | 12 | Transition inventory |

## Status semantics

- `covered`: the required gate passed, provenance is bound to the candidate hash, and the item meets its minimum evidence count.
- `partial`: some useful image/context exists, but the item lacks required proof or its parent gate did not pass.
- `missing`: no qualifying evidence exists.
- `suspicious blank`: automated image metrics found fewer than two colors or a dominant-color fraction of at least 0.9995. Inspect it; an intentional transition must be documented, not automatically accepted.

Machine status answers “is the claimed evidence complete and reproducible?” Human status answers “does this actually look release-ready?” Both must pass for a release visual sign-off.

## Provenance

The primary evidence root must be the `matrix/artifacts` directory beside a passing deterministic-suite `manifest.json`. Its tested ROM must equal the SHA-256 in the selected passing release receipt. Supplemental miniboss, pickup, or projectile receipts must repeat the same hash and include image hashes plus their family-specific deterministic integrity checks.

The built site copies PNGs into content-addressed `media/<prefix>/<sha256>.png`, embeds the full audit manifest in `index.html`, writes `manifest.json`, and covers all files with `CHECKSUMS.sha256`. Generated output is disposable and must remain outside Git.

## Human review

Reviewer verdicts and notes live in browser local storage keyed by stable `category:item` audit IDs. Export review JSON before replacing or moving browser storage. A machine-complete site with unreviewed human cards is not a human sign-off.
