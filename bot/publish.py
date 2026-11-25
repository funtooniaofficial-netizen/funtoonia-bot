"""Publishes the finished reel to Instagram (and the linked Facebook Page)
with Meta's official Graph API. No public video URL needed: uses the
resumable upload endpoints.
"""
import os
import time

import requests

V = os.environ.get("GRAPH_VERSION", "v25.0")
G = f"https://graph.facebook.com/{V}"
TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")
IG_ID = os.environ.get("IG_USER_ID", "")
PAGE_ID = os.environ.get("FB_PAGE_ID", "")


def _check(r):
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text}")
    return r.json()


def instagram_reel(video_path, caption):
    size = os.path.getsize(video_path)
    c = _check(requests.post(f"{G}/{IG_ID}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption,
        "share_to_feed": "true", "access_token": TOKEN}))
    cid = c["id"]
    with open(video_path, "rb") as f:
        _check(requests.post(c.get("uri", f"https://rupload.facebook.com/ig-api-upload/{V}/{cid}"),
                             headers={"Authorization": f"OAuth {TOKEN}",
                                      "offset": "0", "file_size": str(size)},
                             data=f, timeout=600))
    for _ in range(60):  # wait for Instagram to process (up to ~10 min)
        s = _check(requests.get(f"{G}/{cid}", params={
            "fields": "status_code,status", "access_token": TOKEN}))
        print("IG status:", s)
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing error: {s}")
        time.sleep(10)
    p = _check(requests.post(f"{G}/{IG_ID}/media_publish", data={
        "creation_id": cid, "access_token": TOKEN}))
    print("Instagram published:", p)
    return p["id"]


def facebook_reel(video_path, caption):
    if not PAGE_ID:
        return None
    s = _check(requests.post(f"{G}/{PAGE_ID}/video_reels", data={
        "upload_phase": "start", "access_token": TOKEN}))
    vid = s["video_id"]
    with open(video_path, "rb") as f:
        _check(requests.post(s.get("upload_url", f"https://rupload.facebook.com/video-upload/{V}/{vid}"),
                             headers={"Authorization": f"OAuth {TOKEN}", "offset": "0",
                                      "file_size": str(os.path.getsize(video_path))},
                             data=f, timeout=600))
    p = _check(requests.post(f"{G}/{PAGE_ID}/video_reels", data={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
        "description": caption, "access_token": TOKEN}))
    print("Facebook published:", p)
    return vid
