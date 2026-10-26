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

Images:
  - Press Ctrl+V in the text box to send an image from your clipboard
    (screenshots work great), or click "+" to pick an image file,
    or type  /img path/to/file.png
  - Click an image in the chat to see it full size (click it again to close).
  - Install Pillow for best results:  pip install pillow
    (without it, only PNG and GIF files can be sent, and no clipboard paste)
"""

import argparse
import base64
import hashlib
import io
import json
import os
import queue
import re
import socket
import ssl
import sys
import threading
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
FONT_FAMILY = "Segoe UI"
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
ONLINE_PING_EVERY = 45

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

    def send(self, text, kind="msg"):
        msg = {"app": "studychat", "room": self.room, "id": uuid.uuid4().hex,
               "name": self.name, "text": text, "type": kind,
               "uid": self.uid}
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
        self.ping_every = ONLINE_PING_EVERY
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
        return urllib.request.urlopen(req, timeout=timeout, context=self.ctx)

    # --- sending (one background thread keeps messages in order)
    def send(self, text, kind="msg"):
        msg = {"app": "studychat", "room": self.room, "id": uuid.uuid4().hex,
               "name": self.name, "text": text[:1000], "type": kind,
               "uid": self.uid}
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
            try:
                meta = json.dumps(msg)           # one ASCII line
                if data is None:
                    req = urllib.request.Request(
                        url, data=meta.encode("utf-8"), method="POST")
                else:
                    ext = ("png" if data.startswith(b"\x89PNG") else
                           "gif" if data.startswith(b"GIF8") else "jpg")
                    req = urllib.request.Request(
                        url, data=data, method="PUT",
                        headers={"Filename": f"image.{ext}", "Message": meta})
                self._open(req, 60).read()
            except urllib.error.HTTPError as ex:
                self._status("sending too fast, wait a few seconds"
                             if ex.code == 429
                             else f"message not sent (error {ex.code})")
            except Exception:
                self._status("message not sent (is the internet working?)")
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

    # --- receiving
    def _subscribe(self):
        backoff = 1
        start = str(int(time.time()))
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
        self.known_tags = set()
        self.presence = Presence()
        self.last_ping = 0

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
        self.online_lbl = tk.Label(self.header, text="1 online", bg=BAR,
                                   fg=MUTED, cursor="hand2", font=F(-2))
        self.online_lbl.pack(side="right", padx=6)
        self.online_lbl.bind("<Button-1>", lambda e: self.show_who())
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
        for seq in ("<Control-v>", "<Control-V>", "<Command-v>"):
            try:
                self.entry.bind(seq, self._on_paste)
                self.text.bind(seq, self._on_paste)
            except Exception:
                pass

        self.set_state("collapsed")
        self.root.after(100, self.poll)
        self.root.after(500, self.tick)

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
            self.root.focus_force()
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
        self.online_lbl.config(bg=BAR, fg=MUTED, font=F(-2))
        self.text.config(bg=BG, fg=FG, font=F())
        self.text.tag_config("sys", foreground=MUTED)
        self.entry_wrap.config(bg=BAR)
        self.plus.config(bg=BAR, fg=FG, font=F(3, True))
        self.entry.config(bg=BAR, fg=FG, insertbackground=FG, font=F())
        for tag in self.known_tags:
            self.text.tag_config(tag, font=F(0, True))
        for m in self.history:               # thumbnails may change size
            m.pop("_photo", None)
        self.anchor_x = ANCHOR_X
        self.anchor_bottom = self.root.winfo_screenheight() - BOTTOM_MARGIN
        self._geometry()
        self.redraw()

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
        self.online_lbl.config(text=f"{len(self.online_names())} online")

    def show_who(self):
        self.note("Online: " + ", ".join(self.online_names()))

    def _on_text_click(self, _e):
        if self.state != "active":
            self.set_state("active")
        else:
            self.entry.focus_force()         # so Ctrl+V works after clicking

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
        photo = self.make_photo(data, int(sw * 0.8), int(sh * 0.8))
        if photo is None:
            return
        top = self.tk.Toplevel(self.root)
        top.title("Image")
        top.configure(bg=BG)
        top.attributes("-topmost", True)
        lbl = self.tk.Label(top, image=photo, bg=BG, cursor="hand2")
        lbl.image = photo
        lbl.pack()
        for w in (top, lbl):
            w.bind("<Button-1>", lambda e: top.destroy())
        top.bind("<Escape>", lambda e: top.destroy())
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

    def send_file(self, path):
        path = path.strip().strip('"').strip("'")
        try:
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
        self.entry.focus_force()

    def _clip_has_text(self):
        try:
            return bool(self.root.clipboard_get())
        except Exception:
            return False

    def _on_paste(self, _e=None):
        if not PIL_OK:
            if self._clip_has_text():
                return None                  # normal text paste
            self.note("to paste images, run:  python -m pip install pillow  "
                      "then restart the app")
            return "break"
        err = None
        try:
            clip = ImageGrab.grabclipboard()
        except Exception as ex:
            clip, err = None, str(ex)[:80]
        if clip is None:
            if self._clip_has_text():
                return None                  # normal text paste
            self.note("no image found on the clipboard"
                      + (f" ({err})" if err else ""))
            return "break"
        if isinstance(clip, list):           # copied image files
            sent = False
            for p in clip[:3]:
                sent = self.send_file(p) or sent
            return "break" if sent else None
        self.send_pil(clip)
        return "break"

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
        for m in msgs:
            kind = m.get("type")
            if kind in ("join", "leave"):
                word = "joined" if kind == "join" else "left"
                t.insert("end", f"{m['name']} {word}\n", "sys")
                continue
            if kind == "sys":
                t.insert("end", m.get("text", "") + "\n", "sys")
                continue
            tag = "n_" + m["name"]
            if tag not in self.known_tags:
                t.tag_config(tag, foreground=name_color(m["name"]),
                             font=F(0, True))
                self.known_tags.add(tag)
            t.insert("end", m["name"] + ": ", tag)
            if kind == "img" and isinstance(m.get("data"), bytes):
                if "_photo" not in m:
                    m["_photo"] = self.make_photo(m["data"], THUMB_W, THUMB_H)
                t.insert("end", "\n")
                if m["_photo"] is not None:
                    itag = "img_" + str(m.get("id"))
                    start = t.index("end-1c")
                    t.image_create(start, image=m["_photo"], padx=2, pady=2)
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
                t.insert("end", m.get("text", "") + "\n")
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
        if text.startswith("/img "):
            self.send_file(text[5:])
            return
        self.add(self.net.send(text))
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

    def _handle_incoming(self, msg):
        if msg.get("type") == "summon":
            self.set_state("active")
            return
        msg["name"] = str(msg.get("name", "?"))[:20]
        msg["text"] = str(msg.get("text", ""))[:2000]
        self.presence.seen(msg, time.time())
        if msg.get("type") == "join" and msg.get("uid") != self.net.uid:
            # say hi back right away so the newcomer sees who's here
            self.net.send("", kind="ping")
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
    args = ap.parse_args()

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

    root.deiconify()
    overlay = Overlay(root, net, inbox)
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
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        net.close()                      # sends "left" to everyone


if __name__ == "__main__":
    main()