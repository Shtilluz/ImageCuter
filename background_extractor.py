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


def _looks_like_product_photo(bgr, foreground, background):
    """Conservatively opt into photo segmentation for one large, continuous-tone subject."""
    if min(bgr.shape[:2]) < 256 or background.min() < 220 or np.ptp(background) > 18:
        return False
    fraction = np.mean(foreground)
    if not .02 < fraction < .8:
        return False
    sample = bgr[::max(1, bgr.shape[0] // 100), ::max(1, bgr.shape[1] // 100)]
    if len(np.unique((sample // 4).reshape(-1, 3), axis=0)) < 256:
        return False
    _, _, stats, _ = cv2.connectedComponentsWithStats(foreground.astype(np.uint8), connectivity=8)
    return len(stats) > 1 and stats[1:, cv2.CC_STAT_AREA].max() >= foreground.sum() * .9


def _refine_photo_contour(bgr, alpha, background):
    """Snap the coarse silhouette to full-resolution edges, including pale ones.

    Search only a narrow band around each contour. A cyclic dynamic program
    favours a continuous edge with background outside it, rather than isolated
    JPEG blocks or a stronger line inside a pale rim. Rasterize at 4x for coverage.
    """
    blurred = cv2.GaussianBlur(bgr.astype(np.float32), (5, 5), .8)
    difference = _color_distance(blurred, background)
    contours, _ = cv2.findContours((alpha > 127).astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_NONE)
    if not contours:
        return alpha
    result = np.zeros_like(alpha)
    radius = max(6, min(24, round(max(alpha.shape) * .01)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
    transition = .035 * (offsets[:, None] - offsets[None, :]) ** 2
    for contour in contours:
        raw = contour[:, 0, :].astype(np.float32)
        if len(raw) < 20:
            cv2.drawContours(result, [contour], -1, 255, cv2.FILLED)
            continue
        closed = np.vstack((raw, raw[:1]))
        distance = np.r_[0, np.cumsum(np.linalg.norm(np.diff(closed, axis=0), axis=1))]
        ticks = np.linspace(0, distance[-1], max(20, min(4096, round(distance[-1] / 2))), endpoint=False)
        points = np.column_stack([np.interp(ticks, distance, closed[:, k]) for k in range(2)]).astype(np.float32)
        tangent = np.roll(points, -3, axis=0) - np.roll(points, 3, axis=0)
        normals = np.column_stack((-tangent[:, 1], tangent[:, 0]))
        normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], .001)
        if cv2.contourArea(contour, oriented=True) > 0:
            normals = -normals
        coordinates = points[:, None, :] + offsets[None, :, None] * normals[:, None, :]
        def sample(delta):
            positions = coordinates + delta * normals[:, None, :]
            return cv2.remap(difference, positions[:, :, 0], positions[:, :, 1], cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REPLICATE)
        inside = np.maximum.reduce([sample(-d) for d in (1, 2, 3, 4)])
        outside = np.mean([sample(d) for d in (2, 3, 4)], axis=0)
        contrast = np.maximum(inside - outside, 0)
        quality = contrast / (inside + outside + 3) * np.tanh(contrast / 3) / (1 + outside / 4)
        score = quality - .0015 * offsets[None, :] ** 2
        # The image boundary is a crop, not evidence of background beyond it.
        anchored = ((points[:, 0] < 1) | (points[:, 0] > alpha.shape[1] - 2) |
                    (points[:, 1] < 1) | (points[:, 1] > alpha.shape[0] - 2))
        score[anchored[:, None] & (offsets[None, :] != 0)] = -1e9
        def trace(start=None):
            previous = score[0].copy()
            if start is not None:
                previous.fill(-1e9)
                previous[start] = score[0, start]
            back = np.zeros(score.shape, np.int16)
            for index in range(1, len(points)):
                paths = previous[:, None] - transition
                back[index] = paths.argmax(axis=0)
                previous = score[index] + paths.max(axis=0)
            indices = np.empty(len(points), np.int32)
            indices[-1] = np.argmax(previous if start is None else previous - transition[:, start])
            for index in range(len(points) - 1, 0, -1):
                indices[index - 1] = back[index, indices[index]]
            return indices
        chosen = trace()
        chosen = trace(chosen[0])  # close the seam with the same smoothness cost
        adjusted = points + offsets[chosen, None] * normals
        adjusted = (np.roll(adjusted, 2, axis=0) + 4 * np.roll(adjusted, 1, axis=0) +
                    6 * adjusted + 4 * np.roll(adjusted, -1, axis=0) + np.roll(adjusted, -2, axis=0)) / 16
        adjusted[anchored] = points[anchored]
        x0, y0 = np.maximum(0, np.floor(adjusted.min(axis=0) - 2)).astype(int)
        x1, y1 = np.minimum(alpha.shape[::-1], np.ceil(adjusted.max(axis=0) + 3)).astype(int)
        if x0 >= x1 or y0 >= y1:
            continue
        high = np.zeros(((y1 - y0) * 4, (x1 - x0) * 4), np.uint8)
        cv2.fillPoly(high, [np.rint((adjusted - [x0, y0]) * 4).astype(np.int32)], 255)
        coverage = cv2.resize(high, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        result[y0:y1, x0:x1] = np.maximum(result[y0:y1, x0:x1], coverage)
    result[0], result[-1] = alpha[0], alpha[-1]
    result[:, 0], result[:, -1] = alpha[:, 0], alpha[:, -1]
    return result


def extract_photo_foreground(image, tolerance=10, background_rgb=None, marks=None):
    """Separate a photographed product by colour models and a coherent silhouette.

    Work at a bounded resolution to suppress JPEG noise and broad, soft shadows.
    Unlike colour keying, uncertain pixels on BOTH sides of the initial contour
    may change class. Fill the silhouette to preserve pale glass and labels.
    Explicit photo mode resegments RGB, including previously cut-out PNGs.
    """
    bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image[:, :, :3]
    height, width = bgr.shape[:2]
    scale = min(1., 768 / max(height, width))
    small = cv2.resize(bgr, (max(1, round(width * scale)), max(1, round(height * scale))),
                       interpolation=cv2.INTER_AREA) if scale < 1 else np.ascontiguousarray(bgr)
    coarse = extract_foreground(small, tolerance, background_rgb, "solid", allow_photo=False)
    visible = (coarse[:, :, 3] > 0).astype(np.uint8)
    def fallback():
        return extract_foreground(image, tolerance, background_rgb, "solid", marks, allow_photo=False)
    if not visible.any() or visible.all():
        return fallback()
    distance = cv2.distanceTransform(visible, cv2.DIST_L2, 5)
    color = _border_color(small) if background_rgb is None else np.asarray(background_rgb[::-1])
    difference = _color_distance(small, color)
    labels = np.where(visible, cv2.GC_PR_FGD, cv2.GC_PR_BGD).astype(np.uint8)
    labels[cv2.dilate(visible, np.ones((17, 17), np.uint8)) == 0] = cv2.GC_BGD
    labels[(distance > 8) & (difference > max(25, tolerance))] = cv2.GC_FGD
    if marks is not None:
        small_marks = cv2.resize(marks, small.shape[1::-1], interpolation=cv2.INTER_NEAREST)
        labels[small_marks == 1] = cv2.GC_FGD
        labels[small_marks == 2] = cv2.GC_BGD
    try:
        # K-means initialization must not change the result on repeated saves.
        cv2.setRNGSeed(0)
        cv2.grabCut(small, labels, None, np.zeros((1, 65), np.float64),
                    np.zeros((1, 65), np.float64), 3, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return fallback()
    mask = ((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD)).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask.fill(0)
    minimum = max(4, mask.size * .00005)
    for contour in contours:
        if cv2.contourArea(contour) >= minimum:
            cv2.drawContours(mask, [contour], -1, 1, cv2.FILLED)
    radius = max(1, round(min(small.shape[:2]) * .006))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1,) * 2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    coverage = cv2.resize(mask.astype(np.float32), (width, height), interpolation=cv2.INTER_LINEAR)
    coverage = cv2.GaussianBlur(coverage, (3, 3), .5)
    result = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    result[:, :, 3] = _refine_photo_contour(bgr, np.rint(coverage * 255).astype(np.uint8), color)
    return apply_marks(result, np.full((height, width), 255, np.uint8), marks)


def extract_foreground(image, tolerance=10, background_rgb=None, mode="auto", marks=None, allow_photo=True):
    """Return a BGRA copy; remove matching regions reachable from any edge.

    Enclosed regions are kept, even when their colour matches the background.
    Existing alpha is authoritative in automatic mode. Explicit colour selection
    also allows removing a background from an image that already has alpha.
    """
    if mode == "photo" and allow_photo:
        return extract_photo_foreground(image, tolerance, background_rgb, marks)
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
    if (allow_photo and mode == "auto" and background_rgb is None and model is None and
            _looks_like_product_photo(bgr, ~background, color)):
        return extract_photo_foreground(image, tolerance, marks=marks)
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
    # Photo matting already supplies partial coverage. Those pixels still have
    # the source backdrop baked into RGB, even when smoothing leaves alpha alone.
    band = (alpha > 0) & (alpha < 255)
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


def background_difference(bgr, background_rgb=None, mode="auto", tolerance=10):
    """Per-pixel distance to the modelled backdrop (checker, colour or border)."""
    model = (checkerboard_model(bgr, tolerance) if mode == "checker" or
             (mode == "auto" and background_rgb is None) else None)
    if model is not None:
        colors, pattern = model
        difference = _color_distance(bgr, colors[0])
        other = _color_distance(bgr, colors[1])
        np.copyto(difference, other, where=pattern == 1)
        return difference
    color = (_border_color(bgr) if background_rgb is None
             else np.asarray(background_rgb[::-1], dtype=np.float32))
    return _color_distance(bgr, color)


def cleanup_faint_residue(rgba, image=None, background_rgb=None, mode="auto",
                          tolerance=10, floor=8, marks=None):
    """Remove barely-visible leftovers that background removal left behind.

    Drops connected components whose peak alpha stays below `floor`, stray
    faint pixels away from visible bodies, and — when `image` is given — tiny
    specks whose contrast to the modelled backdrop is negligible. Protected
    brush marks and native source transparency are never touched.
    """
    if floor <= 0:
        return rgba
    result = rgba.copy()
    alpha = result[:, :, 3]
    protected = (marks == 1) if marks is not None else np.zeros(alpha.shape, bool)
    positive = alpha > 0
    if not positive.any():
        return result
    difference = None
    if image is not None and mode != "alpha":
        bgr = (cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2
               else image[:, :, :3])
        difference = background_difference(bgr, background_rgb, mode, tolerance)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(positive.astype(np.uint8),
                                                               connectivity=8)
    dropped = np.zeros(alpha.shape, bool)
    for label in range(1, count):
        x, y, w, h = stats[label, :4]
        piece = labels[y:y+h, x:x+w] == label
        window = alpha[y:y+h, x:x+w]
        drop_piece = None
        if int(window[piece].max()) < floor:
            drop_piece = piece
        elif difference is not None and w * h <= 48:
            contrast = difference[y:y+h, x:x+w]
            if float(contrast[piece].max()) <= tolerance + 6:
                drop_piece = piece
        if drop_piece is not None:
            keep_piece = protected[y:y+h, x:x+w]
            dropped[y:y+h, x:x+w] |= drop_piece & ~keep_piece
    if dropped.any():
        result[dropped, 3] = 0
        alpha = result[:, :, 3]
        positive = alpha > 0
    # Faint halo pixels away from any visible body are residue too.
    solid = (alpha >= floor) & ~protected
    if solid.any():
        near = cv2.dilate(solid.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        stray = positive & ~near & ~protected
        result[stray, 3] = 0
    return result


def _separation_seeds(component, radius):
    """Seed cores for splitting touching sprites inside one connected blob.

    Levels step from `radius` down to 1 px: a bulb keeps its own seed when any
    level disconnects it from the cores already found. Small objects therefore
    survive next to large ones even where a single global erosion would erase
    them entirely.
    """
    dist = cv2.distanceTransform(component.astype(np.uint8), cv2.DIST_L2, 5)
    seeds = np.zeros(component.shape, np.uint8)
    top = int(min(radius, dist.max()))
    if top < 1:
        return seeds
    fine_top = min(top, 24)
    levels = list(range(top, fine_top, -max(1, (top - fine_top) // 12 or 1)))
    levels += list(range(fine_top, 0, -1))
    for level in levels:
        count, labels = cv2.connectedComponents((dist >= level).astype(np.uint8),
                                                connectivity=8)
        for label in range(1, count):
            cand = labels == label
            if seeds[cand].any():
                continue
            seeds[cand] = 1
    return seeds


def _attach_leftovers(regions, binary, geometry):
    """Give backdrop-coloured pixels (eyes, gaps) to the object that owns them.

    A leftover blob that touches exactly one region is absorbed into it; one
    wedged between several regions is a gap and stays out of every sprite.
    """
    index = np.zeros(binary.shape, np.int32)
    for i, (x, y, w, h, mask) in enumerate(regions, 1):
        index[y:y+h, x:x+w][mask.astype(bool)] = i
    leftover = ((binary > 0) & (geometry == 0) & (index == 0)).astype(np.uint8)
    if not leftover.any() or not regions:
        return regions
    count, labels, stats, _ = cv2.connectedComponentsWithStats(leftover)
    cents = []
    for x, y, w, h, mask in regions:
        ys, xs = np.nonzero(mask)
        cents.append((float(x + xs.mean()), float(y + ys.mean())) if xs.size
                     else (x + w / 2.0, y + h / 2.0))
    kernel = np.ones((3, 3), np.uint8)
    for i in range(1, count):
        x, y, w, h = stats[i, :4]
        piece = labels[y:y+h, x:x+w] == i
        near = cv2.dilate(piece.astype(np.uint8), kernel).astype(bool)
        owners = {int(o) for o in np.unique(index[y:y+h, x:x+w][near]) if o > 0}
        if len(owners) == 1:
            owner = owners.pop()
        elif len(owners) > 1:
            continue
        else:
            ys, xs = np.nonzero(piece)
            cy, cx = y + ys.mean(), x + xs.mean()
            owner = min(range(1, len(regions) + 1),
                        key=lambda k: (cents[k - 1][0] - cx) ** 2 + (cents[k - 1][1] - cy) ** 2)
        index[y:y+h, x:x+w][piece] = owner
    rebuilt = []
    for i in range(1, len(regions) + 1):
        mask = index == i
        points = cv2.findNonZero(mask.astype(np.uint8))
        if points is None:
            continue
        bx, by, bw, bh = cv2.boundingRect(points)
        rebuilt.append((bx, by, bw, bh, mask[by:by+bh, bx:bx+bw].copy()))
    return rebuilt


def sprite_regions(alpha, min_size=1, separate=0, group_gap=0, single=False,
                   visibility=8, bulk=None):
    """Return tight (x, y, w, h, mask) regions without neighbouring sprite pixels.

    Morphology affects detection only. Original alpha, faint edges and thin
    details are preserved. Separation assigns pixels to the nearest surviving
    seed within each original component instead of clipping expanded rectangles.
    Components whose peak alpha stays below `visibility` count as barely-visible
    background residue and are dropped from detection. `bulk` (optional 0/1
    mask) marks pixels that carry object colour: backdrop-coloured holes and
    gaps are excluded from split geometry and later attached to their owner, so
    grid cells on a solid background separate instead of fusing into one blob.
    """
    binary = (alpha > 0).astype(np.uint8)
    if not binary.any():
        return []
    if visibility > 0:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        for label in range(1, count):
            x, y, w, h = stats[label, :4]
            piece = labels[y:y+h, x:x+w] == label
            if int(alpha[y:y+h, x:x+w][piece].max()) < visibility:
                binary[y:y+h, x:x+w][piece] = 0
        if not binary.any():
            return []
    geometry = binary
    if bulk is not None:
        hollow = binary & (np.asarray(bulk) > 0).astype(np.uint8)
        if hollow.any():
            geometry = hollow
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
        working = cv2.dilate(geometry, kernel)
    else:
        working = geometry
    count, labels, stats, _ = cv2.connectedComponentsWithStats(working, connectivity=8)
    for label in range(1, count):
        x, y, w, h = stats[label, :4]
        if w < min_size or h < min_size:
            continue
        component = (labels[y:y+h, x:x+w] == label) & (geometry[y:y+h, x:x+w] > 0)
        if separate <= 0 or group_gap > 0:
            add(component, int(x), int(y))
            continue
        seeds = _separation_seeds(component, float(separate))
        seed_count, _ = cv2.connectedComponents(seeds, connectivity=8)
        if seed_count <= 2:
            add(component, int(x), int(y))
        else:
            _, nearest = cv2.distanceTransformWithLabels(1 - seeds, cv2.DIST_L2, 5,
                                                        labelType=cv2.DIST_LABEL_CCOMP)
            for seed in range(1, seed_count):
                add(component & (nearest == seed), int(x), int(y))
    if geometry is not binary:
        regions = _attach_leftovers(regions, binary, geometry)
    return sorted(regions, key=lambda r: (r[1], r[0]))


# ══════════════════════════════════════════════════════════════════
#  AUTOMATIC DETECTION PARAMETERS
# ══════════════════════════════════════════════════════════════════

def _junk_count(regions):
    """Regions that look like debris rather than objects."""
    if len(regions) < 2:
        return 0
    areas = sorted(max(1, int(mask.sum())) for _, _, _, _, mask in regions)
    median = areas[len(areas) // 2]
    largest = areas[-1]
    junk = 0
    for x, y, w, h, mask in regions:
        area = max(1, int(mask.sum()))
        fill = area / float(max(1, w * h))
        if area < max(2, 0.05 * median) and area < 0.02 * largest:
            junk += 1
        elif min(w, h) <= 2 and fill < 0.12:
            junk += 1
    return junk


def _adjacent_label_pairs(labels):
    h, w = labels.shape[:2]
    pairs = set()
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a = labels[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
        b = labels[max(0, dy):h - max(0, -dy), max(0, dx):w - max(0, -dx)]
        touch = (a > 0) & (b > 0) & (a != b)
        pairs.update(zip(a[touch].tolist(), b[touch].tolist()))
    return pairs


def _bogus_split_count(alpha, regions, split_ratio=0.45):
    """Adjacent pieces that a neck-versus-thickness test calls one object.

    A cut only counts when the connecting neck is clearly narrower than the
    pieces it joins; halves of a starfish stay together, a tiny object on a
    huge body still splits off.
    """
    if len(regions) < 2:
        return 0
    h, w = alpha.shape[:2]
    labels = np.zeros((h, w), np.int32)
    for i, (x, y, rw, rh, mask) in enumerate(regions, start=1):
        labels[y:y+rh, x:x+rw][mask.astype(bool)] = i
    dist = cv2.distanceTransform((labels > 0).astype(np.uint8), cv2.DIST_L2, 5)
    peak = np.zeros(len(regions) + 1, np.float32)
    for i in range(1, len(regions) + 1):
        m = labels == i
        if m.any():
            peak[i] = float(dist[m].max())
    kernel = np.ones((3, 3), np.uint8)
    bogus = 0
    for a, b in _adjacent_label_pairs(labels):
        ma = labels == a
        mb = labels == b
        near_a = cv2.dilate(ma.astype(np.uint8), kernel).astype(bool) & mb
        near_b = cv2.dilate(mb.astype(np.uint8), kernel).astype(bool) & ma
        saddle = 0.0
        if near_a.any():
            saddle = max(saddle, float(dist[near_a].max()))
        if near_b.any():
            saddle = max(saddle, float(dist[near_b].max()))
        if saddle >= split_ratio * min(peak[a], peak[b]):
            bogus += 1
    return bogus


def _min_size_candidates(regions, limit=4):
    if not regions:
        return [1, 3]
    areas = sorted(max(1, int(mask.sum())) for _, _, _, _, mask in regions)
    candidates = {1, 3}
    med = areas[len(areas) // 2]
    candidates.add(int(max(1, round(med ** 0.5 * 0.2))))
    if len(areas) >= 4:
        low = areas[:max(3, len(areas) * 3 // 4)]
        best_ratio, gap_at = 1.0, None
        for a, b in zip(low, low[1:]):
            ratio = b / float(max(1, a))
            if ratio > best_ratio:
                best_ratio, gap_at = ratio, b
        if gap_at is not None and best_ratio >= 3.0:
            candidates.add(int(max(1, round(gap_at ** 0.5 * 0.35))))
    return sorted(c for c in candidates if 1 <= c <= 64)[:limit]


def tune_detection(alpha, group_gap=0, single=False, max_side=512, bulk=None):
    """Search min_size/separate values that split `alpha` into clean objects.

    The search runs on a downsampled copy and returns full-resolution values.
    Scoring rewards real objects, penalises debris and treats a cut as bogus
    when the neck is not clearly narrower than the pieces it joins.
    """
    h, w = alpha.shape[:2]
    factor = max(1, int(np.ceil(max(h, w) / float(max_side))))
    if factor == 1:
        small = alpha
        small_bulk = bulk
    else:
        size = (max(1, w // factor), max(1, h // factor))
        small = cv2.resize(alpha, size, interpolation=cv2.INTER_NEAREST)
        small_bulk = (None if bulk is None else
                      cv2.resize(np.asarray(bulk, np.uint8), size, interpolation=cv2.INTER_NEAREST))
    base = sprite_regions(small, 1, 0, group_gap, single, bulk=small_bulk)
    sep_ladder = (0,) if single else (0, 1, 2, 3, 4, 6, 9, 14)
    best = None
    for ms in _min_size_candidates(base):
        for sep in sep_ladder:
            regions = sprite_regions(small, ms, sep, group_gap, single, bulk=small_bulk)
            n = len(regions)
            junk = _junk_count(regions)
            bogus = _bogus_split_count(small, regions)
            effective = n - bogus - junk
            score = (-effective, junk, bogus, sep, ms)
            if best is None or score < best[0]:
                best = (score, ms, sep, n, junk)
    if best is None:
        return {"min_size": 3, "separate": 0, "cell": 64, "cols": 8,
                "count": 0, "junk": 0}
    _, ms, sep, _, junk = best
    min_size = max(1, ms * factor)
    separate = max(0, sep * factor)
    regions = sprite_regions(alpha, min_size, separate, group_gap, single, bulk=bulk)
    count = len(regions)
    maxdim = max((max(r[2], r[3]) for r in regions), default=64)
    cell = int(min(2048, max(16, -(-maxdim // 16) * 16)))
    cols = max(1, int(round(count ** 0.5))) if count else 1
    return {"min_size": min_size, "separate": separate, "cell": cell,
            "cols": cols, "count": count, "junk": junk}


def _tolerance_candidates(image, current, background_rgb, mode, limit=4):
    guess = 10
    try:
        bgr = (cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2
               else image[:, :, :3])
        border = np.concatenate((bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]))
        color = (_border_color(bgr) if background_rgb is None
                 else np.asarray(background_rgb[::-1], dtype=np.float32))
        distances = _color_distance(border[:, None, :], color[None, None, :])
        flat = np.sort(distances.ravel())
        guess = int(max(3, min(60, flat[int(len(flat) * 0.9)] + 4)))
    except Exception:
        pass
    values = [current, guess]
    if mode != "photo":
        values += [6, 14, 28]
    seen, out = set(), []
    for value in values:
        value = int(max(0, min(100, value)))
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out[:limit]


def detection_bulk(image, background_rgb=None, mode="auto", tolerance=10, marks=None):
    """Mask of pixels that carry object colour rather than backdrop colour.

    Backdrop-coloured holes (eyes on a matching background, gaps between grid
    cells) are excluded so object splitting sees real silhouettes. Returns None
    when no backdrop was removed and every visible pixel counts.
    """
    if image is None or mode == "alpha":
        return None
    native_alpha = (image.ndim == 3 and image.shape[2] == 4 and
                    bool(np.any(image[:, :, 3] < 255)))
    if background_rgb is None and mode == "auto" and native_alpha:
        return None
    bgr = (cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2
           else image[:, :, :3])
    difference = background_difference(bgr, background_rgb, mode, tolerance)
    bulk = (difference > max(2, tolerance // 2)).astype(np.uint8)
    if marks is not None:
        bulk[marks == 1] = 1
    return bulk


def auto_detect_params(image, tolerance=10, background_rgb=None, mode="auto",
                       marks=None, allow_photo=True, single=False, group_gap=0):
    """Pick background tolerance and separation so objects split cleanly.

    Returns a dict with keys tolerance, min_size, separate, cell, cols, count.
    """
    result = {"tolerance": tolerance, "min_size": 3, "separate": 0,
              "cell": 64, "cols": 8, "count": 0, "junk": 0}
    best = None
    for tol in _tolerance_candidates(image, tolerance, background_rgb, mode):
        rgba = extract_foreground(image, tol, background_rgb, mode, marks, allow_photo)
        rgba = cleanup_faint_residue(rgba, image, background_rgb, mode, tol, 8, marks)
        alpha = rgba[:, :, 3]
        if not (alpha > 0).any():
            continue
        bulk = detection_bulk(image, background_rgb, mode, tol, marks)
        pick = tune_detection(alpha, group_gap=group_gap, single=single, bulk=bulk)
        score = (-pick["count"], pick["junk"], abs(tol - tolerance), tol)
        if best is None or score < best[0]:
            best = (score, tol, pick)
    if best is not None:
        _, tol, pick = best
        result.update(pick)
        result["tolerance"] = tol
    return result
