"""Deterministic edits. Every pixel outside the selection is preserved exactly."""
from PIL import Image, ImageChops, ImageColor


def mask_binary(mask: Image.Image, size: tuple[int, int]):
    """White=edit, black=protect. Hard edges guarantee unchanged outside pixels."""
    return mask.convert("L").resize(size, Image.Resampling.NEAREST).point(lambda value: 255 if value >= 128 else 0)


def preserve_unmasked(original: Image.Image, edited: Image.Image, mask: Image.Image):
    original = original.convert("RGB")
    edited = edited.convert("RGB").resize(original.size, Image.Resampling.LANCZOS)
    return Image.composite(edited, original, mask_binary(mask, original.size))


def recolor(original: Image.Image, mask: Image.Image, color: str):
    original = original.convert("RGB")
    target = ImageColor.getrgb(color)
    target_h, target_s, _ = Image.new("RGB", (1, 1), target).convert("HSV").getpixel((0, 0))
    current_h, current_s, value = original.convert("HSV").split()
    changed = Image.merge("HSV", (
        Image.new("L", original.size, target_h),
        Image.blend(current_s, Image.new("L", original.size, target_s), 0.75),
        value,
    )).convert("RGB")
    return preserve_unmasked(original, changed, mask)


def fill(original: Image.Image, mask: Image.Image, color: str):
    original = original.convert("RGB")
    return preserve_unmasked(original, Image.new("RGB", original.size, ImageColor.getrgb(color)), mask)


def erase(original: Image.Image, mask: Image.Image):
    """Transparent selection. Original RGB information is retained elsewhere."""
    rgba = original.convert("RGBA")
    rgba.putalpha(ImageChops.subtract(Image.new("L", rgba.size, 255), mask_binary(mask, rgba.size)))
    return rgba
