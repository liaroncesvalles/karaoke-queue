"""Karaoke Queue local server.

Serves index.html and provides /api/search?q=... which returns YouTube
search results as JSON, so the page can show results without an API key.

Run:  python3 server.py      then open http://localhost:8000
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8000))
HERE = os.path.dirname(os.path.abspath(__file__))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": "CONSENT=YES+1",
}


def find_videos(node, out):
    """Walk YouTube's page data and collect every videoRenderer."""
    if isinstance(node, dict):
        vr = node.get("videoRenderer")
        if isinstance(vr, dict) and vr.get("videoId"):
            out.append(vr)
        for v in node.values():
            find_videos(v, out)
    elif isinstance(node, list):
        for v in node:
            find_videos(v, out)


def text_of(obj):
    if not isinstance(obj, dict):
        return ""
    if "simpleText" in obj:
        return obj["simpleText"]
    return "".join(r.get("text", "") for r in obj.get("runs", []))


def youtube_search(query, limit=20):
    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": query})
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", "replace")
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        raise RuntimeError("Could not read YouTube results")
    renderers = []
    find_videos(json.loads(m.group(1)), renderers)
    results, seen = [], set()
    for vr in renderers:
        vid = vr["videoId"]
        if vid in seen:
            continue
        seen.add(vid)
        results.append({
            "id": vid,
            "title": text_of(vr.get("title")),
            "channel": text_of(vr.get("ownerText")),
            "duration": text_of(vr.get("lengthText")),
            "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
        })
        if len(results) >= limit:
            break
    # Drop videos whose owners don't allow playing outside YouTube (e.g. Sing King)
    with ThreadPoolExecutor(max_workers=8) as pool:
        playable = list(pool.map(is_embeddable, [r["id"] for r in results]))
    return [r for r, ok in zip(results, playable) if ok]


def is_embeddable(video_id):
    url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"format": "json", "url": f"https://www.youtube.com/watch?v={video_id}"})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=5):
            return True
    except urllib.error.HTTPError as e:
        return e.code not in (401, 403, 404)
    except Exception:
        return True  # couldn't check; keep it and let the player handle it


NOISE = re.compile(r"\b(karaoke|minus ?one|instrumental|lyrics?|version|videoke|with)\b", re.I)


def _suggest_raw(q):
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode(
        {"client": "firefox", "ds": "yt", "q": q})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return data[1] if len(data) > 1 else []
    except Exception:
        return []


def youtube_suggest(query, limit=8):
    """Song suggestions while typing, from YouTube's autocomplete.
    Mixes normal suggestions (full song/artist names) with karaoke-biased ones."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        plain, kara = pool.map(_suggest_raw, [query, f"{query} karaoke"])
    out, seen = [], {query.lower().strip()}
    for s in plain[:5] + kara:
        clean = re.sub(r"\s+", " ", NOISE.sub(" ", s)).strip()
        # skip leftovers that are just the typed words plus one filler word
        if len(clean) <= len(query) + 2 or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        out.append(clean)
        if len(out) >= limit:
            break
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/api/search", "/api/suggest"):
            q = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip()
            try:
                if parsed.path == "/api/suggest":
                    body = {"suggestions": youtube_suggest(q) if q else []}
                else:
                    results = youtube_search(q) if q else []
                    if q and not results:  # YouTube occasionally returns an empty page; try once more
                        results = youtube_search(q)
                    body = {"results": results}
                status = 200
            except Exception as e:  # network error, YouTube layout change, etc.
                body, status = {"error": str(e)}, 502
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            # lets the GitHub Pages copy of the site (liaroncesvalles.github.io) use this search
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet


if __name__ == "__main__":
    print(f"🎤 Karaoke Queue running at http://localhost:{PORT}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
