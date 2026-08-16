"""
Tiger Re-ID diagnostic test (fixed).

Changes vs. the original test_tiger_reid.py:
  1. Correct MegaDescriptor-L-384 preprocessing (mean=std=0.5, per the official
     HF model card) instead of ImageNet stats.
  2. Full diagnostic mode: filename, image size, embedding shape, embedding
     norm, an embedding fingerprint (hash), and the first few embedding
     values are printed for every image.
  3. A raw-file hash (MD5 of the image bytes) is printed and cross-checked
     for every image in the dataset. If two files share a raw-image hash,
     the script raises a loud warning BEFORE running the model, because two
     byte-identical inputs are guaranteed to produce a 1.0000 cosine
     similarity no matter what the model does.
  4. An explicit self-test that feeds two different images through
     get_embedding() and asserts the resulting embeddings are not identical
     (this is what originally should have caught the bug).
  5. BASE_DIR is resolved relative to this file (portable) with a fallback
     you can override with the REID_TEST_DIR environment variable, instead
     of a hardcoded Windows path.
  6. No threshold, no stripe detection, no DB/frontend/map features added,
     per the task scope.
"""

import os
import sys
import hashlib
import torch
import timm
from PIL import Image
from torchvision import transforms
from itertools import combinations
import torch.nn.functional as F

# -----------------------------
# SETTINGS
# -----------------------------

BASE_DIR = os.environ.get(
    "REID_TEST_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reid_test"),
)
BASE_DIR = os.path.abspath(BASE_DIR)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

DIAGNOSTIC = True  # prints per-image fingerprints, shapes, norms, etc.

# -----------------------------
# LOAD MEGADESCRIPTOR
# -----------------------------

print("Loading MegaDescriptor...")

MODEL_NAME = "hf-hub:BVRA/MegaDescriptor-L-384"

model = timm.create_model(
    MODEL_NAME,
    pretrained=True,
    num_classes=0,   # strip classifier head -> pooled feature embedding
)

model = model.to(DEVICE)
model.eval()  # disable dropout / put batchnorm in eval mode -> deterministic

print(f"Model: {MODEL_NAME}")
print(f"Device: {DEVICE}")

# -----------------------------
# IMAGE TRANSFORM
# -----------------------------
#
# BUG (original code): used ImageNet mean/std
#     mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
# MegaDescriptor-L-384's own model card (BVRA/MegaDescriptor-L-384 on the
# HF Hub) specifies mean=std=[0.5, 0.5, 0.5]. Using the wrong normalization
# statistics shifts and rescales every pixel differently than what the
# network was trained on, which quietly degrades embedding quality (it does
# NOT by itself explain the 1.0000 duplicates, but it is a real correctness
# bug against item #6/#12 of the task and is fixed here).

transform = transforms.Compose([
    transforms.Resize((384, 384)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.5, 0.5, 0.5],
        std=[0.5, 0.5, 0.5],
    )
])

# -----------------------------
# HELPERS: HASHING / FINGERPRINTING
# -----------------------------

