"""Makes the still picture for the reel (free).

1st choice: Pollinations.ai (free, no key; optional POLLINATIONS_TOKEN for
higher limits). Fallback: Gemini image model, if your key has access.
"""
import base64
import io
import os
import random
import time
import urllib.parse

import requests
from PIL import Image

W, H = 1080, 1920


def _pollinations(prompt: str) -> Image.Image:
    seed = random.randint(1, 10_000_000)
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt) +
           f"?width={W}&height={H}&model=flux&nologo=true&enhance=true&seed={seed}")
    headers = {}
    token = os.environ.get("POLLINATIONS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(url, headers=headers, timeout=240)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def _gemini_image(prompt: str) -> Image.Image:
    key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_IMAGE_MODEL", "")
    if not model:
        from content import pick_model
        model = pick_model(want_image=True)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": prompt + ". Vertical 9:16 image."}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]}}
    r = requests.post(url, json=body, timeout=240)
    r.raise_for_status()
    for part in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return Image.open(io.BytesIO(base64.b64decode(part["inlineData"]["data"]))).convert("RGB")
    raise RuntimeError("Gemini returned no image")


def make_image(prompt: str, out_path: str) -> str:
    errors = []
    for attempt in range(3):
        for fn in (_pollinations, _gemini_image):
            try:
                img = fn(prompt)
                img.save(out_path, quality=95)
                print(f"image via {fn.__name__}: {img.size}")
                return out_path
            except Exception as e:
                errors.append(f"{fn.__name__}: {e}")
                print(errors[-1])
        time.sleep(20 * (attempt + 1))
    raise RuntimeError("All image sources failed: " + " | ".join(errors))
