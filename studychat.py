#!/usr/bin/env python3
"""
studychat.py - a tiny silent chat overlay for your local wifi (or the internet).

Run the same file on every laptop, pick the same room name, and you're chatting.
No accounts (just Python 3).

  python studychat.py
  python studychat.py --name Lucy --room study
  python studychat.py --online        (school wifi, see below)

How it behaves:
  - Idle: a small blue "Chat" button sits in the bottom-left corner.
  - New message: a small popup opens in the corner, then shrinks back.
  - Click the button/popup to type. Enter sends. Esc closes it.
  - Drag the top bar to move it (it remembers where you put it).
  - Right-click the button to open Settings or quit.

Settings:
  - Click "settings" in the top bar (or type /settings). Colors, opacity,
    sizes, timings and more. Changes preview live; click Save to keep them.
  - Your settings are saved in a file called .studychat.json in your home folder.

School wifi:
  - Most school wifi stops laptops from seeing each other, so same-wifi mode
    can't work there. Choose "online mode" at startup (or run with --online)
    and chat goes through a free public relay (ntfy.sh) instead. Everyone
    must pick the same mode. Online mode is NOT private, so use a long,
    hard-to-guess room name.

Commands: /reels [link] (small Instagram window; needs Chrome, Chromium,
  Edge or Brave, or pywebview),
  /who (who's online), /update (check for a new version),
  /version, /settings, /img, /quit. The chat checks GitHub for a newer
  version when it starts; set STUDYCHAT_NO_UPDATE=1 to turn that off.

Images:
  - Press Ctrl+V in the text box to send an image from your clipboard
    (screenshots work great), or click "+" to pick an image file,
    or type  /img path/to/file.png
  - GIFs keep moving: send one with "+" or  /img path/to/file.gif , or with
    a direct link:  /gif https://example.com/funny.gif  (right-click a GIF
    and "copy image address"). Only the newest few GIFs animate.
  - Click an image in the chat to see it full size (click it again to close).
  - Install Pillow for best results:  pip install pillow
    (without it, only PNG and GIF files can be sent, and no clipboard paste)
"""

import argparse
import base64
import email.utils
import hashlib
import io
import json
import os
import queue
import shutil
import random
import re
import socket
import ssl
import subprocess
import sys
import threading
import webbrowser
import importlib.util
import urllib.parse
import time
import traceback
import urllib.error
import urllib.request
import uuid

try:
    from PIL import Image, ImageGrab
    PIL_OK = True
except Exception:
    PIL_OK = False
try:
    from PIL import ImageTk
except Exception:
    ImageTk = None

# ------------------------------------------------------------------ version
# Bump VERSION whenever you publish a new studychat.py to GitHub. Everyone
# running an older version is told, and can update with one click.
VERSION = "1.0"
UPDATE_REPO = "jojobananas12/Study-chat"     # github.com/<this>
CHECK_UPDATES = os.environ.get("STUDYCHAT_NO_UPDATE") != "1"

# ============================================================== settings ====
# These are the defaults. Everything in the SPEC table below can be changed
# from the Settings window, and is saved to ~/.studychat.json.

# --- Look
PILL_LABEL = "Chat"      # text on the button
PILL_BG = "#2f7df6"      # button color
PILL_FG = "#ffffff"      # button text color
PILL_ALPHA = 0.95        # button opacity
PILL_W, PILL_H = 96, 38  # button size
POPUP_ALPHA = 0.92       # popup opacity
ACTIVE_ALPHA = 0.96      # chat window opacity (while typing)
BG = "#14161c"           # chat background
BAR = "#1d2029"          # top bar and text box color
FG = "#e8e8e8"           # message text color
MUTED = "#8a90a0"        # faded text color
FONT_FAMILY = "Papyrus"
MY_FONT = ""             # font for YOUR messages (blank = use the one above)
FONT_SIZE = 10

# --- Window
WIDTH = 360
POPUP_HEIGHT = 130
POPUP_IMG_HEIGHT = 270   # popup is taller when the newest message is an image
ACTIVE_HEIGHT = 330
ANCHOR_X = 20            # distance from the left edge of the screen
BOTTOM_MARGIN = 70       # distance from the bottom edge of the screen

# --- Behavior
POPUP_SECONDS = 8        # how long a new-message popup stays open
ACTIVE_IDLE_SECONDS = 20 # typing box closes itself after this much quiet
POPUP_LINES = 6          # messages shown in the popup
MAX_HISTORY = 300        # messages kept in the chat
DEFAULT_NAME = ""        # pre-filled in the "Your name" box
DEFAULT_ROOM = "study"   # pre-filled in the "Room name" box

# --- Images
THUMB_W, THUMB_H = 280, 180
MAX_IMAGE_MB = 8         # biggest image allowed, in megabytes
SEND_MAX_DIM = 1600      # big images are shrunk to this many pixels first

# --- Network (these need a restart)
PORT = 50555             # same-wifi mode (everyone must match)
RELAY_URL = "https://ntfy.sh"   # online mode
WIFI_PING_EVERY = 20     # seconds between "I'm still here" signals
ONLINE_PING_EVERY = 240

PALETTE = ["#5aa9ff", "#ff7a7a", "#7be08a", "#ffd166", "#c792ea",
           "#4dd0e1", "#ffab70", "#f48fb1"]

# (tab, variable, label, kind, low, high)   for text: low/high = min/max length
SPEC = [
    ("Look", "PILL_LABEL", "Button text", "str", 1, 12),
    ("Look", "PILL_BG", "Button color", "color", 0, 0),
    ("Look", "PILL_FG", "Button text color", "color", 0, 0),
    ("Look", "PILL_ALPHA", "Button opacity", "float", 0.1, 1.0),
    ("Look", "PILL_W", "Button width", "int", 30, 400),
    ("Look", "PILL_H", "Button height", "int", 16, 150),
    ("Look", "POPUP_ALPHA", "Popup opacity", "float", 0.1, 1.0),
    ("Look", "ACTIVE_ALPHA", "Chat window opacity", "float", 0.1, 1.0),
    ("Look", "BG", "Chat background", "color", 0, 0),
    ("Look", "BAR", "Top bar and text box", "color", 0, 0),
    ("Look", "FG", "Message text color", "color", 0, 0),
    ("Look", "MUTED", "Faded text color", "color", 0, 0),
    ("Look", "FONT_FAMILY", "Font", "str", 1, 40),
    ("Look", "MY_FONT", "Font for your messages (everyone sees it)",
     "font", 0, 40),
    ("Look", "FONT_SIZE", "Text size", "int", 7, 24),
    ("Window", "WIDTH", "Width", "int", 200, 900),
    ("Window", "POPUP_HEIGHT", "Popup height (text)", "int", 60, 600),
    ("Window", "POPUP_IMG_HEIGHT", "Popup height (image)", "int", 100, 900),
    ("Window", "ACTIVE_HEIGHT", "Chat window height", "int", 120, 1000),
    ("Window", "ANCHOR_X", "Distance from left edge", "int", 0, 5000),
    ("Window", "BOTTOM_MARGIN", "Distance from bottom edge", "int", 0, 3000),
    ("Behavior", "POPUP_SECONDS", "Popup stays open (seconds)", "int", 1, 120),
    ("Behavior", "ACTIVE_IDLE_SECONDS", "Close typing box after idle (seconds)",
     "int", 3, 600),
    ("Behavior", "POPUP_LINES", "Messages shown in popup", "int", 1, 20),
    ("Behavior", "MAX_HISTORY", "Messages remembered", "int", 20, 2000),
    ("Behavior", "DEFAULT_NAME", "Default name", "str", 0, 20),
    ("Behavior", "DEFAULT_ROOM", "Default room", "str", 1, 60),
    ("Images", "THUMB_W", "Thumbnail width", "int", 60, 800),
    ("Images", "THUMB_H", "Thumbnail height", "int", 40, 800),
    ("Images", "MAX_IMAGE_MB", "Biggest image allowed (MB)", "int", 1, 15),
    ("Images", "SEND_MAX_DIM", "Shrink big images to (pixels)", "int", 300, 4000),
    ("Network", "PORT", "Same-wifi port", "int", 1024, 65535),
    ("Network", "RELAY_URL", "Online relay address", "str", 8, 200),
    ("Network", "WIFI_PING_EVERY", "Wifi 'still here' signal (seconds)",
     "int", 5, 120),
    ("Network", "ONLINE_PING_EVERY", "Online 'still here' signal (seconds)",
     "int", 15, 300),
]
SPEC_BY_KEY = {s[1]: s for s in SPEC}
DEFAULTS = {s[1]: globals()[s[1]] for s in SPEC}
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".studychat.json")


def derive():
    globals()["MAX_IMAGE_BYTES"] = int(MAX_IMAGE_MB * 1024 * 1024)


derive()


def set_value(key, val):
    globals()[key] = val
    if key == "MAX_IMAGE_MB":
        derive()


def validate(spec, raw):
    """Turn what the person typed into a safe value, or None if it's junk."""
    _tab, _key, _label, kind, lo, hi = spec
    try:
        if kind == "int":
            return int(max(lo, min(hi, round(float(raw)))))
        if kind == "float":
            return round(max(lo, min(hi, float(raw))), 2)
        if kind == "color":
            s = str(raw).strip()
            return s.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", s) else None
        s = str(raw).strip()[:hi]
        return s if len(s) >= lo else None
    except (TypeError, ValueError, OverflowError):
        return None


def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if isinstance(data, dict):
        for spec in SPEC:
            if spec[1] in data:
                v = validate(spec, data[spec[1]])
                if v is not None:
                    set_value(spec[1], v)
    env = os.environ.get("STUDYCHAT_RELAY")     # handy for testing
    if env:
        set_value("RELAY_URL", env)


