# User Demo Save State Manifest

User demo session 2026-05-08 19:11-20:03 EDT (~52 min). All states are mgba-qt save state format (.ss) — NOT loadable directly in PyBoy. Will be useful via:
- Visual frame extraction from corresponding video (`~/Videos/twitch/2026-05-08 18-58-09.mp4`)
- Imported into mgba via Lua script for memory probing
- Reproduced in PyBoy via input-replay matching observed game state

## Level 1 progression (ground truth path)

| Time | File | Notes |
|------|------|-------|
| 19:11 | `191148_user_demo_ss1.ss` | First save — early L1 |
| 19:12 | `191247_orb_item.ss` | Mystery orb item (probably the star) |
| 19:14 | `191434_post_teleporter.ss` | Crossed first optional teleporter |
| 19:15 | `191514_dragon_form.ss` | Dragon transformation from kills |
| 19:17 | `191707_back_from_star.ss` | Back from star detour |
| 19:18 | `191809_flash_bomb.ss` | Flash bomb / mega spiral attack |
| 19:20 | `192002_pre_dragon_portal.ss` | Approaching dragon teleporter |
| 19:20 | `192015_at_dragon_item.ss` | At Dragon item |
| 19:22 | `192220_lock_teleporter.ss` | Lock teleporter (3rd portal) |
| 19:23 | `192315_rock_item.ss` | Rock item (visual of lock effect?) |

## Hidden stage (SHMUP)

| Time | File | Notes |
|------|------|-------|
| 19:40 | `194014_PRE_secret_trigger.ss` | Right before pressing secret trigger |
| 19:40 | `194037_POST_secret_trigger.ss` | (same file size — may not have re-saved) |
| 19:41 | `194147_HIDDEN_STAGE_START.ss` | **Inside SHMUP — start state** |
| 19:43 | `194339_SHMUP_miniboss.ss` | First SHMUP mini-boss |
| 19:48 | `194849_SHMUP_mb2_post_heal.ss` | After 2nd mini-boss + healing |
| 19:50 | `195029_SHMUP_post_hoard.ss` | After getting item hoard |
| 19:51 | `195109_back_to_main.ss` | Back to main level w/ dragon items |

## Shalamar (Boss 1) — confirmed in pause screen

| Time | File | Notes |
|------|------|-------|
| 19:53 | `195321_BOSS_AREA_ENTRY.ss` | Just entered boss area |
| 19:53 | `195329_BOSS1_SHALAMAR_pre_fight.ss` | **Pre-fight, fully stacked** |
| 19:55 | `195542_SHALAMAR_DEAD.ss` | Post-kill |

## Level 2

| Time | File | Notes |
|------|------|-------|
| 19:57 | `195759_L2_pumpkin_mb.ss` | Level 2 first mini-boss = pumpkin head |
| 20:00 | `200043_L2_seahorse_mb.ss` | Seahorse mini-boss in upper section |
| 20:01 | `200142_L2_post_troll_tp.ss` | After dead-end teleporter (game troll) |
| 20:03 | `CHECKPOINT_200320.ss` + `.sav` | Final checkpoint after death |

## Key game knowledge from narration

### Door discovery (the missing piece for RL)
- Path: dungeon → 2 mini-bosses (Gargoyle/Spider) → secret stage entrance "south at middle of 3 passages" → SHMUP → back to main → "left and up, can't miss it" → arena
- Without the secret stage detour, you're "screwed" for boss fight (insufficient items)

### Shalamar kill mechanics
- Weak point: **front-center face/eyes/head**
- **Claws guard** the weak point intermittently
- **Whole-screen shake** = body attack telegraph; dodge body
- Pattern: wait → spam shots when face exposed → dodge during shake → repeat

### Power-ups
- 3 optional teleporters in level 1: star, dragon, lock — each timed buff
- Dragon transformation also possible from killing many monsters
- Items: HP1, HP2, poison cure, "!?" (random), shield, fat arrow (good), 2-way diagonal (bad), spread, mega spiral, flash bomb
- Inventory: Up/Down to cycle items in pause menu
- Start button drops item

### Combat
- **Sticky aim**: dpad direction persists for shooting until next movement
- A = primary fire, B = secondary
- Best strategy: position → aim once → spam A from stable position
