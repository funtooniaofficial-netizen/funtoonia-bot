"""Decides WHAT to post: scene idea, image prompt, on-screen text, caption.

Uses the free Gemini API (text only) and free RSS news feeds.
"""
import json
import os
import random
import re
import xml.etree.ElementTree as ET

import requests

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "")
API = "https://generativelanguage.googleapis.com/v1beta"


def pick_model(want_image=False):
    """Ask Google which models this key can use and pick the best free one,
    so the bot keeps working when Google retires old model names."""
    r = requests.get(f"{API}/models", params={"key": GEMINI_KEY, "pageSize": 200},
                     timeout=30)
    r.raise_for_status()
    names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    bad = ("tts", "live", "audio", "embedding", "thinking", "exp", "preview",
           "computer", "robotics")
    if want_image:
        cands = [n for n in names if "image" in n and "flash" in n]
    else:
        cands = [n for n in names if "flash" in n and "image" not in n
                 and not any(b in n for b in bad)]
        cands = cands or [n for n in names if "flash" in n and "image" not in n]
    if not cands:
        raise RuntimeError(f"No suitable Gemini model in: {names}")

    def ver(n):
        v = [-int(x) for x in re.findall(r"\d+", n)][:3]
        return v + [0] * (3 - len(v))
    cands.sort(key=lambda n: ("lite" in n, ver(n)))
    print("Gemini models available:", cands[:5])
    return cands[0]

STYLE = ("anime style, Studio Ghibli inspired, cinematic lighting, soft colors, "
         "highly detailed background, vertical composition, no text, no letters, "
         "no watermark, no logo")

# Rotates so the feed never looks the same two days in a row
TIMES = ["sunrise", "bright morning", "sunny afternoon", "golden sunset",
         "rainy evening", "calm night with city lights", "snowy dusk",
         "spring cherry blossom day", "autumn afternoon"]

NEWS_FEEDS = [
    ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ("BBC", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
]

# Never turn tragedy into a cartoon reel
BLOCK_WORDS = re.compile(
    r"\b(kill|killed|dead|death|dies|died|murder|shoot|shooting|attack|war|"
    r"bomb|terror|rape|abuse|assault|crash|victim|massacre|hostage|suicide|"
    r"injured|wounded|genocide|stab|missile|strike|flood|earthquake|famine|"
    r"funeral|disaster|fire)\w*", re.I)


def _gemini_json(prompt: str) -> dict:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is missing")
    model = GEMINI_MODEL or pick_model()
    url = f"{API}/models/{model}:generateContent?key={GEMINI_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "temperature": 1.0},
    }
    r = requests.post(url, json=body, timeout=90)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


COMMON_RULES = """
Rules:
- Original scenes only. Never depict real, identifiable people, celebrities,
  politicians, brands, logos or copyrighted characters.
- Family-friendly, kind humour. Never mock a nationality, religion, gender or group.
- "weather" must be one of: rain, snow, petals, sparkles, fireflies, none.
- Caption: 1-2 short lines + one question to the audience to drive comments,
  then 8-12 relevant hashtags including #Funtoonia. Global English.
Return ONLY JSON with keys:
  title, image_prompt, weather, overlay_text, caption
"""


def feelgood(recent_titles):
    time_of_day = random.choice(TIMES)
    prompt = f"""You create a daily relaxing, feel-good anime reel for the
Instagram page "Funtoonia". Today's setting: {time_of_day}.
Invent ONE peaceful, heart-warming scene that makes viewers relax and smile
(cozy places, kindness, animals, nature, small happy moments, travel spots
around the world). Avoid repeating these recent ideas: {recent_titles}.
image_prompt: a vivid 40-70 word description of the scene for an image AI.
overlay_text: a short soothing line (max 8 words) or empty string.
{COMMON_RULES}"""
    d = _gemini_json(prompt)
    d["image_prompt"] = f"{d['image_prompt']}, {time_of_day}, {STYLE}"
    d["mode"] = "feelgood"
    return d


def funny(recent_titles):
    prompt = f"""You create a daily funny anime-style reel for the Instagram
page "Funtoonia". Invent ONE instantly relatable, wholesome joke situation
(office life, Monday mornings, cats vs owners, diets, phone battery at 1%,
online shopping, gym, traffic, AI assistants failing, students, parents...).
Avoid these recent ideas: {recent_titles}.
image_prompt: 40-70 words describing a single funny cartoon moment with an
exaggerated expression; bright daytime colours.
overlay_text: the meme punchline shown on screen, max 14 words, e.g.
"Me: just one episode. Also me at 4 AM:".
{COMMON_RULES}"""
    d = _gemini_json(prompt)
    d["image_prompt"] = f"{d['image_prompt']}, comedic, expressive, {STYLE}"
    d["mode"] = "funny"
    return d


def fetch_news(seen_links):
    items = []
    for source, url in NEWS_FEEDS:
        try:
            r = requests.get(url, timeout=30,
                             headers={"User-Agent": "Mozilla/5.0 FuntooniaBot"})
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                desc = re.sub("<[^>]+>", "", it.findtext("description") or "").strip()
                link = (it.findtext("link") or "").strip()
                if not title or link in seen_links:
                    continue
                if BLOCK_WORDS.search(title + " " + desc):
                    continue
                items.append({"source": source, "title": title,
                              "summary": desc[:400], "link": link})
        except Exception as e:  # one broken feed must not stop the post
            print(f"feed failed {url}: {e}")
    return items[:40]


def news(seen_links):
    items = fetch_news(seen_links)
    if not items:
        raise RuntimeError("No safe news items found")
    listing = "\n".join(f"{i}. [{x['source']}] {x['title']} — {x['summary']}"
                        for i, x in enumerate(items))
    prompt = f"""You run "Funtoonia", a light, positive world-news reel page.
From these headlines of the last 24 hours, pick the ONE story that is
uplifting, surprising, quirky, or a big tech/science/space/world moment
that people will enjoy hearing about. Skip anything tragic or divisive.

{listing}

Then:
- image_prompt: 40-70 words, an illustrated anime scene that represents the
  story symbolically (places, objects, animals, generic people). NO real
  faces, NO politicians, NO logos.
- overlay_text: the news in max 18 plain words, factual, no exaggeration.
- caption: 2-3 factual lines explaining the story, then
  "Source: <source name>", a question to the audience, then hashtags
  including #Funtoonia #news #todayinnews.
Also return "pick" = the index number you chose.
{COMMON_RULES}"""
    d = _gemini_json(prompt)
    pick = items[int(d.get("pick", 0))]
    d["image_prompt"] = f"{d['image_prompt']}, {STYLE}"
    d["mode"] = "news"
    d["source"] = pick["source"]
    d["link"] = pick["link"]
    if pick["source"].lower() not in d["caption"].lower():
        d["caption"] += f"\nSource: {pick['source']}"
    return d
