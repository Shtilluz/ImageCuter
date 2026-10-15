"""Conservative, border-connected background removal for sprite sheets."""

import cv2
import numpy as np
from collections import Counter


def _color_distance(bgr, color):
    distance = np.zeros(bgr.shape[:2], np.float32)
    for channel in range(3):
        delta = bgr[:, :, channel].astype(np.float32)
        delta -= color[channel]
        np.abs(delta, out=delta)
        np.maximum(distance, delta, out=distance)
    return distance


def _border_color(bgr):
    # Vote for a colour group rather than trusting a single corner pixel.
    border = np.concatenate((bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]))
    groups = border.astype(np.int32) // 16
    keys = groups[:, 0] * 256 + groups[:, 1] * 16 + groups[:, 2]
    winner = np.bincount(keys, minlength=4096).argmax()
    return np.median(border[keys == winner], axis=0)


def _checker_axis(lines, colors, tolerance):
    best = None
    for line in lines:
        distances = np.max(np.abs(line[:, None, :].astype(np.float32) - colors), axis=2)
        labels = distances.argmin(axis=1)
        valid = distances.min(axis=1) <= tolerance
        transitions = np.flatnonzero(valid[1:] & valid[:-1] & (labels[1:] != labels[:-1])) + 1
        if len(transitions) < 3 or valid.mean() < .65:
            continue
        widths = np.diff(transitions)
        for width, _ in Counter(int(w) for w in widths if 2 <= w <= 256).most_common(5):
            offset = Counter(int(-t % width) for t in transitions).most_common(1)[0][0]
            parity = ((np.arange(len(line)) + offset) // width) % 2
            match = np.mean(parity[valid] == labels[valid])
            score = max(match, 1 - match)
            if score >= .94 and (best is None or score > best[0]):
                best = (score, width, offset)
    return None if best is None else best[1:]


def checkerboard_model(bgr, tolerance=10):
    """Fit two colours AND their regular spatial pattern; never key two colours globally."""
    h, w = bgr.shape[:2]
    if min(h, w) < 8:
        return None
    border = np.concatenate((bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]))
    first = _border_color(bgr)
    far = np.max(np.abs(border.astype(np.float32) - first), axis=1) > max(12, tolerance * 2)
    if not .15 < far.mean() < .85:
        return None
    samples = border[far]
    groups = samples.astype(np.int32) // 16
    keys = groups[:, 0] * 256 + groups[:, 1] * 16 + groups[:, 2]
    winner = np.bincount(keys, minlength=4096).argmax()
    second = np.median(samples[keys == winner], axis=0)
    colors = np.array((first, second), dtype=np.float32)
    tol = max(3, tolerance)
    x_axis = _checker_axis((bgr[0], bgr[-1]), colors, tol)
    y_axis = _checker_axis((bgr[:, 0], bgr[:, -1]), colors, tol)
    if x_axis is None or y_axis is None:
        return None
    cw, ox = x_axis
    ch, oy = y_axis
    px = (((np.arange(w) + ox) // cw) % 2).astype(np.uint8)
    py = (((np.arange(h) + oy) // ch) % 2).astype(np.uint8)
    pattern = (px[None, :] + py[:, None]) % 2
    edge_pattern = np.concatenate((pattern[0], pattern[-1], pattern[:, 0], pattern[:, -1]))
    distances = np.max(np.abs(border[:, None, :].astype(np.float32) - colors), axis=2)
    valid = distances.min(axis=1) <= tol
    if valid.mean() < .75:
        return None
    match = np.mean(edge_pattern[valid] == distances.argmin(axis=1)[valid])
    if max(match, 1 - match) < .94:
        return None
    if match < .5:
        pattern = 1 - pattern
    return colors, pattern


def extract_foreground(image, tolerance=10, background_rgb=None, mode="auto", marks=None):
    """Return a BGRA copy; remove matching regions reachable from any edge.

    Enclosed regions are kept, even when their colour matches the background.
    Existing alpha is authoritative in automatic mode. Explicit colour selection
    also allows removing a background from an image that already has alpha.
    """
    if image.ndim == 2:
        rgba = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    elif image.shape[2] == 3:
        rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    else:
        rgba = image.copy()
    original_alpha = rgba[:, :, 3].copy()
    if mode == "alpha" or (background_rgb is None and mode == "auto" and np.any(original_alpha < 255)):
        return apply_marks(rgba, original_alpha, marks)

    bgr = rgba[:, :, :3]
    model = (checkerboard_model(bgr, tolerance) if mode == "checker" or
             (mode == "auto" and background_rgb is None) else None)
    if mode == "checker" and model is None:
        # An irregular painted checkerboard is ambiguous; keep the image for
        # manual correction rather than erasing both colours everywhere.
        return apply_marks(rgba, original_alpha, marks)
    if model is not None:
        colors, pattern = model
        difference = _color_distance(bgr, colors[0])
        other = _color_distance(bgr, colors[1])
        np.copyto(difference, other, where=pattern == 1)
    else:
        color = (_border_color(bgr) if background_rgb is None
                 else np.asarray(background_rgb[::-1], dtype=np.float32))
        difference = _color_distance(bgr, color)
    candidates = (difference <= max(0, min(255, tolerance))) | (rgba[:, :, 3] == 0)
    if marks is not None:
        candidates[marks == 1] = False
    # One padded outside region seeds every edge. Four-way connectivity avoids
    # leaking diagonally through a one-pixel outline in pixel art.
    reachable = np.pad(candidates.astype(np.uint8), 1, constant_values=1)
    cv2.floodFill(reachable, None, (0, 0), 2, flags=4)
    background = reachable[1:-1, 1:-1] == 2
    # With no contrast, automatic inference cannot distinguish a solid sprite
    # from its background. Preserve it; an explicit colour can remove it all.
    if background_rgb is None and mode == "auto" and model is None and background.all():
        return apply_marks(rgba, original_alpha, marks)
    rgba[background, 3] = 0
    return apply_marks(rgba, original_alpha, marks)


def apply_marks(rgba, original_alpha, marks):
    if marks is not None:
        rgba[marks == 1, 3] = original_alpha[marks == 1]
        rgba[marks == 2, 3] = 0
    return rgba


def smooth_cutout_edges(image, rgba, background_rgb=None, mode="auto", marks=None, choke=0, tolerance=10):
    """Soften a cutout and unmix its backdrop in a narrow boundary band.

    This estimates edge coverage, not transparency inside glass or reflections.
    Native source alpha and protected brush pixels remain authoritative. Choke
    is an explicit inward trim; zero keeps thin details and the original bounds.
    All colour arithmetic uses the source's BGR order and straight alpha.
    """
    result = rgba.copy()
    if image.ndim == 3 and image.shape[2] == 4 and np.any(image[:, :, 3] < 255):
        return result
    visible = rgba[:, :, 3] > 0
    if not visible.any() or visible.all():
        return result
    mask = visible.astype(np.uint8)
    choke = max(0, min(6, int(choke)))
    if choke:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (choke * 2 + 1,) * 2)
        # A cropped image edge is not evidence of background beyond the frame.
        mask = cv2.erode(mask, kernel, borderType=cv2.BORDER_CONSTANT, borderValue=1)
    coverage = cv2.GaussianBlur(mask.astype(np.float32), (5, 5), .65,
                                borderType=cv2.BORDER_REPLICATE)
    # Never grow a white fringe back into already removed background or holes.
    alpha = np.minimum(np.rint(coverage * 255).astype(np.uint8), rgba[:, :, 3])
    band = (alpha > 0) & (alpha < rgba[:, :, 3])
    bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image[:, :, :3]
    background = None
    if mode != "alpha":
        model = (checkerboard_model(bgr, tolerance) if mode == "checker" or
                 (mode == "auto" and background_rgb is None) else None)
        if model is not None:
            colors, pattern = model
            background = colors[pattern[band]]
        elif mode != "checker":
            background = (_border_color(bgr) if background_rgb is None else
                          np.asarray(background_rgb[::-1], dtype=np.float32))
    if background is not None and band.any():
        a = alpha[band, None].astype(np.float32) / 255
        # C = a*F + (1-a)*B. Feathering alpha alone leaves B baked into RGB.
        color = (bgr[band].astype(np.float32) - (1 - a) * background) / a
        result[band, :3] = np.rint(np.clip(color, 0, 255)).astype(np.uint8)
    result[:, :, 3] = alpha
    if marks is not None:
        result[marks == 1] = rgba[marks == 1]
        result[marks == 2, 3] = 0
    return result


def bleed_transparent_colors(rgba, radius=4):
    """Extend edge RGB into nearby zero-alpha pixels without changing alpha.

    Useful for filtered game textures: transparent corners/padding no longer
    retain the removed backdrop's colour. This does not unmix opaque JPEG edges.
    Input and output use the same channel order (RGBA or BGRA).
    """
    visible = rgba[:, :, 3] > 0
    if not visible.any() or visible.all():
        return rgba
    distance, labels = cv2.distanceTransformWithLabels((~visible).astype(np.uint8),
                                                      cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    fill = (~visible) & (distance <= radius)
    result = rgba.copy()
    colors = rgba[visible, :3]
    result[fill, :3] = colors[labels[fill] - 1]
    return result


def refine_foreground(image, rgba, marks=None, iterations=3):
    """Explicit GrabCut refinement, honouring keep/remove strokes and source alpha."""
    source = (cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA) if image.ndim == 2 else
              cv2.cvtColor(image, cv2.COLOR_BGR2BGRA) if image.shape[2] == 3 else image.copy())
    visible = rgba[:, :, 3] > 0
    if not visible.any() or visible.all():
        raise ValueError("Сначала отделите фон или отметьте кистями объект и фон.")
    labels = np.where(visible, cv2.GC_PR_FGD, cv2.GC_BGD).astype(np.uint8)
    if marks is not None:
        labels[marks == 1] = cv2.GC_FGD
        labels[marks == 2] = cv2.GC_BGD
    cv2.grabCut(np.ascontiguousarray(source[:, :, :3]), labels, None,
                np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64),
                iterations, cv2.GC_INIT_WITH_MASK)
    foreground = (labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD)
    result = source.copy()
    result[~foreground, 3] = 0
    return apply_marks(result, source[:, :, 3], marks)


def sprite_regions(alpha, min_size=1, separate=0, group_gap=0, single=False):
    """Return tight (x, y, w, h, mask) regions without neighbouring sprite pixels.

    Morphology affects detection only. Original alpha, faint edges and thin
    details are preserved. Separation assigns pixels to the nearest surviving
    seed within each original component instead of clipping expanded rectangles.
    """
    binary = (alpha > 0).astype(np.uint8)
    if not binary.any():
        return []
    regions = []

    def add(mask, x=0, y=0):
        points = cv2.findNonZero(mask.astype(np.uint8))
        if points is None:
            return
        bx, by, bw, bh = cv2.boundingRect(points)
        if single or (bw >= min_size and bh >= min_size):
            regions.append((x + bx, y + by, bw, bh, mask[by:by+bh, bx:bx+bw].copy()))

    if single:
        add(binary)
        return regions
    if group_gap > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (group_gap * 2 + 1,) * 2)
        working = cv2.dilate(binary, kernel)
    else:
        working = binary
    count, labels, stats, _ = cv2.connectedComponentsWithStats(working, connectivity=8)
    for label in range(1, count):
        x, y, w, h = stats[label, :4]
        if w < min_size or h < min_size:
            continue
        component = (labels[y:y+h, x:x+w] == label) & (binary[y:y+h, x:x+w] > 0)
        if separate <= 0 or group_gap > 0:
            add(component, int(x), int(y))
            continue
        eroded = cv2.erode(np.pad(component.astype(np.uint8), separate),
                           np.ones((separate * 2 + 1,) * 2, np.uint8))
        eroded = eroded[separate:-separate, separate:-separate]
        seed_count, _ = cv2.connectedComponents(eroded, connectivity=8)
        if seed_count <= 2:
            add(component, int(x), int(y))
        else:
            _, nearest = cv2.distanceTransformWithLabels(1 - eroded, cv2.DIST_L2, 5,
                                                        labelType=cv2.DIST_LABEL_CCOMP)
            for seed in range(1, seed_count):
                add(component & (nearest == seed), int(x), int(y))
    return sorted(regions, key=lambda r: (r[1], r[0]))
