import torch
import timm
from PIL import Image
from torchvision import transforms

IMAGE_PATH = r"D:\THE PUGA PROJECT\test_images\tiger1.jpg"

device = "cuda" if torch.cuda.is_available() else "cpu"

print("Loading MegaDescriptor...")
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

image = Image.open(IMAGE_PATH).convert("RGB")
image = transform(image).unsqueeze(0).to(device)

with torch.no_grad():
    embedding = model(image)

print("Embedding shape:", embedding.shape)
print("Embedding generated successfully!")

torch.save(
    embedding.cpu(),
    "tiger1_embedding.pt"
)

print("Saved: tiger1_embedding.pt")