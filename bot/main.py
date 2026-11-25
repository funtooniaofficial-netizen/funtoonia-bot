"""Entry point: python bot/main.py feelgood|funny|news [--dry-run]"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import content  # noqa: E402
from animate import render  # noqa: E402
from image import make_image  # noqa: E402

STATE = "state/history.json"


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"posts": [], "news_links": []}


def save_state(s):
    os.makedirs("state", exist_ok=True)
    s["posts"] = s["posts"][-60:]
    s["news_links"] = s["news_links"][-300:]
    with open(STATE, "w") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)


def main():
    mode = sys.argv[1]
    dry = "--dry-run" in sys.argv
    state = load_state()
    recent = [p["title"] for p in state["posts"] if p["mode"] == mode][-15:]

    if mode == "feelgood":
        c = content.feelgood(recent)
    elif mode == "funny":
        c = content.funny(recent)
    elif mode == "news":
        c = content.news(set(state["news_links"]))
    else:
        raise SystemExit("mode must be feelgood, funny or news")
    c["caption"] = c["caption"].strip() + "\n\n🎨 AI-generated toon #AIart"
    print(json.dumps(c, indent=1, ensure_ascii=False))

    os.makedirs("out", exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    img = make_image(c["image_prompt"], f"out/{stamp}-{mode}.jpg")
    video = render(img, c, f"out/{stamp}-{mode}.mp4")
    print("video ready:", video)

    if dry:
        print("DRY RUN - not posting")
        return
    from publish import facebook_reel, instagram_reel
    ig = instagram_reel(video, c["caption"])
    try:
        facebook_reel(video, c["caption"])
    except Exception as e:  # Instagram is the priority; FB failure is logged
        print("Facebook reel failed:", e)

    state["posts"].append({"mode": mode, "title": c.get("title", ""),
                           "ig_id": ig, "time": stamp})
    if c.get("link"):
        state["news_links"].append(c["link"])
    save_state(state)


if __name__ == "__main__":
    main()
