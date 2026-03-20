import os
from dataclasses import dataclass
from typing import Any, Dict

import cv2
import numpy as np
import pytesseract
from PIL import Image


@dataclass
class LocalOCRConfig:
    lang: str = os.getenv("OCR_LANG", "deu+lat")
    psm: str = os.getenv("OCR_PSM", "6")
    oem: str = os.getenv("OCR_OEM", "1")
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "tesseract")
    upscale_factor: float = float(os.getenv("OCR_UPSCALE_FACTOR", "2.0"))


class LocalPageReader:
    def __init__(self, config: LocalOCRConfig | None = None):
        self.config = config or LocalOCRConfig()
        pytesseract.pytesseract.tesseract_cmd = self.config.tesseract_cmd

    def preprocess_image(self, image_path: str) -> Image.Image:
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Bild nicht lesbar: {image_path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        if self.config.upscale_factor and self.config.upscale_factor != 1.0:
            gray = cv2.resize(
                gray,
                None,
                fx=self.config.upscale_factor,
                fy=self.config.upscale_factor,
                interpolation=cv2.INTER_CUBIC,
            )

        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        gray = cv2.equalizeHist(gray)

        bw = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )

        kernel = np.ones((1, 1), np.uint8)
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)

        return Image.fromarray(bw)

    def read_page(self, image_path: str) -> Dict[str, Any]:
        image = self.preprocess_image(image_path)

        config_str = f"--oem {self.config.oem} --psm {self.config.psm}"

        text = pytesseract.image_to_string(
            image,
            lang=self.config.lang,
            config=config_str,
        )

        data = pytesseract.image_to_data(
            image,
            lang=self.config.lang,
            config=config_str,
            output_type=pytesseract.Output.DICT,
        )

        confidences = []
        for c in data.get("conf", []):
            try:
                val = float(c)
                if val >= 0:
                    confidences.append(val)
            except Exception:
                pass

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            "engine": "tesseract",
            "text": text.strip(),
            "confidence": round(avg_conf, 2),
            "meta": {
                "lang": self.config.lang,
                "psm": self.config.psm,
                "oem": self.config.oem,
                "upscale_factor": self.config.upscale_factor,
            },
        }
