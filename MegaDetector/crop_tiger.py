import json
from pathlib import Path
from PIL import Image

RESULTS = Path(r"D:\THE PUGA PROJECT\test_results.json")
OUTPUT_DIR = Path(r"D:\THE PUGA PROJECT\tiger_crops")

OUTPUT_DIR.mkdir(exist_ok=True)

with open(RESULTS, "r") as f:
    results = json.load(f)

for item in results:
    image_path = Path(item["file"])

    if not item["detections"]:
        continue

    image = Image.open(image_path)

    for i, detection in enumerate(item["detections"]):
        x1, y1, x2, y2 = detection["bbox"]

        # Convert coordinates to integers
        x1, y1, x2, y2 = map(round, (x1, y1, x2, y2))

        # Keep coordinates inside image
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image.width, x2)
        y2 = min(image.height, y2)

        crop = image.crop((x1, y1, x2, y2))

        output_name = f"{image_path.stem}_animal_{i+1}.jpg"
        output_path = OUTPUT_DIR / output_name

        crop.save(output_path)

        print(f"Saved: {output_path}")

print("\nTiger/animal crops created.")