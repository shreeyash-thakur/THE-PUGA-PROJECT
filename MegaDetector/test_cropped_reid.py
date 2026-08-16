import os
from pathlib import Path
from itertools import combinations

import torch
import torch.nn.functional as F
import timm
from PIL import Image
from torchvision import transforms


CROP_DIR = Path(r"D:\THE PUGA PROJECT\reid_test_cropped")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print("Loading MegaDescriptor-L-384...")
model = timm.create_model(
    "hf-hub:BVRA/MegaDescriptor-L-384",
    pretrained=True
)

model = model.to(DEVICE)
model.eval()

print("Device:", DEVICE)

transform = transforms.Compose([
    transforms.Resize((384, 384)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.5, 0.5, 0.5],
        std=[0.5, 0.5, 0.5]
    )
])


def get_embedding(path):
    image = Image.open(path).convert("RGB")
    tensor = transform(image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        embedding = model(tensor)

    # Normalize embedding
    embedding = F.normalize(embedding, p=2, dim=1)

    return embedding.cpu()


def load_folder(folder):
    embeddings = {}

    if not folder.exists():
        return embeddings

    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp"]:
            continue

        print("Processing:", path.name)
        embeddings[path.name] = get_embedding(path)

    return embeddings


def pairwise_scores(data):
    scores = []

    for (name_a, emb_a), (name_b, emb_b) in combinations(
        data.items(), 2
    ):
        score = F.cosine_similarity(
            emb_a,
            emb_b
        ).item()

        scores.append(score)

        print(
            f"{name_a} <-> {name_b}: {score:.4f}"
        )

    return scores


def cross_scores(data_a, data_b):
    scores = []

    for name_a, emb_a in data_a.items():
        for name_b, emb_b in data_b.items():

            score = F.cosine_similarity(
                emb_a,
                emb_b
            ).item()

            scores.append(score)

            print(
                f"{name_a} <-> {name_b}: {score:.4f}"
            )

    return scores


def average(values):
    return sum(values) / len(values) if values else float("nan")


print("\n==============================")
print("LOADING CROPPED TIGER DATA")
print("==============================")

tiger_a = load_folder(CROP_DIR / "Tiger_A")
tiger_b = load_folder(CROP_DIR / "Tiger_B")


print("\n==============================")
print("SAME TIGER: TIGER A")
print("==============================")

same_a = pairwise_scores(tiger_a)


print("\n==============================")
print("SAME TIGER: TIGER B")
print("==============================")

same_b = pairwise_scores(tiger_b)


print("\n==============================")
print("DIFFERENT TIGERS")
print("==============================")

different = cross_scores(tiger_a, tiger_b)


same_scores = same_a + same_b

same_avg = average(same_scores)
different_avg = average(different)

margin = same_avg - different_avg


print("\n==============================")
print("CROPPED RESULT SUMMARY")
print("==============================")

print(f"Tiger A average:       {average(same_a):.4f}")
print(f"Tiger B average:       {average(same_b):.4f}")
print(f"Same tiger average:    {same_avg:.4f}")
print(f"Different tiger avg:   {different_avg:.4f}")
print(f"Separation margin:     {margin:+.4f}")

print("\nTest completed!")