def save_settings():
    try:
        data = {s[1]: globals()[s[1]] for s in SPEC}
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, SETTINGS_PATH)
        return True
    except OSError:
        return False


def F(delta=0, bold=False):
    size = max(6, FONT_SIZE + delta)
    return (FONT_FAMILY, size, "bold") if bold else (FONT_FAMILY, size)


def name_color(name):
    return PALETTE[sum(map(ord, name)) % len(PALETTE)]


LOG_PATH = os.path.join(os.path.expanduser("~"), ".studychat.log")
_NON_BMP = re.compile("[\U00010000-\U0010ffff]")


def bmp(s):
    """Old versions of Tk (common on Macs) choke on emoji; swap them for ?"""
    return _NON_BMP.sub("?", s)


def log(text):
    """Quiet diagnostics in ~/.studychat.log (handy if something freezes)."""
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 200000:
            os.replace(LOG_PATH, LOG_PATH + ".old")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ updates
def _ver_tuple(v):
    nums = re.findall(r"\d+", str(v))
    return tuple(int(n) for n in nums[:4]) or (0,)


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _http_get(url, timeout=12, limit=3_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": "studychat"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as r:
        return r.read(limit + 1)[:limit]


def _version_in(text):
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return m.group(1) if m else None


def check_for_update():
    """Newest version on GitHub, as {"version", "url"}, or None if you're
    already up to date. Looks at the latest release and at the main branch,
    and takes whichever is newest. Raises if GitHub can't be reached."""
    found, reached = [], False
    try:
        data = json.loads(_http_get(
            f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
            timeout=10).decode("utf-8"))
        tag = str(data.get("tag_name", "")).strip()
        if tag:
            found.append({"version": tag.lstrip("vV"), "url":
                          f"https://raw.githubusercontent.com/"
                          f"{UPDATE_REPO}/{tag}/studychat.py"})
        reached = True
    except urllib.error.HTTPError as ex:
        reached = reached or ex.code == 404     # no releases yet is fine
    except Exception:
        pass
    for branch in ("main", "master"):
        url = (f"https://raw.githubusercontent.com/"
               f"{UPDATE_REPO}/{branch}/studychat.py")
        try:
            ver = _version_in(_http_get(url).decode("utf-8", "replace"))
            reached = True
            if ver:
                found.append({"version": ver, "url": url})
            break
        except urllib.error.HTTPError:
            reached = True
        except Exception:
            pass
    if not reached:
        raise OSError("can't reach GitHub")
    found = [f for f in found if _ver_tuple(f["version"]) > _ver_tuple(VERSION)]
    return max(found, key=lambda f: _ver_tuple(f["version"])) if found else None


def install_update(info):
    """Download the new studychat.py, check it, keep a backup of this one,
    and swap it in. Returns the new version. Raises if anything is off."""
    raw = _http_get(info["url"])
    text = raw.decode("utf-8")
    if "def main" not in text or "class Overlay" not in text:
        raise ValueError("downloaded file doesn't look like studychat")
    compile(text, "studychat.py", "exec")           # must be valid Python
    ver = _version_in(text)
    if not ver or _ver_tuple(ver) <= _ver_tuple(VERSION):
        raise ValueError("downloaded file isn't newer")
    path = os.path.abspath(__file__)
    with open(path, "rb") as f:
        old = f.read()
    with open(path + ".bak", "wb") as f:            # easy to undo
        f.write(old)
    tmp = path + ".new"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)
    return ver


# ---------------------------------------------------------------------- gifs
MAX_GIF_FRAMES = 100       # more frames than this are skipped to save memory
LIVE_GIFS = 5              # only the newest few GIFs in the chat animate


def gif_delays(data):
    """Per-frame delays (ms) read straight from a GIF file."""
    out = [max(20, (b[0] | (b[1] << 8)) * 10) for b in
           re.findall(rb"\x21\xf9\x04.(..)", data, re.S)]
    return [d if d > 20 else 100 for d in out]


def shrink_gif(data, limit):
    """Make an animated GIF smaller (fewer pixels, then fewer frames) until it
    fits under `limit` bytes. Needs Pillow. Returns bytes, or None."""
    if not PIL_OK:
        return None
    try:
        im = Image.open(io.BytesIO(data))
        n = getattr(im, "n_frames", 1)
        frames, durs = [], []
        step = 1 if n <= 150 else 2
        for k in range(0, n, step):
            im.seek(k)
            frames.append(im.convert("RGBA"))
            durs.append(max(20, int(im.info.get("duration", 100))) * step)
        for scale in (0.8, 0.6, 0.45, 0.3):
            w, h = frames[0].size
            size = (max(16, int(w * scale)), max(16, int(h * scale)))
            small = [f.resize(size) for f in frames]
            buf = io.BytesIO()
            small[0].save(buf, "GIF", save_all=True, append_images=small[1:],
                          duration=durs, loop=0, optimize=True, disposal=2)
            if buf.tell() <= limit:
                return buf.getvalue()
    except Exception:
        log("shrink_gif failed: " + traceback.format_exc())
    return None


# ---------------------------------------------------------------- networking
class Net:
    """Text goes out by UDP broadcast. Images are announced by broadcast, then
    each laptop downloads the picture directly from the sender over TCP."""

    mode = "wifi"

    def __init__(self, room, name, inbox):
        self.room, self.name, self.inbox = room, name, inbox
        self.seen = set()
        self.images = {}
        self.uid = uuid.uuid4().hex
        self.closed = False
        self.ping_every = WIFI_PING_EVERY

        self.rx = self._make_rx()
        self.tx = self._make_tx()
        self.targets = []
        self._refresh_targets()

        # small TCP server that hands out images we've sent
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("", 0))
        self.srv.listen(8)
        self.img_port = self.srv.getsockname()[1]

        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._serve, daemon=True).start()

    @staticmethod
    def _make_rx():
        rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        rx.bind(("", PORT))
        return rx

    @staticmethod
    def _make_tx():
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        return tx

    def _refresh_targets(self):
        """Where to broadcast. Redone regularly in case the wifi changed."""
        targets = [("255.255.255.255", PORT)]
        ip = self._local_ip()
        if ip:
            # most home/dorm networks are /24; also hit that broadcast address
            targets.append((ip.rsplit(".", 1)[0] + ".255", PORT))
        self.targets = targets

    @staticmethod
    def _local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return None

    def _broadcast(self, msg):
        data = json.dumps(msg).encode("utf-8")
        failed = 0
        for target in self.targets:
            try:
                self.tx.sendto(data, target)
            except OSError:
                failed += 1
        if self.targets and failed == len(self.targets):
            try:                              # sending socket went bad
                self.tx.close()
                self.tx = self._make_tx()
            except OSError:
                pass

    def send(self, text, kind="msg", extra=None):
        msg = {"app": "studychat", "room": self.room, "id": uuid.uuid4().hex,
               "name": self.name, "text": text, "type": kind,
               "uid": self.uid}
        if extra:
            msg.update(extra)
        if kind == "ping":
            self._refresh_targets()
        self.seen.add(msg["id"])
        self._broadcast(msg)
        return msg

    def close(self):
        """Tell everyone we're leaving (safe to call more than once)."""
        if not self.closed:
            self.closed = True
            self.send("left", kind="leave")

    def send_image(self, data):
        mid = uuid.uuid4().hex
        self.images[mid] = data
        while len(self.images) > 20:          # keep only the latest few
            self.images.pop(next(iter(self.images)))
        msg = {"app": "studychat", "room": self.room, "id": mid,
               "name": self.name, "text": "", "type": "img",
               "port": self.img_port, "size": len(data)}
        self.seen.add(mid)
        self._broadcast(msg)
        return dict(msg, data=data)

    # --- serving images to other laptops
    def _serve(self):
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._send_to, args=(conn,),
                             daemon=True).start()

    def _send_to(self, conn):
        try:
            conn.settimeout(10)
            with conn.makefile("rb") as f:
                mid = f.readline(100).decode("ascii", "ignore").strip()
            data = self.images.get(mid)
            if data:
                conn.sendall(data)
        except OSError:
            pass
        finally:
            conn.close()

    # --- receiving
    def _listen(self):
        errors = 0
        while True:
            try:
                data, addr = self.rx.recvfrom(65535)
            except OSError:
                # wifi changed or the computer woke up: don't spin, rebuild
                errors += 1
                time.sleep(min(3.0, 0.25 * errors))
                if errors >= 2:
                    try:
                        self.rx.close()
                    except OSError:
                        pass
                    try:
                        self.rx = self._make_rx()
                        if errors == 2:
                            log("wifi listener restarted")
                    except OSError:
                        pass
                continue
            errors = 0
            try:
                msg = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("app") != "studychat" or msg.get("room") != self.room:
                continue
            mid = msg.get("id")
            if not mid or mid in self.seen:   # own echo or duplicate packet
                continue
            self.seen.add(mid)
            if msg.get("type") == "img":
                threading.Thread(target=self._fetch, args=(msg, addr[0]),
                                 daemon=True).start()
            else:
                msg.pop("data", None)
                self.inbox.put(msg)

    def _fetch(self, msg, ip):
        try:
            size = int(msg.get("size", 0))
            if not 0 < size <= MAX_IMAGE_BYTES:
                raise ValueError("bad size")
            buf = bytearray()
            with socket.create_connection((ip, int(msg["port"])),
                                          timeout=10) as s:
                s.sendall((str(msg["id"]) + "\n").encode("ascii"))
                while len(buf) < size:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
            if len(buf) != size:
                raise ValueError("short read")
            msg["data"] = bytes(buf)
        except Exception:
            msg = {"type": "msg", "id": msg.get("id"),
                   "name": msg.get("name", "?"),
                   "text": "(sent an image that didn't load)"}
        self.inbox.put(msg)


