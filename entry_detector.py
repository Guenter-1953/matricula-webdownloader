import json
import os
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

from PIL import Image, ImageDraw, ImageEnhance, ImageOps


@dataclass
class EntryRegion:
    y1: int
    y2: int
    height: int
    pixel_count_sum: int


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


def load_image(image_path: str) -> Image.Image:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    return Image.open(image_path).convert("RGB")


def to_grayscale(image: Image.Image) -> Image.Image:
    return ImageOps.grayscale(image)


def enhance_contrast(image: Image.Image, factor: float = 2.0) -> Image.Image:
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def binarize_image(image: Image.Image, threshold: int = 170) -> Image.Image:
    return image.point(lambda p: 0 if p < threshold else 255, mode="L")


def compute_horizontal_projection(binary_image: Image.Image) -> List[int]:
    """
    Returns a list where each item is the number of dark pixels in that row.
    Assumes binary image with:
      0   = black/text
      255 = white/background
    """
    width, height = binary_image.size
    pixels = binary_image.load()

    projection = []
    for y in range(height):
        dark_count = 0
        for x in range(width):
            if pixels[x, y] == 0:
                dark_count += 1
        projection.append(dark_count)

    return projection


def smooth_projection(values: List[int], radius: int = 3) -> List[int]:
    if not values:
        return []

    smoothed = []
    n = len(values)

    for i in range(n):
        start = max(0, i - radius)
        end = min(n, i + radius + 1)
        window = values[start:end]
        smoothed.append(int(sum(window) / len(window)))

    return smoothed


def detect_vertical_text_regions(
    projection: List[int],
    min_dark_pixels_per_row: int = 25,
    min_region_height: int = 20,
    merge_gap: int = 12,
) -> List[EntryRegion]:
    """
    Detects vertical regions (y1..y2) where rows contain enough dark pixels.
    This is a first coarse segmentation step.
    """
    raw_regions: List[EntryRegion] = []

    in_region = False
    region_start = 0
    region_sum = 0

    for y, value in enumerate(projection):
        is_text_row = value >= min_dark_pixels_per_row

        if is_text_row and not in_region:
            in_region = True
            region_start = y
            region_sum = value
        elif is_text_row and in_region:
            region_sum += value
        elif not is_text_row and in_region:
            region_end = y - 1
            height = region_end - region_start + 1
            if height >= min_region_height:
                raw_regions.append(
                    EntryRegion(
                        y1=region_start,
                        y2=region_end,
                        height=height,
                        pixel_count_sum=region_sum,
                    )
                )
            in_region = False
            region_sum = 0

    if in_region:
        region_end = len(projection) - 1
        height = region_end - region_start + 1
        if height >= min_region_height:
            raw_regions.append(
                EntryRegion(
                    y1=region_start,
                    y2=region_end,
                    height=height,
                    pixel_count_sum=region_sum,
                )
            )

    if not raw_regions:
        return []

    merged_regions: List[EntryRegion] = []
    current = raw_regions[0]

    for nxt in raw_regions[1:]:
        gap = nxt.y1 - current.y2 - 1
        if gap <= merge_gap:
            current = EntryRegion(
                y1=current.y1,
                y2=nxt.y2,
                height=nxt.y2 - current.y1 + 1,
                pixel_count_sum=current.pixel_count_sum + nxt.pixel_count_sum,
            )
        else:
            merged_regions.append(current)
            current = nxt

    merged_regions.append(current)
    return merged_regions


def filter_regions_by_height(
    regions: List[EntryRegion],
    min_height: int = 28,
    max_height: Optional[int] = None,
) -> List[EntryRegion]:
    filtered = []
    for region in regions:
        if region.height < min_height:
            continue
        if max_height is not None and region.height > max_height:
            continue
        filtered.append(region)
    return filtered


def save_debug_binary_image(binary_image: Image.Image, output_path: str) -> None:
    _ensure_dir(os.path.dirname(output_path))
    binary_image.save(output_path)


