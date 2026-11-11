"""Optional CPU garment/background mask; first use downloads an external model."""
from functools import lru_cache

from PIL import Image

CLOTHES = {4, 5, 6, 7, 8, 17}  # Upper clothes, skirt, pants, dress, belt, scarf
BACKGROUND = {0}
MODEL = "mattmdjaga/segformer_b2_clothes"


@lru_cache(maxsize=1)
def load():
    try:
        from transformers import AutoImageProcessor, SegformerForSemanticSegmentation
        import torch
    except ImportError as exc:
        raise RuntimeError("Install requirements-ai.txt to use automatic selection.") from exc
    processor = AutoImageProcessor.from_pretrained(MODEL)
    model = SegformerForSemanticSegmentation.from_pretrained(MODEL).eval().cpu()
    return processor, model, torch


def suggest_mask(image: Image.Image, target: str):
    if target not in ("clothes", "background"):
        raise ValueError("Select 'clothes' or 'background'.")
    processor, model, torch = load()
    with torch.inference_mode():
        pixels = processor(images=image.convert("RGB"), return_tensors="pt")["pixel_values"]
        logits = model(pixel_values=pixels).logits
        labels = torch.nn.functional.interpolate(
            logits, size=image.size[::-1], mode="bilinear", align_corners=False
        ).argmax(dim=1)[0]
        chosen = CLOTHES if target == "clothes" else BACKGROUND
        mask = torch.zeros_like(labels, dtype=torch.uint8)
        for label in chosen:
            mask = mask | (labels == label).to(torch.uint8)
    return Image.fromarray(mask.numpy() * 255, mode="L")