class RelayNet:
    """Online mode: messages go through a free public relay (ntfy.sh) over
    HTTPS, so it works on school wifi that stops laptops from seeing each
    other. Same interface as Net. The relay can see the messages, so this is
    not private; use a long, hard-to-guess room name."""

    mode = "online"

    def __init__(self, room, name, inbox):
        self.room, self.name, self.inbox = room, name, inbox
        self.seen = set()
        self.last_id = None
        self.connected = False
        self.uid = uuid.uuid4().hex
        self.closed = False
        # The free relay allows only a few posts per minute for everyone on
        # the same internet address, so keep background chatter rare.
        self.ping_every = max(ONLINE_PING_EVERY, 180)
        self.cool_until = 0              # pause quiet signals after a 429
        self.token = os.environ.get("STUDYCHAT_TOKEN")   # ntfy account
        self.base = RELAY_URL.rstrip("/")
        self.topic = "sc-" + hashlib.sha256(
            ("studychat:" + room).encode("utf-8")).hexdigest()[:32]
        try:
            import certifi
            self.ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            self.ctx = ssl.create_default_context()
        self.sendq = queue.Queue()
        threading.Thread(target=self._sender, daemon=True).start()
        threading.Thread(target=self._subscribe, daemon=True).start()

    def _status(self, text):
        self.inbox.put({"type": "sys", "name": "", "text": text})

    def _open(self, req, timeout):
        req.add_header("User-Agent", "studychat")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        return urllib.request.urlopen(req, timeout=timeout, context=self.ctx)

    # --- sending (one background thread keeps messages in order)
    def send(self, text, kind="msg", extra=None):
        msg = {"app": "studychat", "room": self.room, "id": uuid.uuid4().hex,
               "name": self.name, "text": text[:1000], "type": kind,
               "uid": self.uid}
        if extra:
            msg.update(extra)
        self.seen.add(msg["id"])
        self.sendq.put((msg, None))
        return msg

    def send_image(self, data):
        msg = {"app": "studychat", "room": self.room, "id": uuid.uuid4().hex,
               "name": self.name, "text": "", "type": "img",
               "size": len(data)}
        self.seen.add(msg["id"])
        self.sendq.put((msg, data))
        return dict(msg, data=data)

    def _sender(self):
        url = f"{self.base}/{self.topic}"
        while True:
            msg, data = self.sendq.get()
            quiet = msg.get("type") in ("ping", "join", "leave")
            if quiet and msg.get("type") != "leave" \
                    and time.time() < self.cool_until:
                self.sendq.task_done()           # relay is angry: stay quiet
                continue
            try:
                meta = json.dumps(msg)           # one ASCII line
                for attempt in range(4):
                    if data is None:
                        req = urllib.request.Request(
                            url, data=meta.encode("utf-8"), method="POST")
                    else:
                        ext = ("png" if data.startswith(b"\x89PNG") else
                               "gif" if data.startswith(b"GIF8") else "jpg")
                        req = urllib.request.Request(
                            url, data=data, method="PUT",
                            headers={"Filename": f"image.{ext}",
                                     "Message": meta})
                    try:
                        self._open(req, 60).read()
                        break
                    except urllib.error.HTTPError as ex:
                        if ex.code == 429:
                            self.cool_until = time.time() + 45
                        if ex.code != 429 or quiet or attempt == 3:
                            raise
                        # the relay says slow down: wait, then try again
                        if attempt == 0:
                            self._status("relay is busy, retrying...")
                        time.sleep(5 * (attempt + 1))
            except urllib.error.HTTPError as ex:
                if not quiet:
                    self._status("relay is too busy, message not sent; "
                                 "try again in a minute" if ex.code == 429
                                 else f"message not sent (error {ex.code})")
            except Exception:
                if not quiet:
                    self._status("message not sent (is the internet "
                                 "working?)")
            finally:
                self.sendq.task_done()

    def close(self):
        """Tell everyone we're leaving, and give it a moment to go out."""
        if self.closed:
            return
        self.closed = True
        self.send("left", kind="leave")
        waiter = threading.Thread(target=self.sendq.join, daemon=True)
        waiter.start()
        waiter.join(4)

    def _server_now(self):
        try:
            with self._open(urllib.request.Request(
                    self.base + "/v1/health"), 8) as r:
                return email.utils.parsedate_to_datetime(
                    r.headers.get("Date")).timestamp()
        except Exception:
            return time.time()

    # --- receiving
    def _subscribe(self):
        backoff = 1
        # Use the relay's clock, not ours: if this laptop's clock is a bit
        # fast, "since" would be in the future and replies to our join
        # would be missed (the wrong "online" count on first join).
        start = str(int(self._server_now() - 3))
        failed = False
        while True:
            try:
                url = (f"{self.base}/{self.topic}/json?since="
                       f"{self.last_id or start}")
                with self._open(urllib.request.Request(url), 90) as resp:
                    if not self.connected:
                        self.connected = True
                        self._status("online" if not failed
                                     else "back online")
                    backoff, failed = 1, False
                    for raw in resp:
                        self._handle(raw)
            except Exception:
                pass
            if self.connected or not failed:
                self.connected = False
                if not failed:
                    self._status("can't reach the chat server, retrying...")
                failed = True
            time.sleep(backoff)
            backoff = min(backoff * 2, 15)

    def _handle(self, raw):
        try:
            ev = json.loads(raw)
            if ev.get("event") != "message":
                return
            self.last_id = ev.get("id") or self.last_id
            msg = json.loads(ev.get("message", ""))
        except (ValueError, TypeError, AttributeError):
            return
        if not isinstance(msg, dict):
            return
        if msg.get("app") != "studychat" or msg.get("room") != self.room:
            return
        mid = msg.get("id")
        if not mid or mid in self.seen:           # our own echo or a repeat
            return
        self.seen.add(mid)
        msg.pop("data", None)
        att = ev.get("attachment")
        if msg.get("type") == "img":
            url = att.get("url") if isinstance(att, dict) else None
            if url:
                threading.Thread(target=self._fetch, args=(msg, url),
                                 daemon=True).start()
                return
            msg = {"type": "msg", "id": mid, "name": msg.get("name", "?"),
                   "text": "(sent an image that didn't load)"}
        self.inbox.put(msg)

    def _fetch(self, msg, url):
        try:
            if not str(url).startswith(self.base + "/"):   # only our relay
                raise ValueError("unexpected url")
            with self._open(urllib.request.Request(url), 30) as resp:
                data = resp.read(MAX_IMAGE_BYTES + 1)
            if not data or len(data) > MAX_IMAGE_BYTES:
                raise ValueError("bad size")
            msg["data"] = data
        except Exception:
            msg = {"type": "msg", "id": msg.get("id"),
                   "name": msg.get("name", "?"),
                   "text": "(sent an image that didn't load)"}
        self.inbox.put(msg)


class Presence:
    """Tracks who is around, so a crash or closed laptop lid also shows up
    as "left" once their regular signals stop."""

    def __init__(self):
        self.peers = {}                     # uid -> (name, last time seen)

    def seen(self, msg, now):
        uid = msg.get("uid")
        if not isinstance(uid, str) or not uid:
            return
        if msg.get("type") == "leave":
            self.peers.pop(uid, None)
        else:
            self.peers[uid] = (str(msg.get("name", "?"))[:20], now)

    def refresh_all(self, now):
        """After the computer sleeps, don't announce that everyone left."""
        self.peers = {u: (n, now) for u, (n, _t) in self.peers.items()}

    def expired(self, now, ttl):
        gone = [(u, n) for u, (n, t) in self.peers.items() if now - t > ttl]
        for u, _ in gone:
            del self.peers[u]
        return [n for _, n in gone]


