import matplotlib.pyplot as plt
from PIL import Image

img = Image.new("RGBA", (9, 9), (0, 0, 0, 255))
pixels = img.load()
cx, cy = 4, 4

# 7x7 square
for dy in range(-3, 4):
    for dx in range(-3, 4):
        pixels[cx + dx, cy + dy] = (255, 255, 255, 255)

# Extra 5 in each cardinal direction
for i in range(-2, 3):
    pixels[cx + i, cy - 4] = (255, 255, 255, 255)  # North
    pixels[cx + i, cy + 4] = (255, 255, 255, 255)  # South
    pixels[cx - 4, cy + i] = (255, 255, 255, 255)  # West
    pixels[cx + 4, cy + i] = (255, 255, 255, 255)  # East

# Mark center
pixels[cx, cy] = (0, 200, 0, 255)

count = sum(1 for y in range(9) for x in range(9) if pixels[x, y] != (0, 0, 0, 255))
print(f"Visible cells: {count}")

fig, ax = plt.subplots()
fig.set_facecolor("grey")
ax.imshow(img, interpolation="nearest")
ax.axis("off")
ax.set_title(f"Visibility mask ({count} cells)")
plt.show()
