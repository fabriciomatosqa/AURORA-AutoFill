#!/usr/bin/env python3
"""Regera ícones Windows/Linux/Qt a partir da marca transparente fornecida."""
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.branding import brand_webp_bytes


def main() -> None:
    assets = ROOT / "assets"
    artwork = Image.open(BytesIO(brand_webp_bytes(assets))).convert("RGBA")
    if artwork.size != (256, 256):
        raise ValueError(f"Tamanho inesperado da arte: {artwork.size}")
    if artwork.getextrema()[3] != (0, 255):
        raise ValueError("A logo deve possuir transparência alfa real.")

    artwork.save(assets / "aurora_icon_256.png", optimize=True)
    artwork.resize((512, 512), Image.Resampling.LANCZOS).save(
        assets / "aurora_icon.png", optimize=True
    )
    artwork.save(
        assets / "aurora_icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
               (64, 64), (128, 128), (256, 256)],
    )
    print("Ícones AURORA transparentes gerados: PNG 512, PNG 256 e ICO 16–256.")


if __name__ == "__main__":
    main()
