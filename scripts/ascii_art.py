from PIL import Image
import sys

img = Image.open(sys.argv[1]).convert("L")
img = img.resize((80, 36))
pixels = img.load()

chars = " .:-=+*#%@"
for y in range(36):
    line = []
    for x in range(80):
        val = pixels[x, y]
        char_idx = int(val / 256 * len(chars))
        line.append(chars[char_idx])
    print("".join(line))
