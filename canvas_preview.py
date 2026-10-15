"""Bounded preview rendering: zoom never allocates the full enlarged image."""
from math import ceil, floor

from PIL import Image


def resize_region(image, scaled_size, box, resample=Image.Resampling.LANCZOS):
    """Render an integer region of a virtual resize, including filter support."""
    left, top, right, bottom = box
    sx, sy = image.width / scaled_size[0], image.height / scaled_size[1]
    source = (left * sx, top * sy, right * sx, bottom * sy)
    # Crop first: RGBA resize otherwise premultiplies the entire source, even
    # when Pillow's box parameter selects a small region at high zoom.
    support = 0 if resample == Image.Resampling.NEAREST else 3
    px, py = ceil(support * max(1, sx)), ceil(support * max(1, sy))
    crop = (max(0, floor(source[0]) - px), max(0, floor(source[1]) - py),
            min(image.width, ceil(source[2]) + px), min(image.height, ceil(source[3]) + py))
    part = image.crop(crop)
    source = (source[0] - crop[0], source[1] - crop[1],
              source[2] - crop[0], source[3] - crop[1])
    return part.resize((right - left, bottom - top), resample, box=source)


def viewport_region(scaled_size, origin, viewport):
    """Visible bounds in virtual image coordinates, or None when off screen."""
    w, h = scaled_size
    ox, oy = origin
    cw, ch = viewport
    box = (max(0, -ox), max(0, -oy), min(w, cw - ox), min(h, ch - oy))
    return box if box[2] > box[0] and box[3] > box[1] else None
