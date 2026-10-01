"""Consecutive native-frame oracle for Game Over and returned-title colours.

Same-age cold-title frames are the reference, excluding the animated cursor
and demo region. Game Over uses the existing reviewed native RGB identity.
Missing frames fail closed; no palette, scene, or rendering writes are used.
"""
from pathlib import Path
import hashlib
from PIL import Image

TITLE_AGES = range(60, 301)
GAMEOVER_AGES = range(10, 61)
TITLE_REGIONS = ((40, 8, 152, 64), (0, 112, 160, 144))


def rgb_frame(path: Path) -> Image.Image:
    with Image.open(path) as source:
        if source.size != (160, 144):
            raise ValueError(f"not a native frame: {path.name}")
        return source.convert('RGB')


def validate_sequence(output: Path) -> dict[str, int]:
    from verify_death_gameover import gameover_rgb_sha256_for_rom
    expected_gameover = gameover_rgb_sha256_for_rom((output / 'runtime/candidate.gb').read_bytes())
    from verify_gameover_restart import compare_images
    # Read every required capture explicitly: an empty glob is never a pass.
    title_checks = gameover_checks = 0
    for age in TITLE_AGES:
        before = output / f'sequence-title-0-{age:04d}.png'
        for cycle in (1, 2):
            after = output / f'sequence-title-{cycle}-{age:04d}.png'
            for region in TITLE_REGIONS:
                compare_images(before, after, region)
            title_checks += 1
    for cycle in (1, 2):
        for age in GAMEOVER_AGES:
            path = output / f'sequence-gameover-{cycle}-{age:04d}.png'
            image = rgb_frame(path)
            if hashlib.sha256(image.tobytes()).hexdigest() != expected_gameover:
                raise ValueError(f'Game Over sequence corrupted: {path.name}')
            gameover_checks += 1
    return {'title_frame_pairs': title_checks, 'gameover_frames': gameover_checks}
