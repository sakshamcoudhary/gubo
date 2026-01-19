# ------------------------------------------------------------
# Instagram Info API — Updated & Stabilized Version
# Original Credit : Anmol (@FOREVER_HIDDEN)
# Updated by      : Compatibility + Stability Fix
# Purpose         : Fetch public profile & recent media safely
# ------------------------------------------------------------

from flask import Flask, jsonify, request
import requests
import time
import socket
from functools import lru_cache

app = Flask(__name__)

# ---------------- SAFE HELPERS ----------------

def safe_get(d, *keys, default=None):
    """
    Safely get nested dict values.
    """
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
    return d if d is not None else default


# ---------------- INSTAGRAM FETCH ----------------

@lru_cache(maxsize=512)
def fetch_instagram_profile(username, proxy=None):
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "x-ig-app-id": "936619743392459",
        "Referer": f"https://www.instagram.com/{username}/",
    }

    session = requests.Session()
    proxies = {"http": proxy, "https": proxy} if proxy else None

    backoff = 1
    for _ in range(4):
        try:
            resp = session.get(url, headers=headers, timeout=10, proxies=proxies)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in (403, 429):
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code == 404:
                return {"error": "not_found", "status_code": 404}

            return {
                "error": "http_error",
                "status_code": resp.status_code,
                "body": resp.text[:300],
            }

        except requests.RequestException as e:
            time.sleep(backoff)
            backoff *= 2

    return {"error": "request_failed"}


# ---------------- API ROUTE ----------------

@app.route("/api/insta/<username>", methods=["GET"])
def insta_info(username):
    proxy = request.args.get("proxy")
    data = fetch_instagram_profile(username, proxy=proxy)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid_response"}), 502

    if "error" in data:
        return jsonify(data), data.get("status_code", 400)

    try:
        user = (
            safe_get(data, "data", "user")
            or safe_get(data, "user")
            or safe_get(data, "data")
        )

        if not isinstance(user, dict):
            return jsonify({"error": "user_not_found", "raw": data})

        out = {
            "id": user.get("id"),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "biography": user.get("biography"),
            "is_private": user.get("is_private"),
            "is_verified": user.get("is_verified"),
            "profile_pic_url": (
                user.get("profile_pic_url_hd")
                or user.get("profile_pic_url")
            ),
            "followers_count": safe_get(
                user, "edge_followed_by", "count",
                default=user.get("followers_count")
            ),
            "following_count": safe_get(
                user, "edge_follow", "count",
                default=user.get("following_count")
            ),
            "media_count": safe_get(
                user, "edge_owner_to_timeline_media", "count",
                default=user.get("media_count")
            ),
            "recent_media": [],
        }

        media_block = (
            user.get("edge_owner_to_timeline_media")
            or user.get("media")
            or {}
        )

        edges = media_block.get("edges") or media_block.get("items") or []

        for item in edges[:8]:
            node = item.get("node") if isinstance(item, dict) else item
            if not isinstance(node, dict):
                continue

            caption = None
            cap_edges = safe_get(node, "edge_media_to_caption", "edges", default=[])
            if cap_edges:
                caption = safe_get(cap_edges[0], "node", "text")

            out["recent_media"].append({
                "id": node.get("id"),
                "shortcode": node.get("shortcode"),
                "display_url": node.get("display_url") or node.get("display_src"),
                "taken_at": (
                    node.get("taken_at_timestamp")
                    or node.get("taken_at")
                ),
                "caption": caption,
            })

        return jsonify(out)

    except Exception as exc:
        return jsonify({
            "error": "parse_error",
            "details": str(exc)
        }), 500


# ---------------- PORT HANDLING ----------------

def find_free_port(start=8080, end=65535):
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("0.0.0.0", port)) != 0:
                return port
    raise RuntimeError("No free port available")


# ---------------- MAIN ----------------

if __name__ == "__main__":
    port = find_free_port()
    print(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)