import torch
import timm
from PIL import Image
from torchvision import transforms
from pathlib import Path

CROP_DIR = Path(r"D:\THE PUGA PROJECT\tiger_crops")
OUTPUT_DIR = Path(r"D:\THE PUGA PROJECT\embeddings")

OUTPUT_DIR.mkdir(exist_ok=True)

device = "cuda" if torch.cuda.is_available() else "cpu"

print("Loading MegaDescriptor-L...")
model = timm.create_model(
    "hf-hub:BVRA/MegaDescriptor-L-384",
    pretrained=True
)

model = model.to(device)
model.eval()

print("Device:", device)

transform = transforms.Compose([
    transforms.Resize((384, 384)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

for image_path in sorted(CROP_DIR.glob("*.jpg")):

    print(f"\nProcessing: {image_path.name}")

    image = Image.open(image_path).convert("RGB")
    image = transform(image).unsqueeze(0).to(device)

    with torch.no_grad():
        embedding = model(image)

    output_path = OUTPUT_DIR / f"{image_path.stem}.pt"

    torch.save(embedding.cpu(), output_path)

    print("Embedding shape:", embedding.shape)
    print("Saved:", output_path)

print("\nAll embeddings generated successfully!")