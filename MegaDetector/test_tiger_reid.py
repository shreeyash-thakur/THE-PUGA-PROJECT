import os
import torch
import timm
from PIL import Image
from torchvision import transforms
from itertools import combinations
import torch.nn.functional as F

# -----------------------------
# SETTINGS
# -----------------------------

BASE_DIR = r"D:\THE PUGA PROJECT\reid_test"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# -----------------------------
# LOAD MEGADESCRIPTOR
# -----------------------------

print("Loading MegaDescriptor...")

model = timm.create_model(
    "hf_hub:BVRA/MegaDescriptor-L-384",
    pretrained=True,
    num_classes=0
)

model = model.to(DEVICE)
model.eval()

print(f"Device: {DEVICE}")

# -----------------------------
# IMAGE TRANSFORM
# -----------------------------

transform = transforms.Compose([
    transforms.Resize((384, 384)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

# -----------------------------
# GENERATE EMBEDDING
# -----------------------------

def get_embedding(image_path):

    image = Image.open(image_path).convert("RGB")

    tensor = transform(image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        embedding = model(tensor)

    embedding = F.normalize(embedding, p=2, dim=1)

    return embedding.cpu()


# -----------------------------
# LOAD TIGER IMAGES
# -----------------------------

def load_tiger(folder):

    images = []

    for file in sorted(os.listdir(folder)):

        if file.lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):

            path = os.path.join(folder, file)

            print("Processing:", path)

            embedding = get_embedding(path)

            images.append({
                "name": file,
                "embedding": embedding
            })

    return images


tiger_a = load_tiger(
    os.path.join(BASE_DIR, "Tiger_A")
)

tiger_b = load_tiger(
    os.path.join(BASE_DIR, "Tiger_B")
)

# -----------------------------
# COMPARE SAME TIGER
# -----------------------------

def compare_same_tiger(images, name):

    scores = []

    print("\n==============================")
    print(f"SAME TIGER: {name}")
    print("==============================")

    for a, b in combinations(images, 2):

        score = F.cosine_similarity(
            a["embedding"],
            b["embedding"]
        ).item()

        scores.append(score)

        print(
            f"{a['name']} ↔ {b['name']} : {score:.4f}"
        )

    return scores


same_a = compare_same_tiger(
    tiger_a,
    "Tiger A"
)

same_b = compare_same_tiger(
    tiger_b,
    "Tiger B"
)

# -----------------------------
# COMPARE DIFFERENT TIGERS
# -----------------------------

print("\n==============================")
print("DIFFERENT TIGERS")
print("==============================")

different_scores = []

for a in tiger_a:

    for b in tiger_b:

        score = F.cosine_similarity(
            a["embedding"],
            b["embedding"]
        ).item()

        different_scores.append(score)

        print(
            f"{a['name']} ↔ {b['name']} : {score:.4f}"
        )

# -----------------------------
# SUMMARY
# -----------------------------

print("\n==============================")
print("RESULT SUMMARY")
print("==============================")

if same_a:
    print(
        f"Tiger A average: "
        f"{sum(same_a)/len(same_a):.4f}"
    )

if same_b:
    print(
        f"Tiger B average: "
        f"{sum(same_b)/len(same_b):.4f}"
    )

if different_scores:
    print(
        f"Different tiger average: "
        f"{sum(different_scores)/len(different_scores):.4f}"
    )

print("\nTest completed!")