# ------------------------------------------------------------ settings window
class SettingsWindow:
    """Tabs of settings. Changes preview live; Save keeps them, Cancel undoes."""

    def __init__(self, ov):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ov = tk, ov
        self.snapshot = {s[1]: globals()[s[1]] for s in SPEC}
        self.vars, self.swatches = {}, {}
        self.loading = False
        self.job = None
        self._picking = False
        try:
            from tkinter import font as tkfont
            self.font_names = sorted({f for f in tkfont.families(ov.root)
                                      if not f.startswith("@")},
                                     key=str.lower)
        except Exception:
            self.font_names = []
        self.font_lower = {f.lower(): f for f in self.font_names}

        win = self.win = tk.Toplevel(ov.root)
        win.title("Study chat settings")
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self.cancel)

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        tabs = {}
        for name in ("Look", "Window", "Behavior", "Images", "Network"):
            frame = ttk.Frame(nb, padding=10)
            nb.add(frame, text=name)
            tabs[name] = [frame, 0]
        for spec in SPEC:
            self._row(tabs[spec[0]], spec, ttk)
        ttk.Label(tabs["Network"][0], foreground="#b00020",
                  text="These need a restart. Everyone must use the same "
                       "port\nand relay address as each other."
                  ).grid(row=99, column=0, columnspan=2, sticky="w",
                         pady=(10, 0))
        ttk.Label(tabs["Window"][0], foreground="#666666",
                  text="Tip: you can also just drag the top bar to move it."
                  ).grid(row=99, column=0, columnspan=2, sticky="w",
                         pady=(10, 0))

        ttk.Label(win, foreground="#666666",
                  text="Changes preview live. Click Save to keep them."
                  ).pack(anchor="w", padx=12)
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text="Reset to defaults",
                   command=self.reset).pack(side="left")
        ttk.Button(bar, text="Save", command=self.save).pack(side="right")
        ttk.Button(bar, text="Cancel",
                   command=self.cancel).pack(side="right", padx=6)

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        win.focus_force()

    def _fmt(self, key):
        v = globals()[key]
        return f"{v:.2f}" if SPEC_BY_KEY[key][3] == "float" else str(v)

    def _row(self, tab, spec, ttk):
        tk = self.tk
        frame, r = tab[0], tab[1]
        tab[1] += 1
        _t, key, label, kind, lo, hi = spec
        ttk.Label(frame, text=label).grid(row=r, column=0, sticky="w",
                                          pady=3, padx=(0, 14))
        var = tk.StringVar(value=self._fmt(key))
        self.vars[key] = var
        if kind == "color":
            cell = ttk.Frame(frame)
            cell.grid(row=r, column=1, sticky="w")
            sw = tk.Label(cell, width=4, relief="solid", bd=1,
                          cursor="hand2", bg=var.get())
            sw.pack(side="left", padx=(0, 6))
            sw.bind("<Button-1>", lambda e, k=key: self._pick(k))
            self.swatches[key] = sw
            ttk.Entry(cell, textvariable=var, width=10).pack(side="left")
        elif kind in ("int", "float"):
            opts = dict(from_=lo, to=hi, width=10, textvariable=var,
                        increment=1 if kind == "int" else 0.05)
            if kind == "float":
                opts["format"] = "%.2f"
            ttk.Spinbox(frame, **opts).grid(row=r, column=1, sticky="w")
        elif kind == "font":
            # type to search; click a font in the list to choose it
            cell = ttk.Frame(frame)
            cell.grid(row=r, column=1, sticky="w")
            ttk.Entry(cell, textvariable=var, width=34).pack(anchor="w")
            box = ttk.Frame(cell)
            box.pack(anchor="w", pady=(3, 0))
            lb = tk.Listbox(box, height=6, width=36, exportselection=False,
                            activestyle="none")
            sb = ttk.Scrollbar(box, orient="vertical", command=lb.yview)
            lb.config(yscrollcommand=sb.set)
            lb.pack(side="left")
            sb.pack(side="left", fill="y")
            ttk.Label(cell, foreground="#666666",
                      text="Type to search, click a font to choose it.\n"
                           "Empty = same as the Font setting."
                      ).pack(anchor="w", pady=(2, 0))

            def refill(*_a):
                if self._picking:
                    return
                q = var.get().strip().lower()
                lb.delete(0, "end")
                for f in self.font_names:
                    if q in f.lower():
                        lb.insert("end", f)
                cur = var.get().strip().lower()
                for i in range(lb.size()):
                    if lb.get(i).lower() == cur:
                        lb.selection_set(i)
                        lb.see(i)
                        break

            def pick(_e=None):
                sel = lb.curselection()
                if sel:
                    self._picking = True
                    try:
                        var.set(lb.get(sel[0]))
                    finally:
                        self._picking = False

            lb.bind("<<ListboxSelect>>", pick)
            var.trace_add("write", refill)
            refill()
        else:
            ttk.Entry(frame, textvariable=var, width=30).grid(
                row=r, column=1, sticky="w")
        var.trace_add("write", lambda *a, k=key: self._changed(k))

    def _pick(self, key):
        from tkinter import colorchooser
        try:
            _rgb, hexv = colorchooser.askcolor(
                color=self.vars[key].get(), parent=self.win,
                title="Pick a color")
        except Exception:
            _rgb, hexv = colorchooser.askcolor(parent=self.win)
        if hexv:
            self.vars[key].set(hexv)

    def _changed(self, key):
        if self.loading:
            return
        spec = SPEC_BY_KEY[key]
        val = validate(spec, self.vars[key].get())
        if val is not None and spec[3] == "font" and val and self.font_lower:
            val = self.font_lower.get(val.lower())   # only real fonts apply
        if val is None:                      # half-typed or junk: ignore
            return
        set_value(key, val)
        if spec[3] == "color" and key in self.swatches:
            self.swatches[key].config(bg=val)
        if self.job:
            self.win.after_cancel(self.job)
        self.job = self.win.after(250, self.ov.apply_settings)

    def _load_all(self, values):
        self.loading = True
        for key, val in values.items():
            set_value(key, val)
            self.vars[key].set(self._fmt(key))
            if key in self.swatches:
                self.swatches[key].config(bg=val)
        self.loading = False
        self.ov.apply_settings()

    def reset(self):
        self._load_all(DEFAULTS)

    def cancel(self):
        self._load_all(self.snapshot)
        self.close()

    def save(self):
        ok = save_settings()
        self.close()
        if not ok:
            self.ov.note("couldn't save your settings file")

    def close(self):
        if self.job:
            try:
                self.win.after_cancel(self.job)
            except Exception:
                pass
        self.ov.settings_win = None
        self.ov.busy = False
        self.win.destroy()
        self.ov._focus_entry()