def file_md5(path, chunk_size=8192):
    """Hash of the raw image bytes on disk -- proves whether two files
    are literally the same file content, independent of the model."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def embedding_fingerprint(embedding_tensor, n_bytes=8):
    """Short, stable hash of the embedding values themselves. If two
    different images ever produce the same fingerprint, their embeddings
    are numerically identical (not just similar)."""
    data = embedding_tensor.detach().cpu().contiguous().numpy().tobytes()
    return hashlib.sha256(data).hexdigest()[:16]


# -----------------------------
# GENERATE EMBEDDING
# -----------------------------

def get_embedding(image_path, verbose=DIAGNOSTIC):

    # Load fresh from disk every call -- no shared/cached PIL Image or
    # tensor object is reused across images.
    image = Image.open(image_path).convert("RGB")
    image_size = image.size  # (width, height) of the *source* file

    tensor = transform(image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        embedding = model(tensor)

    embedding = F.normalize(embedding, p=2, dim=1)
    embedding = embedding.cpu()

    if verbose:
        norm = embedding.norm(p=2, dim=1).item()
        fp = embedding_fingerprint(embedding)
        first_vals = embedding[0, :5].tolist()
        raw_hash = file_md5(image_path)
        print(f"    file            : {os.path.basename(image_path)}")
        print(f"    raw file MD5    : {raw_hash}")
        print(f"    image size      : {image_size}")
        print(f"    embedding shape : {tuple(embedding.shape)}")
        print(f"    embedding norm  : {norm:.6f}")
        print(f"    embedding fp    : {fp}")
        print(f"    first 5 values  : {[round(v, 4) for v in first_vals]}")

    return embedding, image_size


# -----------------------------
# LOAD TIGER IMAGES
# -----------------------------

def load_tiger(folder, label):

    images = []

    print(f"\n------ Loading {label} from {folder} ------")

    for file in sorted(os.listdir(folder)):

        if file.lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):

            path = os.path.join(folder, file)

            print(f"\nProcessing: {path}")

            embedding, image_size = get_embedding(path)

            images.append({
                "name": file,
                "path": path,
                "embedding": embedding,
                "image_size": image_size,
                "raw_hash": file_md5(path),
                "fingerprint": embedding_fingerprint(embedding),
            })

    return images


tiger_a = load_tiger(os.path.join(BASE_DIR, "Tiger_A"), "Tiger A")
tiger_b = load_tiger(os.path.join(BASE_DIR, "Tiger_B"), "Tiger B")

all_images = tiger_a + tiger_b

# -----------------------------
# DATASET SANITY CHECK
# -----------------------------
# Catch duplicate/re-used source files BEFORE trusting any similarity score.
# Two files with the same raw MD5 hash are the same image on disk -- any
# deterministic model (eval mode, no dropout) is mathematically guaranteed
# to produce identical embeddings for them, and cosine similarity will be
# exactly 1.0000. That is a data problem, not a model problem.

print("\n==============================")
print("DATASET INTEGRITY CHECK")
print("==============================")

hash_to_names = {}
for img in all_images:
    hash_to_names.setdefault(img["raw_hash"], []).append(img["name"])

duplicates_found = False
for h, names in hash_to_names.items():
    if len(names) > 1:
        duplicates_found = True
        print(f"[DUPLICATE FILE] identical image bytes (MD5 {h}) used for: {names}")

if not duplicates_found:
    print("No duplicate source image files detected.")
else:
    print(
        "\nWARNING: The dataset contains byte-identical image files under "
        "different filenames (see above). Any pair built from these files "
        "will show cosine similarity == 1.0000 regardless of the Re-ID "
        "model, because the model is receiving the exact same input twice. "
        "This is the root cause of the previously reported suspicious "
        "1.0000 'different tiger' scores. Fix by replacing the duplicated "
        "files with genuinely distinct photos before trusting any "
        "similarity numbers from this dataset."
    )

# Also flag embedding-level duplicates in case two *different* files somehow
# still produced numerically identical embeddings (would point to a bug in
# the embedding code itself, e.g. accidental caching/reuse).
fp_to_names = {}
for img in all_images:
    fp_to_names.setdefault(img["fingerprint"], []).append(img["name"])

for fp, names in fp_to_names.items():
    unique_hashes = {n: h for n, h in ((img["name"], img["raw_hash"]) for img in all_images if img["name"] in names)}
    if len(names) > 1 and len(set(unique_hashes.values())) > 1:
        print(
            f"[PIPELINE BUG] different source files {names} produced an "
            f"IDENTICAL embedding fingerprint ({fp}) despite different raw "
            f"file content. This would indicate a real bug in get_embedding() "
            f"(e.g. tensor/model reuse, wrong indexing, or a caching issue), "
            f"not just a duplicated dataset."
        )

# -----------------------------
# EXPLICIT TEST: DIFFERENT IMAGES -> DIFFERENT EMBEDDINGS
# -----------------------------

print("\n==============================")
print("SELF-TEST: distinct files must yield distinct embeddings")
print("==============================")

distinct_pairs_tested = 0
for a, b in combinations(all_images, 2):
    if a["raw_hash"] == b["raw_hash"]:
        # Same file content -- identical embedding is *expected*, skip.
        continue
    distinct_pairs_tested += 1
    same_embedding = torch.equal(a["embedding"], b["embedding"])
    status = "FAIL (identical embeddings!)" if same_embedding else "OK (embeddings differ)"
    print(f"{a['name']} vs {b['name']}: {status}")
    if same_embedding:
        print(
            "  -> Two genuinely different image files produced numerically "
            "identical embeddings. This points to a real bug (e.g. a stale "
            "tensor being reused, or the wrong image being loaded)."
        )

print(f"\nTested {distinct_pairs_tested} distinct-file pairs.")

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

        flag = "  <-- SAME FILE (duplicate)" if a["raw_hash"] == b["raw_hash"] else ""
        print(f"{a['name']} <-> {b['name']} : {score:.4f}{flag}")

    return scores


same_a = compare_same_tiger(tiger_a, "Tiger A")
same_b = compare_same_tiger(tiger_b, "Tiger B")

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

        flag = "  <-- SAME FILE (duplicate)" if a["raw_hash"] == b["raw_hash"] else ""
        print(f"{a['name']} <-> {b['name']} : {score:.4f}{flag}")

# -----------------------------
# SUMMARY
# -----------------------------

print("\n==============================")
print("RESULT SUMMARY")
print("==============================")

if same_a:
    print(f"Tiger A average: {sum(same_a)/len(same_a):.4f}")

if same_b:
    print(f"Tiger B average: {sum(same_b)/len(same_b):.4f}")

if different_scores:
    print(f"Different tiger average: {sum(different_scores)/len(different_scores):.4f}")

if duplicates_found:
    print(
        "\nNOTE: results above include byte-identical duplicate file pairs "
        "and are not a valid Re-ID evaluation until those duplicates are "
        "replaced with real, distinct photos (see DATASET INTEGRITY CHECK)."
    )

print("\nTest completed!")