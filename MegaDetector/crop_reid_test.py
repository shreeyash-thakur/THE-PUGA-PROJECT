import json
from pathlib import Path
from PIL import Image

RESULTS = Path(r"D:\THE PUGA PROJECT\reid_detections.json")
OUTPUT_DIR = Path(r"D:\THE PUGA PROJECT\reid_test_cropped")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with open(RESULTS, "r") as f:
    results = json.load(f)

saved = 0

for item in results:

    image_path = Path(item["file"])

    animal_detections = [
        d for d in item.get("detections", [])
        if d.get("category") == "animal"
    ]

    if not animal_detections:
        print(f"SKIP: {image_path.name} -> no animal detection")
        continue

    # If multiple animals are detected, use the largest bounding box.
    detection = max(
        animal_detections,
        key=lambda d: d["bbox"][2] * d["bbox"][3]
    )

    confidence = detection["confidence"]

    x, y, w, h = detection["bbox"]

    image = Image.open(image_path).convert("RGB")

    # MegaDetector bbox format is:
    # [x, y, width, height]
    x1 = round(x)
    y1 = round(y)
    x2 = round(x + w)
    y2 = round(y + h)

    # Keep coordinates inside image
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(image.width, x2)
    y2 = min(image.height, y2)

    crop = image.crop((x1, y1, x2, y2))

    # Preserve Tiger_A / Tiger_B structure
    tiger_group = image_path.parent.name

    output_dir = OUTPUT_DIR / tiger_group
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / image_path.name

    crop.save(output_path, quality=95)

    saved += 1

    print(
        f"SAVED: {output_path}"
        f" | confidence={confidence:.4f}"
        f" | bbox=({x1}, {y1}, {x2}, {y2})"
    )

print()
print("======================================")
print(f"Created {saved} cropped images")
print(f"Output: {OUTPUT_DIR}")
print("======================================")