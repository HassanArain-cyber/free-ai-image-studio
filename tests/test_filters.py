from PIL import Image

from app import filters


def test_recolor_unselected_pixels_are_exact():
    original = Image.new("RGB", (16, 16), (100, 120, 160))
    mask = Image.new("L", (16, 16), 0)
    mask.putpixel((8, 8), 255)
    result = filters.recolor(original, mask, "#ff0000")
    assert result.getpixel((0, 0)) == original.getpixel((0, 0))
    assert result.getpixel((8, 8)) != original.getpixel((8, 8))


def test_erase_changes_only_alpha():
    original = Image.new("RGB", (8, 8), (20, 40, 60))
    mask = Image.new("L", (8, 8), 0)
    mask.putpixel((3, 4), 255)
    result = filters.erase(original, mask)
    assert result.getpixel((0, 0)) == (20, 40, 60, 255)
    assert result.getpixel((3, 4)) == (20, 40, 60, 0)


def test_hard_mask_ensures_unselected_pixels_unchanged():
    original = Image.new("RGB", (16, 16), "blue")
    generated = Image.new("RGB", (8, 8), "red")
    mask = Image.new("L", original.size, 0)
    mask.putpixel((5, 5), 255)
    result = filters.preserve_unmasked(original, generated, mask)
    assert result.getpixel((4, 5)) == original.getpixel((4, 5))
    assert result.getpixel((5, 5)) == (255, 0, 0)