def save_debug_boxes_image(
    original_image: Image.Image,
    regions: List[EntryRegion],
    output_path: str,
    left_margin: int = 0,
    right_margin: int = 0,
) -> None:
    _ensure_dir(os.path.dirname(output_path))

    debug_img = original_image.copy()
    draw = ImageDraw.Draw(debug_img)

    width, _ = debug_img.size
    x1 = _clamp(left_margin, 0, width - 1)
    x2 = _clamp(width - 1 - right_margin, 0, width - 1)

    for idx, region in enumerate(regions, start=1):
        draw.rectangle([x1, region.y1, x2, region.y2], outline="red", width=3)
        label = f"{idx:03d}"
        text_y = max(0, region.y1 - 18)
        draw.text((x1 + 5, text_y), label, fill="red")

    debug_img.save(output_path)


def save_projection_json(
    projection: List[int],
    smoothed_projection: List[int],
    output_path: str,
) -> None:
    _ensure_dir(os.path.dirname(output_path))
    payload = {
        "projection": projection,
        "smoothed_projection": smoothed_projection,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def regions_to_json_dict(
    image_path: str,
    image_size: tuple,
    regions: List[EntryRegion],
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    width, height = image_size
    return {
        "image_path": image_path,
        "image_width": width,
        "image_height": height,
        "entry_regions": [asdict(r) for r in regions],
        "settings": settings,
    }


def save_regions_json(
    image_path: str,
    image_size: tuple,
    regions: List[EntryRegion],
    settings: Dict[str, Any],
    output_path: str,
) -> None:
    _ensure_dir(os.path.dirname(output_path))
    payload = regions_to_json_dict(image_path, image_size, regions, settings)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def detect_entries_on_page(
    image_path: str,
    output_dir: Optional[str] = None,
    contrast_factor: float = 2.0,
    threshold: int = 170,
    projection_smoothing_radius: int = 3,
    min_dark_pixels_per_row: int = 25,
    min_region_height: int = 20,
    merge_gap: int = 12,
    filter_min_height: int = 28,
    filter_max_height: Optional[int] = None,
    left_margin: int = 0,
    right_margin: int = 0,
    save_debug: bool = True,
) -> Dict[str, Any]:
    """
    Step 1:
    - load page image
    - grayscale
    - enhance contrast
    - binarize
    - build horizontal projection
    - detect coarse vertical text regions
    - optionally save debug outputs

    Returns a dict with detected regions and metadata.
    """
    image = load_image(image_path)
    gray = to_grayscale(image)
    enhanced = enhance_contrast(gray, factor=contrast_factor)
    binary = binarize_image(enhanced, threshold=threshold)

    projection = compute_horizontal_projection(binary)
    smoothed_projection = smooth_projection(
        projection,
        radius=projection_smoothing_radius,
    )

    regions = detect_vertical_text_regions(
        projection=smoothed_projection,
        min_dark_pixels_per_row=min_dark_pixels_per_row,
        min_region_height=min_region_height,
        merge_gap=merge_gap,
    )

    regions = filter_regions_by_height(
        regions,
        min_height=filter_min_height,
        max_height=filter_max_height,
    )

    settings = {
        "contrast_factor": contrast_factor,
        "threshold": threshold,
        "projection_smoothing_radius": projection_smoothing_radius,
        "min_dark_pixels_per_row": min_dark_pixels_per_row,
        "min_region_height": min_region_height,
        "merge_gap": merge_gap,
        "filter_min_height": filter_min_height,
        "filter_max_height": filter_max_height,
        "left_margin": left_margin,
        "right_margin": right_margin,
    }

    result = regions_to_json_dict(
        image_path=image_path,
        image_size=image.size,
        regions=regions,
        settings=settings,
    )

    if output_dir:
        _ensure_dir(output_dir)

        base_name = os.path.splitext(os.path.basename(image_path))[0]

        json_path = os.path.join(output_dir, f"{base_name}.entries.json")
        save_regions_json(
            image_path=image_path,
            image_size=image.size,
            regions=regions,
            settings=settings,
            output_path=json_path,
        )

        if save_debug:
            binary_path = os.path.join(output_dir, f"{base_name}.binary.png")
            boxes_path = os.path.join(output_dir, f"{base_name}.debug_boxes.png")
            projection_path = os.path.join(output_dir, f"{base_name}.projection.json")

            save_debug_binary_image(binary, binary_path)
            save_debug_boxes_image(
                original_image=image,
                regions=regions,
                output_path=boxes_path,
                left_margin=left_margin,
                right_margin=right_margin,
            )
            save_projection_json(
                projection=projection,
                smoothed_projection=smoothed_projection,
                output_path=projection_path,
            )

        result["output_dir"] = output_dir

    return result
