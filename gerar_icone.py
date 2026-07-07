# -*- coding: utf-8 -*-
"""Gera beergame.ico (multi-resolução) a partir de logo.jpg/logo.png.
Use depois de trocar o logo: python gerar_icone.py"""
import os
from PIL import Image

origem = "logo.jpg" if os.path.exists("logo.jpg") else "logo.png"
img = Image.open(origem).convert("RGBA")
tamanhos = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
img.save("beergame.ico", sizes=tamanhos)
print(f"beergame.ico gerado a partir de {origem} ({len(tamanhos)} resoluções).")
