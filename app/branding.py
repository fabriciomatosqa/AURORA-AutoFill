"""Fonte compactada da marca AURORA; mesma arte para UI e instaladores."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

# Extraída da imagem PNG transparente aprovada para a identidade AURORA.
BRAND_SHA256 = "109b1a4b8c98c2f8708c6a80f9d09e409dc2576259ac02f60cc01361d95b9298"


def brand_webp_bytes(root: Path | None = None) -> bytes:
    assets = root or Path(__file__).resolve().parents[1] / "assets"
    paths = sorted((assets / "branding").glob("part*.txt"))
    if len(paths) != 11:
        raise FileNotFoundError("Os 11 segmentos da identidade AURORA são obrigatórios.")
    encoded = "".join(path.read_text(encoding="ascii").strip() for path in paths)
    data = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(data).hexdigest() != BRAND_SHA256:
        raise ValueError("A marca AURORA não passou na verificação de integridade.")
    return data