# ------------------------------------------------------------------------ UI
class Overlay:
    def __init__(self, root, net, inbox):
        import tkinter as tk
        self.tk = tk

        class SafeText(tk.Text):
            def insert(self, index, chars, *args):
                try:
                    return super().insert(index, chars, *args)
                except tk.TclError:          # emoji on old Tk versions
                    return super().insert(index, bmp(chars), *args)

        self.root, self.net, self.inbox = root, net, inbox
        root.report_callback_exception = self._on_error
        self.last_tick = time.time()
        self.tick_n = 0
        self.history = []
        self.state = "collapsed"
        self.popup_until = 0
        self.last_activity = 0
        self.busy = False
        self.settings_win = None
        self._focus_job = None
        self.font_tags = {}                 # text tag -> (family, bold, color)
        try:
            self.old_tk = str(root.tk.call("info", "patchlevel")
                              ).startswith("8.5")
        except Exception:
            self.old_tk = False
        self.anims = []                     # animated GIFs now in the chat
        self._installed = None              # fonts on this computer
        self.font_warned = set()
        self.full_anims = []                # ...and in full-size viewers
        self.presence = Presence()
        self.last_ping = 0
        self.start_time = time.time()      # first-join roll call
        self.ready_at = None
        self.roll_sent = 0
        self.roll_done = False
        self.last_reply = 0
        self.reply_seq = 0
        self.update_info = None            # newer version found on GitHub

        if root.tk.call("tk", "windowingsystem") == "aqua":
            # Aqua treats overrideredirect windows as non-activating and
            # ignores their focus requests. Hide the title bar while keeping
            # a normal window that macOS can give keyboard focus to.
            root.tk.call("tk::unsupported::MacWindowStyle", "style",
                         root._w, "document", ("noTitleBar",))
        elif (sys.platform.startswith("linux")
              and os.environ.get("STUDYCHAT_BORDERLESS") != "1"):
            # Most Linux desktops (GNOME/Fedora, Wayland) never give keyboard
            # focus to windows with no title bar, so typing is impossible.
            # Use a normal window instead. If your desktop handles borderless
            # windows fine, set STUDYCHAT_BORDERLESS=1 to get the slim look.
            root.title("Study chat")
        else:
            root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)

        # anchor = bottom-left corner, so growing/shrinking keeps it in place
        self.anchor_x = ANCHOR_X
        self.anchor_bottom = root.winfo_screenheight() - BOTTOM_MARGIN

        # pieces
        self.pill = tk.Label(root, text=PILL_LABEL, bg=PILL_BG, fg=PILL_FG,
                             font=F(3, True), cursor="hand2")
        self.pill.bind("<Button-1>", lambda e: self.set_state("active"))
        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="Settings...",
                              command=self.open_settings)
        self.menu.add_command(label="Instagram reels window",
                              command=self.open_reels)
        self.menu.add_command(label="Check for updates",
                              command=self.update_cmd)
        self.menu.add_command(label="Quit", command=root.destroy)
        for b in ("<Button-2>", "<Button-3>"):
            self.pill.bind(b, lambda e: self.menu.tk_popup(e.x_root, e.y_root))

        self.header = tk.Frame(root, bg=BAR)
        self.title = tk.Label(self.header, bg=BAR, fg=MUTED,
                              text=f"{net.room}  -  {net.name}  ({net.mode})"
                                   + ("" if PIL_OK else "  (no Pillow)"),
                              font=F(-2))
        self.title.pack(side="left", padx=6, pady=2)
        self.close_lbl = tk.Label(self.header, text="x", bg=BAR, fg=MUTED,
                                  cursor="hand2", font=F(-1))
        self.close_lbl.pack(side="right", padx=6)
        self.close_lbl.bind("<Button-1>",
                            lambda e: self.set_state("collapsed"))
        self.settings_lbl = tk.Label(self.header, text="settings", bg=BAR,
                                     fg=MUTED, cursor="hand2", font=F(-2))
        self.settings_lbl.pack(side="right", padx=6)
        self.settings_lbl.bind("<Button-1>", lambda e: self.open_settings())
        self.reels_lbl = tk.Label(self.header, text="reels", bg=BAR,
                                  fg=MUTED, cursor="hand2", font=F(-2))
        self.reels_lbl.pack(side="right", padx=6)
        self.reels_lbl.bind("<Button-1>", lambda e: self.open_reels())
        self.online_lbl = tk.Label(self.header, text="checking...", bg=BAR,
                                   fg=MUTED, cursor="hand2", font=F(-2))
        self.online_lbl.pack(side="right", padx=6)
        self.online_lbl.bind("<Button-1>", lambda e: self.show_who())
        self.update_lbl = tk.Label(self.header, text="", bg=BAR,
                                   fg="#7be08a", cursor="hand2", font=F(-2))
        self.update_lbl.bind("<Button-1>", lambda e: self.update_cmd())
        for w in (self.header, self.title):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        self.text = SafeText(root, bg=BG, fg=FG, bd=0, highlightthickness=0,
                            wrap="word", font=F(), padx=6, pady=4,
                            state="disabled", cursor="arrow")
        self.text.tag_config("sys", foreground=MUTED)
        self.text.bind("<Button-1>", self._on_text_click)

        self.entry_wrap = tk.Frame(root, bg=BAR)
        self.plus = tk.Label(self.entry_wrap, text="+", bg=BAR, fg=FG,
                             cursor="hand2", font=F(3, True))
        self.plus.pack(side="right", padx=8)
        self.plus.bind("<Button-1>", lambda e: self.pick_image())
        self.entry = tk.Entry(self.entry_wrap, bg=BAR, fg=FG, bd=0,
                              insertbackground=FG, font=F(),
                              highlightthickness=0)
        self.entry.pack(side="left", fill="x", expand=True, padx=6, pady=5)
        self.entry.bind("<Return>", self._on_send)
        self.entry.bind("<Escape>", lambda e: self.set_state("collapsed"))
        self.entry.bind("<Key>", lambda e: self._touch())
        self.entry.bind("<Button-1>", self._focus_entry)
        self.entry.bind("<Map>", self._focus_entry)
        for seq in ("<Control-v>", "<Control-V>", "<Command-v>"):
            try:
                self.entry.bind(seq, self._on_paste)
                self.text.bind(seq, self._on_paste)
            except Exception:
                pass

        self.set_state("collapsed")
        self.root.after(100, self.poll)
        self.root.after(500, self.tick)
        self.root.after(60, self._animate)

    # ---- geometry / state
    def _place(self, w, h):
        x, y = self.anchor_x, self.anchor_bottom - h
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _geometry(self):
        """Size, position and opacity for the current state."""
        if self.state == "collapsed":
            self._place(PILL_W, PILL_H)
            alpha = PILL_ALPHA
        elif self.state == "popup":
            last = self.history[-1] if self.history else {}
            self._place(WIDTH, POPUP_IMG_HEIGHT
                        if last.get("type") == "img" else POPUP_HEIGHT)
            alpha = POPUP_ALPHA
        else:
            self._place(WIDTH, ACTIVE_HEIGHT)
            alpha = ACTIVE_ALPHA
        self.root.attributes("-alpha", alpha)

    def set_state(self, state):
        if self._focus_job is not None:
            self.root.after_cancel(self._focus_job)
            self._focus_job = None
        self.state = state
        for w in (self.pill, self.header, self.text, self.entry_wrap):
            w.pack_forget()
        if state == "collapsed":
            self.pill.pack(fill="both", expand=True)
            self._geometry()
        elif state == "popup":
            self.text.pack(fill="both", expand=True)
            self._geometry()
            self.redraw()
        else:
            self.header.pack(fill="x")
            self.entry_wrap.pack(side="bottom", fill="x")
            self.text.pack(fill="both", expand=True)
            self._geometry()
            self.redraw()
            self._touch()
            self.root.lift()
            self._focus_entry()

    def _focus_entry(self, _e=None):
        """Restore typing after geometry and default mouse bindings finish."""
        if self.state != "active" or self.busy:
            return
        self._touch()
        if self._focus_job is not None:
            self.root.after_cancel(self._focus_job)
        self._focus_job = self.root.after_idle(self._restore_entry_focus)

    def _restore_entry_focus(self):
        self._focus_job = None
        if (self.state == "active" and not self.busy
                and self.entry.winfo_viewable()):
            self.entry.focus_force()

    def apply_settings(self):
        """Re-style everything after a setting changes (no focus changes)."""
        self.root.configure(bg=BG)
        self.pill.config(text=PILL_LABEL, bg=PILL_BG, fg=PILL_FG,
                         font=F(3, True))
        self.header.config(bg=BAR)
        self.title.config(bg=BAR, fg=MUTED, font=F(-2))
        self.close_lbl.config(bg=BAR, fg=MUTED, font=F(-1))
        self.settings_lbl.config(bg=BAR, fg=MUTED, font=F(-2))
        self.reels_lbl.config(bg=BAR, fg=MUTED, font=F(-2))
        self.online_lbl.config(bg=BAR, fg=MUTED, font=F(-2))
        self.text.config(bg=BG, fg=FG, font=F())
        self.text.tag_config("sys", foreground=MUTED)
        self.entry_wrap.config(bg=BAR)
        self.plus.config(bg=BAR, fg=FG, font=F(3, True))
        self.entry.config(bg=BAR, fg=FG, insertbackground=FG, font=F())
        for tag, (fam, bold, color) in self.font_tags.items():
            self._config_tag(tag, fam, bold, color)
        for m in self.history:               # thumbnails may change size
            m.pop("_photo", None)
            m.pop("_anim", None)
        self.anchor_x = ANCHOR_X
        self.anchor_bottom = self.root.winfo_screenheight() - BOTTOM_MARGIN
        self._geometry()
        self.redraw()

    def _config_tag(self, tag, family, bold, color):
        font = (family, max(6, FONT_SIZE)) + (("bold",) if bold else ())
        opts = {"font": font}
        if color:
            opts["foreground"] = color
        self.text.tag_config(tag, **opts)

    def _font_tag(self, family, bold=False, color=None, name=""):
        """A text tag that draws in one person's chosen font."""
        tag = ("n_" if bold else "t_") + name + "|" + family
        if tag not in self.font_tags:
            self.font_tags[tag] = (family, bold, color)
            self._config_tag(tag, family, bold, color)
        return tag

    def open_reels(self, link=""):
        """Small Instagram window (/reels, or the "reels" button)."""
        url = reels_url(link)
        if url is None:
            self.note("use:  /reels  or  /reels https://www.instagram.com/...")
            return
        old = getattr(self, "reels_proc", None)
        if old is not None and old.poll() is None:
            old.terminate()                  # replace it (new link or retry)
        exe = find_chromium()
        if exe is not None:
            # Chrome/Edge "app" mode: a bare phone-sized window that uses
            # your normal browser profile, so you are already logged in to
            # Instagram if you are in that browser. (No custom user agent
            # here: it would change your whole browser, and Instagram
            # switches to its phone layout at this width anyway.)
            x = max(0, self.root.winfo_screenwidth() - 420)
            cmd = exe + [f"--app={url}", "--window-size=390,720",
                         f"--window-position={x},40"]
            note = ""
        elif importlib.util.find_spec("webview") is not None:
            cmd = [sys.executable, os.path.abspath(__file__), "--reels", url]
            note = ("this small window can't use your browser's logins, so "
                    "log in to Instagram once in it")
        else:                                # nothing small is possible
            webbrowser.open(url)
            self.note("opened in your normal browser (so you're logged in). "
                      "For a small phone-sized window, install Chrome, "
                      "Chromium, Edge or Brave"
                      + (" (on Fedora: sudo dnf install chromium)"
                         if sys.platform.startswith("linux") else "") + ".")
            return
        try:
            self.reels_proc = subprocess.Popen(cmd)
            if note:
                self.note(note)
        except Exception:
            log("reels start failed: " + traceback.format_exc())
            self.note("couldn't open the reels window")

    def open_settings(self):
        if self.settings_win is not None:
            try:
                self.settings_win.win.lift()
                return
            except Exception:
                self.settings_win = None
        if self.state != "active":
            self.set_state("active")
        self.busy = True
        try:
            self.settings_win = SettingsWindow(self)
        except Exception:
            self.busy = False
            self.settings_win = None
            self.note("couldn't open settings")

    def online_names(self):
        """Everyone we know is in the room right now, you first."""
        others = sorted(n for n, _t in self.presence.peers.values())
        return [f"{self.net.name} (you)"] + others

    def update_online(self):
        n = len(self.online_names())
        if n == 1 and not self.roll_done:
            text = "checking..."           # still asking who's here
        else:
            text = f"{n} online"
        if self.online_lbl.cget("text") != text:
            self.online_lbl.config(text=text)

    def _reply_roll(self):
        """Someone joined or asked who's here: answer so they can list us.
        A small random delay stops everyone answering in the same instant."""
        now = time.time()
        if now - self.last_reply < 1.5:
            return
        self.last_reply = now
        top = 2000 if self.net.mode == "online" else 250
        self.reply_seq += 1
        seq = self.reply_seq

        def go():
            if seq != self.reply_seq:        # someone else already answered
                return
            roster = [{"uid": u, "name": n} for u, (n, _t)
                      in list(self.presence.peers.items())[:40]]
            self.net.send("", kind="ping", extra={"roster": roster})
        self.root.after(random.randint(0, top), go)

    # ---- updates
    def start_update_check(self):
        if not CHECK_UPDATES:
            return
        threading.Thread(target=self._update_worker, args=(False,),
                         daemon=True).start()

    def _update_worker(self, manual):
        try:
            info = check_for_update()
        except Exception:
            if manual:
                self.inbox.put({"type": "sys", "name": "", "text":
                                "couldn't check for updates (no internet "
                                "or GitHub is busy)"})
            return
        if info:
            self.inbox.put({"type": "update_found", "info": info})
        elif manual:
            self.inbox.put({"type": "sys", "name": "", "text":
                            f"you're up to date (v{VERSION})"})

    def _install_worker(self, info):
        try:
            ver = install_update(info)
            self.inbox.put({"type": "update_done", "version": ver})
        except Exception as ex:
            log("update failed: " + traceback.format_exc())
            self.inbox.put({"type": "sys", "name": "", "text":
                            f"update failed ({str(ex)[:60]}); nothing "
                            "was changed"})

    def update_cmd(self):
        """Menu, header link, or /update."""
        if self.update_info is None:
            self.note("checking for updates...")
            threading.Thread(target=self._update_worker, args=(True,),
                             daemon=True).start()
            return
        from tkinter import messagebox
        info = self.update_info
        self.busy = True
        try:
            ok = messagebox.askyesno(
                "Study chat",
                f"Update from v{VERSION} to v{info['version']}?\n\n"
                f"This downloads the new studychat.py from GitHub "
                f"({UPDATE_REPO}) and replaces this file. Your old copy is "
                "kept as studychat.py.bak.", parent=self.root)
        finally:
            self.busy = False
        if ok:
            self.note("downloading update...")
            threading.Thread(target=self._install_worker, args=(info,),
                             daemon=True).start()

    def _on_update_done(self, ver):
        from tkinter import messagebox
        self.update_info = None
        self.update_lbl.pack_forget()
        self.busy = True
        try:
            again = messagebox.askyesno(
                "Study chat", f"Updated to v{ver}. Restart now?",
                parent=self.root)
        finally:
            self.busy = False
        if not again:
            self.note(f"updated to v{ver}; it takes effect next time you "
                      "start the chat")
            return
        args = [sys.executable, os.path.abspath(__file__),
                "--name", self.net.name, "--room", self.net.room,
                "--online" if self.net.mode == "online" else "--lan"]
        try:
            subprocess.Popen(args)
            self.root.destroy()
        except Exception:
            self.note("couldn't restart by itself; please close and reopen")

    def show_who(self):
        self.note("Online: " + ", ".join(self.online_names()))

    def show_who_popup(self):
        """On joining, list who's here (and pop the window open briefly)."""
        self._deliver({"type": "sys", "name": "", "text":
                       "Online: " + ", ".join(self.online_names())})

    def _on_text_click(self, e):
        if any(tag.startswith("img_") for tag in
               self.text.tag_names(f"@{e.x},{e.y}")):
            # The image tag opens a viewer; leave focus with that window.
            return "break"
        if self.state != "active":
            self.set_state("active")
        else:
            # Text's default click binding takes focus even when disabled.
            # Restore it afterwards, retaining normal history selection.
            self._focus_entry()

    def _touch(self):
        self.last_activity = time.time()

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root, e.y_root

    def _drag_move(self, e):
        self.anchor_x += e.x_root - self._dx
        self.anchor_bottom += e.y_root - self._dy
        self._dx, self._dy = e.x_root, e.y_root
        self._place(WIDTH, ACTIVE_HEIGHT)

    def _drag_end(self, _e):
        """Remember where the window was dropped."""
        global ANCHOR_X, BOTTOM_MARGIN
        ANCHOR_X = max(0, int(self.anchor_x))
        BOTTOM_MARGIN = max(0, int(self.root.winfo_screenheight()
                                   - self.anchor_bottom))
        if self.settings_win is None:
            save_settings()

    # ---- images
    def _pil_photo(self, im):
        if ImageTk is not None:
            return ImageTk.PhotoImage(im)
        b = io.BytesIO()
        im.convert("RGBA").save(b, "PNG")
        return self.tk.PhotoImage(master=self.root,
                                  data=base64.b64encode(b.getvalue()))

    def make_anim(self, data, max_w, max_h):
        """Frames for an animated GIF, or None if it isn't animated."""
        if not data.startswith(b"GIF8"):
            return None
        frames, delays = [], []
        try:
            if PIL_OK:
                im = Image.open(io.BytesIO(data))
                n = getattr(im, "n_frames", 1)
                if n < 2 or n > MAX_GIF_FRAMES:
                    return None
                for k in range(n):
                    im.seek(k)
                    fr = im.convert("RGBA")
                    fr.thumbnail((max_w, max_h))
                    frames.append(self._pil_photo(fr))
                    delays.append(max(20, int(im.info.get("duration", 100))))
            else:
                b64 = base64.b64encode(data)
                k = 0
                while k <= MAX_GIF_FRAMES:
                    try:
                        frames.append(self.tk.PhotoImage(
                            master=self.root, data=b64,
                            format=f"gif -index {k}"))
                    except self.tk.TclError:
                        break
                    k += 1
                if len(frames) < 2 or k > MAX_GIF_FRAMES:
                    return None
                f = max(1, -(-frames[0].width() // max_w),
                        -(-frames[0].height() // max_h))
                if f > 1:
                    frames = [p.subsample(f) for p in frames]
                dl = gif_delays(data)
                delays = [dl[i] if i < len(dl) else 100
                          for i in range(len(frames))]
            disp = self.tk.PhotoImage(master=self.root)
            self.root.tk.call(str(disp), "copy", str(frames[0]))
            return {"disp": disp, "frames": frames, "delays": delays,
                    "i": 0, "next": time.time() + delays[0] / 1000}
        except Exception:
            log("make_anim failed: " + traceback.format_exc())
            return None

    def _animate(self):
        try:
            now = time.time()
            if self.state != "collapsed":
                self.full_anims[:] = [a for a in self.full_anims
                                      if a["widget"].winfo_exists()]
                for a in self.anims + self.full_anims:
                    if now >= a["next"]:
                        a["i"] = (a["i"] + 1) % len(a["frames"])
                        self.root.tk.call(str(a["disp"]), "copy",
                                          str(a["frames"][a["i"]]))
                        a["next"] = now + a["delays"][a["i"]] / 1000
        except Exception:
            log("animate failed: " + traceback.format_exc())
        finally:
            self.root.after(30, self._animate)

    def make_photo(self, data, max_w, max_h):
        try:
            if PIL_OK:
                im = Image.open(io.BytesIO(data))
                im.thumbnail((max_w, max_h))
                if ImageTk is not None:
                    return ImageTk.PhotoImage(im)
                b = io.BytesIO()
                im.convert("RGBA").save(b, "PNG")
                return self.tk.PhotoImage(data=base64.b64encode(b.getvalue()))
            p = self.tk.PhotoImage(data=base64.b64encode(data))
            f = max(1, -(-p.width() // max_w), -(-p.height() // max_h))
            return p.subsample(f) if f > 1 else p
        except Exception:
            return None

    def open_full(self, data):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        anim = self.make_anim(data, int(sw * 0.8), int(sh * 0.8))
        photo = anim["disp"] if anim else self.make_photo(
            data, int(sw * 0.8), int(sh * 0.8))
        if photo is None:
            return
        top = self.tk.Toplevel(self.root)
        top.title("Image")
        top.configure(bg=BG)
        top.attributes("-topmost", True)
        lbl = self.tk.Label(top, image=photo, bg=BG, cursor="hand2")
        lbl.image = photo
        lbl.pack()
        if anim:
            anim["widget"] = lbl
            self.full_anims.append(anim)

        def close(_e=None):
            top.destroy()
            self._focus_entry()
            return "break"

        for w in (top, lbl):
            w.bind("<Button-1>", close)
        top.bind("<Escape>", close)
        top.protocol("WM_DELETE_WINDOW", close)
        top.focus_force()

    def push_image(self, data):
        msg = self.net.send_image(data)
        self.add(msg)
        self._touch()
        self.redraw()

    def note(self, text):
        self.add({"type": "sys", "name": "", "text": text})
        self.redraw()

    def send_pil(self, im):
        try:
            im.load()
            if max(im.size) > SEND_MAX_DIM:
                im.thumbnail((SEND_MAX_DIM, SEND_MAX_DIM))
            buf = io.BytesIO()
            if im.mode in ("RGBA", "LA", "P"):
                im.save(buf, "PNG")
            else:
                im.convert("RGB").save(buf, "JPEG", quality=85)
            data = buf.getvalue()
            if len(data) > MAX_IMAGE_BYTES:
                buf = io.BytesIO()
                im.convert("RGB").save(buf, "JPEG", quality=70)
                data = buf.getvalue()
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("too big")
        except Exception:
            self.note("couldn't send that image")
            return False
        self.push_image(data)
        return True

    def send_gif(self, data):
        """Send a GIF as it is, so it keeps moving. Too big? Shrink it."""
        if len(data) > MAX_IMAGE_BYTES:
            data = shrink_gif(data, MAX_IMAGE_BYTES)
            if data is None:
                self.note("that GIF is too big to send"
                          + ("" if PIL_OK else
                             " (install Pillow so it can be shrunk)"))
                return False
        self.push_image(data)
        return True

    def send_file(self, path):
        path = path.strip().strip('"').strip("'")
        try:
            with open(path, "rb") as f:
                head = f.read(8)
                if head.startswith(b"GIF8"):
                    f.seek(0)
                    return self.send_gif(f.read(40 * 1024 * 1024))
            if PIL_OK:
                return self.send_pil(Image.open(path))
            with open(path, "rb") as f:
                data = f.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES or not (
                    data.startswith(b"\x89PNG") or data.startswith(b"GIF8")):
                raise ValueError("unsupported")
        except Exception:
            self.note("couldn't open that image" + (
                "" if PIL_OK else " (install Pillow for more than PNG/GIF)"))
            return False
        self.push_image(data)
        return True

    def send_gif_link(self, url):
        """/gif <direct link to a .gif file>"""
        if not url.lower().startswith(("http://", "https://")):
            self.note("use:  /gif https://.../funny.gif  (a direct link; on "
                      "most sites, right-click the GIF and copy image address)")
            return
        self.note("fetching GIF...")

        def work():
            try:
                data = _http_get(url, timeout=20, limit=30 * 1024 * 1024)
            except Exception:
                self.inbox.put({"type": "sys", "name": "", "text":
                                "couldn't download that link"})
                return
            if not data.startswith(b"GIF8"):
                self.inbox.put({"type": "sys", "name": "", "text":
                                "that link isn't a GIF file (it needs to end "
                                "in .gif, not be a web page)"})
                return
            self.inbox.put({"type": "gif_ready", "data": data})
        threading.Thread(target=work, daemon=True).start()

    def pick_image(self):
        from tkinter import filedialog
        self.busy = True
        try:
            path = filedialog.askopenfilename(
                parent=self.root, title="Send an image",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                           ("All files", "*.*")])
        finally:
            self.busy = self.settings_win is not None
            self._touch()
        if path:
            self.send_file(path)
        self.root.lift()
        self._focus_entry()

    def _clip_text(self):
        try:
            return self.root.clipboard_get() or ""
        except Exception:
            return ""

    def _paste_text(self, text):
        """Put text into the typing box ourselves, instead of letting Tk do
        it. Old Macs crash on some characters (emoji) when Tk pastes them."""
        text = re.sub(r"[\r\n\t]+", " ", text)
        text = "".join(c for c in text if c.isprintable())[:1000]
        if self.old_tk:
            text = bmp(text)
        if not text:
            return
        try:
            self.entry.delete("sel.first", "sel.last")   # replace selection
        except Exception:
            pass
        self.entry.insert("insert", text)

    def _on_paste(self, _e=None):
        try:
            # Text first: it's instant, and it never starts another program
            # (the image check below does, and that can upset a Mac).
            text = self._clip_text()
            if text.strip():
                path = text.strip().strip('"').strip("'")
                if ("\n" not in path and os.path.isfile(path) and
                        path.lower().endswith((".png", ".jpg", ".jpeg", ".gif",
                                               ".bmp", ".webp"))):
                    self.send_file(path)         # a copied image file
                else:
                    self._paste_text(text)
                return "break"
            if not PIL_OK:
                self.note("to paste images, run:  python -m pip install "
                          "pillow  then restart the app")
                return "break"
            err = None
            try:
                clip = ImageGrab.grabclipboard()
            except Exception as ex:
                clip, err = None, str(ex)[:80]
            if clip is None:
                self.note("no image found on the clipboard"
                          + (f" ({err})" if err else ""))
            elif isinstance(clip, list):         # copied image files
                for p in clip[:3]:
                    self.send_file(p)
            else:
                self.send_pil(clip)
        except Exception:
            log("paste failed: " + traceback.format_exc())
        return "break"                           # we handled it, always

    # ---- content
    def _on_error(self, exc, val, tb):
        log("callback error: "
            + "".join(traceback.format_exception(exc, val, tb)))

    def redraw(self):
        try:
            self._redraw()
        except Exception:
            log("redraw failed: " + traceback.format_exc())
        finally:
            try:                             # never leave the chat editable
                self.text.config(state="disabled")
                self.text.see("end")
            except Exception:
                pass

    def _redraw(self):
        t = self.text
        t.config(state="normal")
        t.delete("1.0", "end")
        msgs = self.history[-(POPUP_LINES if self.state == "popup" else MAX_HISTORY):]
        self.anims = []
        gifs = [m for m in msgs if m.get("type") == "img"
                and isinstance(m.get("data"), bytes)
                and m["data"].startswith(b"GIF8")]
        live = {id(m) for m in gifs[-LIVE_GIFS:]}     # older ones hold still
        for m in gifs:
            if id(m) not in live:
                m.pop("_anim", None)
        for m in msgs:
            kind = m.get("type")
            if kind in ("join", "leave"):
                word = "joined" if kind == "join" else "left"
                t.insert("end", f"{m['name']} {word}\n", "sys")
                continue
            if kind == "sys":
                t.insert("end", m.get("text", "") + "\n", "sys")
                continue
            if m.get("uid") == self.net.uid:      # mine: always my current font
                fam = MY_FONT or FONT_FAMILY
            else:                                 # theirs: the font they chose
                fam = m.get("font") or FONT_FAMILY
            tag = self._font_tag(fam, True, name_color(m["name"]), m["name"])
            ttag = self._font_tag(fam)
            t.insert("end", m["name"] + ": ", tag)
            if kind == "img" and isinstance(m.get("data"), bytes):
                if id(m) in live and "_anim" not in m:
                    m["_anim"] = self.make_anim(m["data"], THUMB_W, THUMB_H)
                anim = m.get("_anim") if id(m) in live else None
                if anim:
                    self.anims.append(anim)
                elif "_photo" not in m:
                    m["_photo"] = self.make_photo(m["data"], THUMB_W, THUMB_H)
                shown = anim["disp"] if anim else m.get("_photo")
                t.insert("end", "\n")
                if shown is not None:
                    itag = "img_" + str(m.get("id"))
                    start = t.index("end-1c")
                    t.image_create(start, image=shown, padx=2, pady=2)
                    t.tag_add(itag, start, f"{start}+1c")
                    t.tag_bind(itag, "<Button-1>",
                               lambda e, d=m["data"]: self.open_full(d))
                    t.tag_bind(itag, "<Enter>",
                               lambda e: t.config(cursor="hand2"))
                    t.tag_bind(itag, "<Leave>",
                               lambda e: t.config(cursor="arrow"))
                else:
                    t.insert("end", "(image couldn't be shown)", "sys")
                t.insert("end", "\n")
            else:
                t.insert("end", m.get("text", "") + "\n", ttag)
        t.config(state="disabled")
        t.see("end")

    def add(self, msg):
        self.history.append(msg)
        del self.history[:-MAX_HISTORY]

    def _on_send(self, _e):
        text = self.entry.get().strip()
        self.entry.delete(0, "end")
        self._touch()
        if not text:
            return
        if text == "/quit":
            self.root.destroy()
            return
        if text == "/settings":
            self.open_settings()
            return
        if text == "/who":
            self.show_who()
            return
        if text in ("/update", "/version"):
            if text == "/version":
                self.note(f"studychat v{VERSION}")
            self.update_cmd()
            return
        if text.startswith("/img "):
            self.send_file(text[5:])
            return
        if text == "/reels" or text.startswith("/reels "):
            self.open_reels(text[6:])
            return
        if text.startswith("/gif "):
            self.send_gif_link(text[5:].strip())
            return
        self.add(self.net.send(text, extra={"font": MY_FONT}
                               if MY_FONT else None))
        self.last_ping = time.time()        # a message already says "here"
        self.redraw()

    # ---- loops
    def poll(self):
        # One bad message must never stop the loop, or the chat looks frozen.
        try:
            while True:
                try:
                    msg = self.inbox.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle_incoming(msg)
                except Exception:
                    log("bad incoming message: " + traceback.format_exc())
            self.update_online()
        except Exception:
            log("poll failed: " + traceback.format_exc())
        finally:
            self.root.after(100, self.poll)

    def _usable_font(self, family, who):
        """The font to draw someone's message in. If it isn't installed on
        this computer, use our normal font and say so once."""
        if self._installed is None:
            try:
                from tkinter import font as tkfont
                self._installed = {f.lower() for f in
                                   tkfont.families(self.root)}
            except Exception:
                self._installed = set()
        if not self._installed or family.lower() in self._installed:
            return family
        if (who, family.lower()) not in self.font_warned:
            self.font_warned.add((who, family.lower()))
            self.add({"type": "sys", "name": "", "text":
                      f"{who} uses the font \"{family}\", which isn't "
                      "installed on this computer, so you see the normal "
                      "font."})
        return ""

    def _handle_incoming(self, msg):
        if msg.get("type") == "summon":
            self.set_state("active")
            return
        if msg.get("type") == "update_found":
            info = msg.get("info") or {}
            if self.update_info is None and info.get("version"):
                self.update_info = info
                self.update_lbl.config(text=f"update v{info['version']}")
                self.update_lbl.pack(side="right", padx=6)
                self._deliver({"type": "sys", "name": "", "text":
                               f"Update available: v{info['version']} "
                               f"(you have v{VERSION}). Click \"update\" in "
                               "the top bar or type /update."})
            return
        if msg.get("type") == "gif_ready":
            self.send_gif(msg["data"])
            return
        if msg.get("type") == "update_done":
            self._on_update_done(str(msg.get("version", "")))
            return
        msg["name"] = str(msg.get("name", "?"))[:20]
        msg["text"] = str(msg.get("text", ""))[:2000]
        msg["font"] = "".join(c for c in str(msg.get("font", ""))
                              if c.isprintable())[:60].strip()
        if msg["font"] and msg.get("uid") != self.net.uid:
            msg["font"] = self._usable_font(msg["font"], msg["name"])
        self.presence.seen(msg, time.time())
        roster = msg.get("roster")
        if (msg.get("type") == "ping" and isinstance(roster, list)
                and msg.get("uid") != self.net.uid):
            self.reply_seq += 1              # they answered, so we needn't
            if not self.roll_done:           # newcomer: learn who else is here
                for it in roster[:50]:
                    if not isinstance(it, dict):
                        continue
                    u, n = it.get("uid"), str(it.get("name", "?"))[:20]
                    if (isinstance(u, str) and u and u != self.net.uid
                            and u not in self.presence.peers):
                        self.presence.peers[u] = (n, time.time())
        if msg.get("uid") != self.net.uid and (
                msg.get("type") == "join"
                or (msg.get("type") == "ping" and msg.get("text") == "who")):
            # say hi back so the newcomer sees who's here
            self._reply_roll()
        if msg.get("type") == "ping":          # quiet "still here" signal
            return
        self._deliver(msg)

    def _deliver(self, msg):
        self.add(msg)
        if self.state == "active":
            self.redraw()
        else:
            self.popup_until = time.time() + POPUP_SECONDS
            self.set_state("popup")

    def tick(self):
        # Wrapped so an error can't stop the timer (that would leave popups
        # stuck open and the chat looking frozen).
        try:
            now = time.time()
            late = now - self.last_tick
            self.last_tick = now
            if late > 5:                     # computer slept or app was frozen
                log(f"timer was {late:.0f}s late (sleep, or the system "
                    "slowed the app down)")
                self.presence.refresh_all(now)
                self.last_ping = 0
            # first-join roll call: ask who's here (again if nobody answered)
            if self.ready_at is None and getattr(self.net, "connected", True):
                self.ready_at = now
            if self.ready_at is not None and not self.roll_done:
                waited = now - self.ready_at
                alone = len(self.presence.peers) == 0
                if (alone and self.roll_sent < (2 if self.net.mode == "online" else 3)
                        and waited >= (0.3, 3.0, 8.0)[self.roll_sent]):
                    self.roll_sent += 1
                    self.net.send("who", kind="ping")
                if waited > 3.5:
                    self.roll_done = True
                    self.update_online()
                    self.show_who_popup()
            if not self.roll_done and now - self.start_time > 15:
                self.roll_done = True               # offline: stop waiting
                self.update_online()
            # tell others we're still here, and notice when someone stops
            if now - self.last_ping > self.net.ping_every:
                self.last_ping = now
                self.net.send("", kind="ping")
            for pname in self.presence.expired(now, 3 * self.net.ping_every):
                self._deliver({"type": "leave", "name": pname, "text": ""})
            if self.state == "popup" and now > self.popup_until:
                self.set_state("collapsed")
            elif (self.state == "active" and not self.busy
                  and not self.entry.get()
                  and now - self.last_activity > ACTIVE_IDLE_SECONDS):
                self.set_state("collapsed")
            # keep sitting above other windows (every couple of seconds)
            self.tick_n += 1
            if self.tick_n % 4 == 0:
                self.root.attributes("-topmost", True)
        except Exception:
            log("tick failed: " + traceback.format_exc())
        finally:
            self.root.after(500, self.tick)


# --------------------------------------------------------------------- reels
REELS_HOME = "https://www.instagram.com/reels/"
REELS_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1")


def reels_url(text):
    """A safe Instagram address to open, or None if it isn't Instagram."""
    text = (text or "").strip()
    if not text:
        return REELS_HOME
    try:
        u = urllib.parse.urlparse(text)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if u.scheme in ("http", "https") and (
            host == "instagram.com" or host.endswith(".instagram.com")):
        return text
    return None


def default_browser_hint():
    """'chrome', 'edge' or 'brave' if that is the computer's default
    browser, else ''. Best effort; any problem just means ''."""
    raw = ""
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\https\UserChoice")
            raw = str(winreg.QueryValueEx(key, "ProgId")[0])
        elif sys.platform == "darwin":
            import plistlib
            path = os.path.join(
                os.path.expanduser("~"), "Library", "Preferences",
                "com.apple.LaunchServices",
                "com.apple.launchservices.secure.plist")
            with open(path, "rb") as f:
                for h in plistlib.load(f).get("LSHandlers", []):
                    if h.get("LSHandlerURLScheme") == "https":
                        raw = str(h.get("LSHandlerRoleAll", ""))
                        break
        else:
            raw = subprocess.run(["xdg-settings", "get",
                                  "default-web-browser"],
                                 capture_output=True, text=True,
                                 timeout=3).stdout
    except Exception:
        return ""
    raw = raw.lower()
    for hint, words in (("chrome", ("chrome",)), ("chromium", ("chromium",)),
                        ("edge", ("edge", "msedge")), ("brave", ("brave",))):
        if any(w in raw for w in words):
            return hint
    return ""


# Linux program names and Flatpak ids for Chrome-family browsers
_LINUX_NAMES = (("google-chrome-stable", "chrome"), ("google-chrome", "chrome"),
                ("chromium", "chromium"), ("chromium-browser", "chromium"),
                ("microsoft-edge-stable", "edge"), ("microsoft-edge", "edge"),
                ("brave-browser", "brave"), ("brave-browser-stable", "brave"),
                ("brave", "brave"))
_FLATPAKS = {"com.google.Chrome": "chrome", "org.chromium.Chromium": "chromium",
             "com.brave.Browser": "brave", "com.microsoft.Edge": "edge",
             "io.github.ungoogled_software.ungoogled_chromium": "chromium"}


def find_chromium():
    """The command (a list) that starts Chrome, Edge, Brave or Chromium, or
    None if none is installed. Works on Windows, Mac and Linux (including
    Fedora, with normal, Snap or Flatpak installs). The computer's default
    browser comes first, since that is the one you most likely stay logged
    in to Instagram on."""
    env = os.environ
    cands = []                                   # (which, [command...])
    if sys.platform == "win32":
        for base in (env.get("ProgramFiles"), env.get("ProgramFiles(x86)"),
                     env.get("LocalAppData")):
            if base:
                for hint, parts in (
                        ("edge", ("Microsoft", "Edge", "Application",
                                  "msedge.exe")),
                        ("chrome", ("Google", "Chrome", "Application",
                                    "chrome.exe")),
                        ("brave", ("BraveSoftware", "Brave-Browser",
                                   "Application", "brave.exe"))):
                    p = os.path.join(base, *parts)
                    if os.path.isfile(p):
                        cands.append((hint, [p]))
    elif sys.platform == "darwin":
        for hint, app in (("chrome", "Google Chrome"),
                          ("edge", "Microsoft Edge"),
                          ("brave", "Brave Browser"),
                          ("chromium", "Chromium")):
            p = f"/Applications/{app}.app/Contents/MacOS/{app}"
            if os.path.isfile(p):
                cands.append((hint, [p]))
    else:
        for name, hint in _LINUX_NAMES:
            p = shutil.which(name)
            if p:
                cands.append((hint, [p]))
        if shutil.which("flatpak"):              # common on Fedora
            try:
                out = subprocess.run(
                    ["flatpak", "list", "--app", "--columns=application"],
                    capture_output=True, text=True, timeout=6).stdout
                for app_id in out.split():
                    if app_id in _FLATPAKS:
                        cands.append((_FLATPAKS[app_id],
                                      ["flatpak", "run", app_id]))
            except Exception:
                pass
    want = default_browser_hint()
    cands.sort(key=lambda c: c[0] != want)       # stable: default first
    return cands[0][1] if cands else None


def run_reels(url):
    """A small always-on-top browser window for Instagram (own process, since
    pywebview wants to run on its own main thread). Needs: pip install
    pywebview. You log in once; it remembers you."""
    import webview
    webview.create_window("Reels", url, width=390, height=720, on_top=True)
    storage = os.path.join(os.path.expanduser("~"), ".studychat_web")
    for kw in ({"private_mode": False, "storage_path": storage,
                "user_agent": REELS_UA},
               {"private_mode": False, "storage_path": storage}, {}):
        try:
            webview.start(**kw)          # older pywebview: fewer options
            return
        except TypeError:
            continue


def main():
    import tkinter as tk
    from tkinter import simpledialog

    load_settings()

    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--room")
    ap.add_argument("--online", action="store_true",
                    help="use the internet relay (works on school wifi)")
    ap.add_argument("--lan", action="store_true",
                    help="same-wifi mode (needs a network that allows it)")
    ap.add_argument("--reels", nargs="?", const=REELS_HOME,
                    help="open just the small Instagram window")
    args = ap.parse_args()
    if args.reels is not None:
        try:
            run_reels(reels_url(args.reels) or REELS_HOME)
        except Exception:
            log("reels window failed: " + traceback.format_exc())
        return

    root = tk.Tk()
    root.withdraw()
    online = args.online
    if not args.online and not args.lan:
        from tkinter import messagebox
        online = messagebox.askyesno(
            "Study chat",
            "Use online mode?\n\n"
            "Yes = works on school wifi (goes through the internet)\n"
            "No = same-wifi mode (faster, but most school wifi blocks it)\n\n"
            "Everyone in the room has to pick the same one.")
    name = args.name or simpledialog.askstring(
        "Study chat", "Your name:", initialvalue=DEFAULT_NAME) or "anon"
    room = args.room or simpledialog.askstring(
        "Study chat",
        "Room name (everyone types the same one).\n"
        "In online mode, make it long and hard to guess, like a password.",
        initialvalue=DEFAULT_ROOM) or "study"
    name, room = name.strip()[:20], room.strip()[:60]

    inbox = queue.Queue()
    try:
        net = RelayNet(room, name, inbox) if online else Net(room, name, inbox)
    except OSError as e:
        print("Could not open the network port:", e)
        return

    # optional global hotkey (pip install pynput). Off on Mac by default,
    # because pynput can freeze or crash Tk apps there.
    if sys.platform != "darwin" or os.environ.get("STUDYCHAT_HOTKEY") == "1":
        try:
            from pynput import keyboard
            keyboard.GlobalHotKeys(
                {"<ctrl>+<alt>+c": lambda: inbox.put({"type": "summon"})}
            ).start()
        except Exception:
            pass

    overlay = Overlay(root, net, inbox)
    root.deiconify()                     # set the macOS style before mapping
    try:
        tkver = str(root.tk.call("info", "patchlevel"))
        log(f"started: python {sys.version.split()[0]}, tk {tkver}, "
            f"{sys.platform}, {net.mode} mode")
        if tkver.startswith("8.5"):
            overlay.note("warning: your Python uses an old, buggy Tk (8.5) "
                         "that can freeze. Install Python from python.org.")
    except Exception:
        pass
    net.send("joined", kind="join")
    overlay.add({"type": "join", "name": "You", "text": ""})
    overlay.start_update_check()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        proc = getattr(overlay, "reels_proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()             # close the reels window too
        net.close()                      # sends "left" to everyone


if __name__ == "__main__":
    main()
    # Hello - Max
