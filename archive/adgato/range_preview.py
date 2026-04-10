import sys
from PIL import Image

def create_circle_image(radius_sq, padding=2):
    r = int(radius_sq**0.5) + 1
    size = 2 * (r + padding) + 1
    cx = cy = size // 2
    img = Image.new("RGB", (size, size), "white")
    for y in range(size):
        for x in range(size):
            if (x - cx)**2 + (y - cy)**2 <= radius_sq:
                img.putpixel((x, y), (0, 0, 255))
    return img

if __name__ == "__main__":
    radius_sq = int(sys.argv[1])
    img = create_circle_image(radius_sq)
    img.save("circle.png")
    print(f"Saved {img.size[0]}x{img.size[1]} image")