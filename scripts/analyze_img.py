from PIL import Image
import sys

img = Image.open(sys.argv[1])
colors = img.getcolors()
print(f"Image {sys.argv[1]}: size={img.size}, unique_colors={len(colors) if colors else 'many'}")
if colors:
    # Print the top colors
    sorted_colors = sorted(colors, key=lambda x: x[0], reverse=True)
    for count, color in sorted_colors[:10]:
        print(f"  {count} pixels of color {color}")
