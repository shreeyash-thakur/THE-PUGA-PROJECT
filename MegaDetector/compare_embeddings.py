import torch
import torch.nn.functional as F
from pathlib import Path

EMBEDDING_DIR = Path(r"D:\THE PUGA PROJECT\embeddings")

files = sorted(EMBEDDING_DIR.glob("*.pt"))

embeddings = {}

for file in files:
    embeddings[file.stem] = torch.load(file, map_location="cpu").flatten()

print("\n=== Similarity Results ===\n")

names = list(embeddings.keys())

for i in range(len(names)):
    for j in range(i + 1, len(names)):

        a = embeddings[names[i]].unsqueeze(0)
        b = embeddings[names[j]].unsqueeze(0)

        similarity = F.cosine_similarity(a, b).item()

        print(
            f"{names[i]:25} ↔ {names[j]:25} "
            f"{similarity:.4f}"
        )