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
  - Every launch starts at the bottom-left of the primary display.
  - Drag the top bar to move it for this session, including between monitors.
    On Windows, dropping it keeps it inside a display's usable area.
  - Right-click the button to open Settings or quit.

Lost window:
  - Restart Study Chat to bring it back to the bottom-left corner.
  - The menu's "Reset window position" brings it back without restarting.
  - Ctrl+Alt+C brings it back and opens the chat if the optional pynput
    package is installed (pip install pynput). Off by default on macOS.
  - On Windows, disconnecting the display holding the chat brings it back
    to the primary display within a couple of seconds.
  - For older versions: close the chat, open %USERPROFILE%\\.studychat.json
    in Notepad, set ANCHOR_X to 20 and BOTTOM_MARGIN to 70, save and restart.

Flip:
  - The "flip" button (or /flip) turns everyone's chat text upside down for
    5 seconds. It only changes the chat window's text. Anyone can turn it
    off for themselves in Settings (Behavior, "Let others flip your chat").

Late joiners:
  - If you join after others, someone already in the room sends you the
    recent text messages. Nothing is saved to disk, so when the last person
    leaves, the chat is gone. (Images from before you joined don't come.)

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

Links in messages are clickable (Instagram links open the small reels
  window). Select chat text with the mouse and press Ctrl+C (Cmd+C on a
  Mac) to copy it, or right-click a line or link for a copy menu.
Top bar: the "menu" dropdown holds flip, GIF, reels, settings, updates and
  Disconnect (leaves the room and closes the program).
Commands: /disconnect (or /quit), /getfonts (install the free fonts your friends use),
  /guess (start a shared number-guessing game),
  /reels [link] (small Instagram window; needs Chrome, Chromium,
  Edge or Brave, or pywebview), /reelgif (send a GIF of the reel; same as
  the "gif" button, "/reelgif area" picks the screen area again),
  /duel (challenge the room to a tiny turn-based fighting game),
  /duel watch (watch an active duel),
  /duel solo (test it alone: you control both fighters),
  /who (who's online), /update (check for a new version),
  /version, /settings, /img, /quit. The chat checks GitHub for a newer
  version when it starts; set STUDYCHAT_NO_UPDATE=1 to turn that off.

Shared fonts:
  Fonts in ~/StudyChatFonts are offered to people in the room. When you accept
  a font from someone, it is saved in your folder and can be shared onward.
  Use "get fonts" to accept offers; only accept fonts from people you trust.

Number guesser:
  Use /guess or the menu to start a shared round. Everyone else gets one
  guess; a wrong guess ends that player's turn without closing their chat.

Images:
  - Press Ctrl+V in the text box to send an image from your clipboard
    (screenshots work great), or click "+" to pick an image file,
    or type  /img path/to/file.png
  - The skull button (next to "+") opens the GIF called skeleton-skyrim
    (from the same folder as studychat.py) in a window on EVERYONE'S screen.
    It closes itself after a few seconds, or on a click. You can turn it off
    for yourself in Settings ("Let others open the skeleton window").
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
import struct
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
from dataclasses import dataclass

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
VERSION = "1.13"
UPDATE_REPO = "jojobananas12/Study-chat"     # github.com/<this>
CHECK_UPDATES = os.environ.get("STUDYCHAT_NO_UPDATE") != "1"

# When someone with one of these names (lowercase) joins, your copy of the
# chat sends them this message. Add or delete lines to change it.
JOIN_GREETINGS = {"david": "Love you David!"}
GREETING_SENDER = "Admin"        # the name those messages appear under

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
ANCHOR_X = 20            # fixed startup offset from the usable left edge
BOTTOM_MARGIN = 70       # fixed startup offset from the usable bottom edge

# --- Behavior
POPUP_SECONDS = 8        # how long a new-message popup stays open
ACTIVE_IDLE_SECONDS = 20 # typing box closes itself after this much quiet
POPUP_LINES = 5          # most messages in the popup: the new one + 4 earlier
MAX_HISTORY = 300        # messages kept in the chat
DEFAULT_NAME = ""        # pre-filled in the "Your name" box
DEFAULT_ROOM = "study"   # pre-filled in the "Room name" box
FONT_SYNC = 1            # 1 = share the fonts folder with the room, 0 = don't
FONT_FOLDER = os.path.join(os.path.expanduser("~"), "StudyChatFonts")

# --- Images
THUMB_W, THUMB_H = 280, 180
MAX_IMAGE_MB = 8         # biggest image allowed, in megabytes
SEND_MAX_DIM = 1600      # big images are shrunk to this many pixels first
ALLOW_FLIP = 1           # 1 = others can flip your chat upside down, 0 = no
ALLOW_SKELETON = 1       # 1 = others can open the skeleton window on your screen
SKELETON_SECONDS = 10    # that window closes itself after this many seconds
GIF_SECONDS = 4          # length of a "gif of the reel" recording
GIF_FPS = 8              # frames per second of that recording
GIF_WIDTH = 300          # width (pixels) of that GIF

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
    ("Behavior", "POPUP_SECONDS", "Popup stays open (seconds)", "int", 1, 120),
    ("Behavior", "ACTIVE_IDLE_SECONDS", "Close typing box after idle (seconds)",
     "int", 3, 600),
    ("Behavior", "POPUP_LINES", "Messages in popup (new + earlier unseen)",
     "int", 1, 5),
    ("Behavior", "MAX_HISTORY", "Messages remembered", "int", 20, 2000),
    ("Behavior", "ALLOW_FLIP", "Let others flip your chat (1 = yes, 0 = no)",
     "int", 0, 1),
    ("Behavior", "ALLOW_SKELETON",
     "Let others open the skeleton window on your screen (1 = yes, 0 = no)",
     "int", 0, 1),
    ("Behavior", "SKELETON_SECONDS", "Skeleton window closes after (seconds)",
     "int", 3, 120),
    ("Behavior", "DEFAULT_NAME", "Default name", "str", 0, 20),
    ("Behavior", "DEFAULT_ROOM", "Default room", "str", 1, 60),
    ("Behavior", "FONT_SYNC",
     "Share the fonts folder with the room (1 = yes, 0 = no)", "int", 0, 1),
    ("Behavior", "FONT_FOLDER", "Shared fonts folder", "str", 1, 300),
    ("Images", "THUMB_W", "Thumbnail width", "int", 60, 800),
    ("Images", "THUMB_H", "Thumbnail height", "int", 40, 800),
    ("Images", "MAX_IMAGE_MB", "Biggest image allowed (MB)", "int", 1, 15),
    ("Images", "SEND_MAX_DIM", "Shrink big images to (pixels)", "int", 300, 4000),
    ("Images", "GIF_SECONDS", "Reel GIF length (seconds)", "int", 1, 8),
    ("Images", "GIF_FPS", "Reel GIF frames per second", "int", 3, 12),
    ("Images", "GIF_WIDTH", "Reel GIF width (pixels)", "int", 120, 640),
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


# ---------------------------------------------------------- window placement
@dataclass(frozen=True)
class Monitor:
    name: str
    bounds: tuple                       # left, top, right, bottom
    work: tuple                         # usable rectangle, excluding taskbars
    primary: bool = False


def _windows_monitors():
    """Read monitor rectangles in the UI thread's existing DPI context."""
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    user32.EnumDisplayMonitors.argtypes = (
        wintypes.HDC, ctypes.POINTER(wintypes.RECT),
        callback_type, wintypes.LPARAM)
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    monitors = []

    @callback_type
    def collect(handle, _hdc, _rect, _data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r, w = info.rcMonitor, info.rcWork
            if r.right > r.left and r.bottom > r.top and (
                    w.right > w.left and w.bottom > w.top):
                monitors.append(Monitor(
                    info.szDevice, (r.left, r.top, r.right, r.bottom),
                    (w.left, w.top, w.right, w.bottom),
                    bool(info.dwFlags & 1)))  # MONITORINFOF_PRIMARY
        return True

    if not user32.EnumDisplayMonitors(None, None, collect, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not monitors or not any(m.primary for m in monitors):
        raise OSError("could not read the primary display")
    return sorted(monitors, key=lambda m: (not m.primary, m.name))


def display_monitors(root):
    """Windows work areas, or a safe Tk screen fallback without dependencies."""
    if sys.platform == "win32":
        try:
            return _windows_monitors()
        except (OSError, AttributeError):
            pass
    bounds = (0, 0, max(1, root.winfo_screenwidth()),
              max(1, root.winfo_screenheight()))
    return [Monitor("tk-screen", bounds, bounds, True)]


def monitor_for_window(x, y, w, h, monitors):
    """Prefer greatest overlap, then shortest distance, then the primary."""
    def rank(m):
        left, top, right, bottom = m.bounds
        overlap = (max(0, min(x + w, right) - max(x, left))
                   * max(0, min(y + h, bottom) - max(y, top)))
        dx = max(left - (x + w), x - right, 0)
        dy = max(top - (y + h), y - bottom, 0)
        return (-overlap, dx * dx + dy * dy, not m.primary, m.name)
    return min(monitors, key=rank)


def fit_window(x, anchor_bottom, w, h, work):
    """Fit a bottom-anchored window without changing its configured size."""
    left, top, right, bottom = work
    w, h = min(w, right - left), min(h, bottom - top)
    x = max(left, min(x, right - w))
    y = max(top, min(anchor_bottom - h, bottom - h))
    return int(x), int(y), int(w), int(h)


def F(delta=0, bold=False):
    size = max(6, FONT_SIZE + delta)
    return (FONT_FAMILY, size, "bold") if bold else (FONT_FAMILY, size)


def name_color(name):
    return PALETTE[sum(map(ord, name)) % len(PALETTE)]


_FLIP = {}
for _a, _b in zip("abcdefghijklmnopqrstuvwxyz",
                  ["ɐ", "q", "ɔ", "p", "ǝ", "ɟ", "ƃ", "ɥ", "ᴉ", "ɾ", "ʞ",
                   "l", "ɯ", "u", "o", "d", "b", "ɹ", "s", "ʇ", "n", "ʌ",
                   "ʍ", "x", "ʎ", "z"]):
    _FLIP[_a] = _b
for _a, _b in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                  ["∀", "ᗺ", "Ɔ", "ᗡ", "Ǝ", "Ⅎ", "⅁", "H", "I", "ſ", "ʞ",
                   "˥", "W", "N", "O", "Ԁ", "Ό", "ᴚ", "S", "⊥", "∩", "Λ",
                   "M", "X", "⅄", "Z"]):
    _FLIP[_a] = _b
for _a, _b in zip("0123456789", ["0", "Ɩ", "ᄅ", "Ɛ", "ㄣ", "ϛ", "9", "ㄥ", "8",
                                 "6"]):
    _FLIP[_a] = _b
for _a, _b in zip(".,'?!()[]{}<>&_;", ["˙", "'", ",", "¿", "¡", ")", "(", "]",
                                      "[", "}", "{", ">", "<", "⅋", "‾",
                                      "؛"]):
    _FLIP[_a] = _b


URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.I)
LINK_COLOR = "#6cb6ff"


def split_links(text):
    """Cut a message into [(piece, url or None), ...] so links can be made
    clickable. Trailing punctuation (a full stop, a closing bracket) is left
    out of the link."""
    out, pos = [], 0
    for m in URL_RE.finditer(text):
        raw = m.group()
        while raw and (raw[-1] in ".,;:!?'\"]}" or (
                raw[-1] == ")" and raw.count(")") > raw.count("("))):
            raw = raw[:-1]
        url = raw if raw.lower().startswith("http") else "https://" + raw
        try:
            u = urllib.parse.urlparse(url)
            good = u.scheme in ("http", "https") and "." in (u.hostname or "")
        except ValueError:
            good = False
        if not good:
            continue
        if m.start() > pos:
            out.append((text[pos:m.start()], None))
        out.append((raw, url))
        pos = m.start() + len(raw)
    if pos < len(text):
        out.append((text[pos:], None))
    return out


def flip_text(s):
    """Upside-down text: each line turned around and read backwards."""
    return "\n".join("".join(_FLIP.get(c, c) for c in line[::-1])
                     for line in str(s).split("\n"))


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
# ---------------------------------------------------------------------- fonts
GOOGLE_CSS = "https://fonts.googleapis.com/css2?family="


def google_font_files(family):
    """Direct links to a free Google font's files, as {"name", "urls"}, or
    None if Google doesn't have a font by that name. Raises if Google can't
    be reached."""
    tried = []
    for name in (family, family.title()):
        if name not in tried:
            tried.append(name)
    for name in tried:
        for spec in (":wght@400;700", ""):       # regular + bold, else regular
            url = GOOGLE_CSS + urllib.parse.quote_plus(name) + spec
            try:
                css = _http_get(url, timeout=10, limit=300_000).decode(
                    "utf-8", "replace")
            except urllib.error.HTTPError as ex:
                if ex.code in (400, 404):
                    continue                     # no such font (or weight)
                raise
            links = re.findall(
                r"url\((https://fonts\.gstatic\.com/[^)\s'\"]+)\)", css)
            files = []
            for u in links:
                if (u.split("?")[0].lower().endswith((".ttf", ".otf"))
                        and u not in files):
                    files.append(u)
            if files:
                return {"name": name, "urls": files[:4]}
            if links:
                raise ValueError("only web-format files offered")
    return None


def download_font(url):
    """Download one font file from Google's font server and sanity-check it."""
    host = urllib.parse.urlparse(url).hostname or ""
    if urllib.parse.urlparse(url).scheme != "https" \
            or host != "fonts.gstatic.com":
        raise ValueError("unexpected font address")
    data = _http_get(url, timeout=40, limit=30_000_000)
    if not data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise ValueError("that isn't a font file")
    return data


def font_dir():
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            home, "AppData", "Local")
        return os.path.join(base, "Microsoft", "Windows", "Fonts")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Fonts")
    return os.path.join(home, ".local", "share", "fonts")


def install_font_file(data, filename):
    """Install a font for this user only (no admin password needed)."""
    d = font_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, filename)
    with open(path, "wb") as f:
        f.write(data)
    if sys.platform == "win32":
        import ctypes
        import winreg
        kind = "OpenType" if data[:4] == b"OTTO" else "TrueType"
        with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows NT\CurrentVersion\Fonts") as k:
            winreg.SetValueEx(k, f"{os.path.splitext(filename)[0]} ({kind})",
                              0, winreg.REG_SZ, path)
        ctypes.windll.gdi32.AddFontResourceExW(path, 0, 0)   # usable now
        ctypes.windll.user32.PostMessageW(0xFFFF, 0x001D, 0, 0)  # tell apps
    elif sys.platform != "darwin":
        try:
            subprocess.run(["fc-cache", "-f", d], timeout=60,
                           capture_output=True)
        except Exception:
            pass
    return path


# -------------------------------------------------------- shared fonts folder
# Everyone's copy keeps a folder of font files (default ~/StudyChatFonts).
# Free fonts downloaded with "get fonts" are saved in it, and so is anything
# you drop in it. The room is told what's in it, and anyone who wants a font
# can ask for it (after a prompt). Nothing outside this folder is ever shared,
# and a font is only sent to the person who asked for it.
MAX_FONT_BYTES = 5_000_000
MAX_SHARED_FONTS = 30
FONT_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"true")


def font_hash(data):
    return hashlib.sha256(data).hexdigest()[:16]


def looks_like_font(data):
    return (isinstance(data, (bytes, bytearray))
            and 12 < len(data) <= MAX_FONT_BYTES
            and bytes(data[:4]) in FONT_MAGIC)


def safe_font_name(name, ext=None):
    """A plain file name (letters, digits, dots, dashes) ending in .ttf/.otf."""
    stem, own = os.path.splitext(os.path.basename(str(name)))
    stem = re.sub(r"[^A-Za-z0-9._-]+", "", stem)[:60].strip(".") or "font"
    ext = (ext or own or "").lower()
    return stem + (ext if ext in (".ttf", ".otf") else ".ttf")


def font_family_name(data):
    """The family name stored inside a font file, or None."""
    try:
        count = struct.unpack(">H", data[4:6])[0]
        for i in range(min(count, 64)):
            tag, _sum, off, size = struct.unpack(
                ">4sIII", data[12 + 16 * i:28 + 16 * i])
            if tag != b"name":
                continue
            t = bytes(data[off:off + size])
            _fmt, n, base = struct.unpack(">HHH", t[:6])
            best = None
            for j in range(min(n, 300)):
                pid, _eid, _lid, nid, ln, o = struct.unpack(
                    ">HHHHHH", t[6 + 12 * j:18 + 12 * j])
                if nid not in (1, 16):
                    continue
                raw = t[base + o:base + o + ln]
                try:
                    s = raw.decode("utf-16-be" if pid in (0, 3)
                                   else "mac_roman")
                except ValueError:
                    continue
                s = "".join(c for c in s if c.isprintable()).strip()[:60]
                rank = (nid == 1, pid == 3)
                if s and (best is None or rank > best[0]):
                    best = (rank, s)
            return best[1] if best else None
    except Exception:
        pass
    return None


def scan_font_folder(folder, cache):
    """Fonts in the shared folder, as {hash: {"n": name, "s": size, "path"}}.
    `cache` remembers hashes so unchanged files aren't read again."""
    found = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return found
    for fname in names:
        if len(found) >= MAX_SHARED_FONTS:
            break
        if not fname.lower().endswith((".ttf", ".otf")):
            continue
        path = os.path.join(folder, fname)
        try:
            st = os.stat(path)
            if not os.path.isfile(path) or not 12 < st.st_size <= MAX_FONT_BYTES:
                continue
            key = (path, st.st_size, int(st.st_mtime))
            h = cache.get(key)
            if h is None:
                with open(path, "rb") as f:
                    data = f.read(MAX_FONT_BYTES + 1)
                if not looks_like_font(data):
                    continue
                h = font_hash(data)
                cache[key] = h
        except OSError:
            continue
        found.setdefault(h, {"n": safe_font_name(fname), "s": st.st_size,
                             "path": path})
    return found


def save_to_font_folder(folder, data, name):
    """Copy a font into the shared folder unless it's already there.
    Returns the new path, or None if it was already saved."""
    os.makedirs(folder, exist_ok=True)
    if font_hash(data) in scan_font_folder(folder, {}):
        return None
    stem, ext = os.path.splitext(safe_font_name(
        name, ".otf" if bytes(data[:4]) == b"OTTO" else ".ttf"))
    path, k = os.path.join(folder, stem + ext), 1
    while os.path.exists(path):
        k += 1
        path = os.path.join(folder, f"{stem}-{k}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def open_folder(path):
    """Show a folder in the computer's file browser."""
    os.makedirs(path, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


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


# ------------------------------------------------------------------ duel
# A tiny fighting game, as a pure integer simulation. It is turn based: each
# turn both fighters who are free pick one move, and every move takes a whole
# number of turns. The same picks always give the same fight on every laptop,
# so players only send their picks (one small message per pick). Nothing in
# here touches Tk or the network.
DUEL_W = 10                  # the arena is a row of tiles 0..DUEL_W
DUEL_HP = 5
DUEL_START = (3, 7)
DUEL_MAX_ROUNDS = 25         # turns; then whoever has more HP wins
DUEL_SUB = 8                 # animation frames drawn per turn

# Rules: turns = how many turns it takes, reach = how many tiles away it can
# hit, dmg = damage. The su/act/rec/steps numbers are only for the drawing.
DUEL_MOVES = {
    "jab":     dict(kind="strike", turns=1, reach=1, dmg=1,
                    su=3, act=2, rec=4,
                    help="1 turn, hits the 1 tile in front, 1 damage. Beats "
                         "grab, and cancels a heavy wind-up. If it's blocked "
                         "you lose your next turn."),
    "heavy":   dict(kind="strike", turns=2, reach=2, dmg=2,
                    su=7, act=3, rec=8,
                    help="2 turns (wind up, then strike), hits the 2 tiles in "
                         "front, 2 damage. A hit on the wind-up cancels it. "
                         "If it's blocked you lose your next turn."),
    "grab":    dict(kind="throw", turns=1, reach=1, dmg=0,
                    su=2, act=2, rec=3,
                    help="1 turn, hits the 1 tile in front, no damage. Beats "
                         "block. If it lands, they lose 2 turns. If it fails, "
                         "you lose 3 turns. Loses to jab and heavy."),
    "block":   dict(kind="guard", turns=1, su=1, act=7, rec=3,
                    help="1 turn, covers your own tile. Stops jab and heavy, "
                         "and then the attacker loses their next turn. Loses "
                         "to grab. If nothing was blocked you lose your next "
                         "turn."),
    "advance": dict(kind="walk", turns=1, dir=1, steps=2, su=0, act=0, rec=1,
                    help="1 turn, step 1 tile forward."),
    "dash":    dict(kind="walk", turns=2, dir=1, distance=3, first=2,
                    steps=4, su=0, act=0, rec=1,
                    help="2 turns: move 2 tiles forward now and 1 more next turn."),
    "retreat": dict(kind="walk", turns=1, dir=-1, steps=2, su=0, act=0, rec=1,
                    help="1 turn, step 1 tile back."),
    "dash_back": dict(kind="walk", turns=2, dir=-1, distance=3, first=2,
                      steps=4, su=0, act=0, rec=1,
                      help="2 turns: move 2 tiles back now and 1 more next turn."),
    "wait":    dict(kind="idle", turns=1, su=0, act=0, rec=3,
                    help="1 turn, do nothing."),
}
DUEL_ORDER = ("jab", "heavy", "grab", "block", "wait")
DUEL_MOVE_CHOICES = ("advance", "dash")

# What each fighter does on one turn. "wind" and "strike" are the two halves
# of a heavy attack; "stunned" is a turn lost.
_ATTACKS = {"jab": ("jab", 1, 1), "strike": ("heavy", 2, 2),
            "grab": ("grab", 1, 0)}          # act: (art move, reach, damage)


def _anim_total(m):
    d = DUEL_MOVES[m]
    return d["steps"] + d["rec"] if d["kind"] == "walk" \
        else d["su"] + d["act"] + d["rec"]


def duel_new():
    """A fresh fight. Fighter 0 starts on the left."""
    def fighter(x, f):
        return {"x": x, "f": f, "hp": DUEL_HP, "move": None, "t": 0,
                "stun": 0}
    return {"p": [fighter(DUEL_START[0], 1), fighter(DUEL_START[1], -1)],
            "round": 0, "over": False, "winner": None}


def duel_free(fi):
    return fi["stun"] == 0 and fi["move"] is None


def duel_need(S):
    """Which fighters must pick a move this turn. Anyone winding up or
    stunned has no choice, so they send nothing."""
    return [i for i in (0, 1) if duel_free(S["p"][i])]


def duel_turn_lead(S, i):
    """Positive means fighter i has fewer committed/lost turns remaining."""
    def unavailable(fi):
        return fi["stun"] + (
            1 if fi["move"] in ("heavy", "dash", "dash_back") else 0)
    return unavailable(S["p"][1 - i]) - unavailable(S["p"][i])


def duel_frame_lead(S, i):
    """Turn advantage expressed in the duel's animation frames."""
    return duel_turn_lead(S, i) * DUEL_SUB


def duel_movement_action(direction, action):
    """Resolve the selected relative direction and movement type."""
    if direction not in ("forward", "back"):
        raise ValueError("movement direction must be forward or back")
    if action not in DUEL_MOVE_CHOICES:
        raise ValueError("movement type must be advance or dash")
    if direction == "forward":
        return action
    return "retreat" if action == "advance" else "dash_back"


def duel_move_tiles(m, x, f):
    """The tiles a move affects for a fighter on tile x facing f (+1 means
    the right). Returns (tiles, kind) for the hover highlight."""
    d = DUEL_MOVES.get(m)
    if not d:
        return [], None
    k = d["kind"]
    if k == "walk":
        distance = d.get("distance", 1)
        tiles = [x + d["dir"] * f * n for n in range(1, distance + 1)]
        kind = "move"
    elif k in ("strike", "throw"):
        tiles = [x + f * j for j in range(1, d["reach"] + 1)]
        kind = "attack" if k == "strike" else "grab"
    elif k == "guard":
        tiles, kind = [x], "guard"
    else:
        return [], None
    return [t for t in tiles if 0 <= t <= DUEL_W], kind


def _art_t(fi):
    """Where the drawing of a held move is (a heavy wind-up stays raised)."""
    return DUEL_MOVES["heavy"]["su"] if fi["move"] == "heavy" else 0


def duel_frame(S):
    """A plain snapshot of the fight for drawing."""
    out = []
    for fi in S["p"]:
        out.append({"x": fi["x"], "f": fi["f"], "hp": fi["hp"],
                    "move": fi["move"], "stun": fi["stun"],
                    "t": _art_t(fi), "ko": fi["hp"] <= 0, "ev": [],
                    "guard": False, "active": False, "reach": 0})
    return {"p": out, "ev": []}


def _hit_sub(am, lo, hi):
    """The animation frame (1..DUEL_SUB) where a hit shows up: the first one
    past the start-up of the move."""
    su = DUEL_MOVES[am]["su"]
    for k in range(1, DUEL_SUB + 1):
        if lo + (hi - lo) * k // DUEL_SUB > su:
            return k
    return DUEL_SUB


def duel_round(S, choices):
    """Play one turn. choices: {fighter index: move name} for every fighter
    in duel_need(S); a bad or missing choice becomes 'wait'.
    Returns (frames, events). frames[0] is the start of the turn."""
    P = S["p"]
    # ---- what everyone does this turn
    acts = [None, None]
    for i in (0, 1):
        fi = P[i]
        if fi["stun"] > 0:
            acts[i] = "stunned"
        elif fi["move"] == "heavy":
            acts[i] = "strike"                   # second half of the heavy
        elif fi["move"] in ("dash", "dash_back"):
            acts[i] = "dash_follow"
        else:
            m = choices.get(i)
            m = m if m in DUEL_MOVES else "wait"
            acts[i] = "wind" if m == "heavy" else m
    start = [dict(P[i]) for i in (0, 1)]
    ev = []
    # ---- 1. walking (a step that would make them touch is cancelled)
    step = [0, 0]
    for i in (0, 1):
        if acts[i] in ("advance", "dash", "retreat", "dash_back"):
            move = DUEL_MOVES[acts[i]]
            distance = move.get("first", move.get("distance", 1))
            step[i] = move["dir"] * P[i]["f"] * distance
        elif acts[i] == "dash_follow":
            move = DUEL_MOVES[P[i]["move"]]
            step[i] = move["dir"] * P[i]["f"]
    nx = [min(DUEL_W, max(0, P[i]["x"] + step[i])) for i in (0, 1)]
    if nx[1] - nx[0] < 1:
        for i in (0, 1):
            if step[i] * P[i]["f"] > 0:          # moving toward the other
                nx[i] = P[i]["x"]
    gap = nx[1] - nx[0]
    # ---- 2. who hits whom, all decided from this turn's picks
    reach = [_ATTACKS[a][1] if a in _ATTACKS else 0 for a in acts]
    land = [a in _ATTACKS and gap <= reach[i] for i, a in enumerate(acts)]
    hurt = [0, 0]                                # damage taken
    stun = [0, 0]                                # turns lost from now on
    cut = [False, False]                         # move cancelled
    grabbed = [False, False]                     # successful grab by fighter
    seen = [None, None]                          # animation frame it shows on
    blocked = [False, False]                     # a block that stopped a hit
    for a in (0, 1):
        if not land[a]:
            continue
        d = 1 - a
        act = acts[a]
        k = _hit_sub(_ATTACKS[act][0],
                     DUEL_MOVES["heavy"]["su"] if act == "strike" else 0,
                     _anim_total(_ATTACKS[act][0]))
        if act == "grab":
            if acts[d] in ("jab", "wind", "strike"):
                continue                         # attacks beat a grab
            if land[d]:
                if a == 0:
                    ev.append((k, "tech"))       # both grabbed: nothing
                continue
            grabbed[a] = True
            stun[d] = max(stun[d], 2)
            cut[d] = True
            seen[d] = k
            ev.append((k, "grab:%d" % d))
        elif acts[d] == "block":
            blocked[d] = True
            ev.append((k, "blocked:%d" % d))
            stun[a] = max(stun[a], 1)            # a blocked attack: you stall
            seen[a] = k
        else:
            hurt[d] += _ATTACKS[act][2]
            cut[d] = True
            seen[d] = k
            ev.append((k, "hit:%d:%s" % (d, _ATTACKS[act][0])))
    for i in (0, 1):                             # a block that stops nothing
        if acts[i] == "block" and not blocked[i] and not stun[i]:
            stun[i] = 1                              # costs the next turn
            ev.append((DUEL_SUB, "whiff:%d" % i))
    for i in (0, 1):
        if acts[i] == "grab" and not grabbed[i]:
            penalty = 4 if acts[1 - i] == "jab" else 3
            stun[i] = max(stun[i], penalty)
            ev.append((DUEL_SUB, f"grab_fail:{i}:{penalty}"))
    # ---- 3. apply it
    S["round"] += 1
    for i in (0, 1):
        fi = P[i]
        fi["x"] = nx[i]
        fi["hp"] = max(0, fi["hp"] - hurt[i])
        if acts[i] == "stunned":
            fi["stun"] -= 1
        fi["stun"] = max(fi["stun"], stun[i])
        if acts[i] == "wind" and not cut[i]:
            fi["move"], fi["t"] = "heavy", 1     # strikes next turn
        elif acts[i] in ("dash", "dash_back") and not cut[i]:
            fi["move"], fi["t"] = acts[i], 1     # one more tile next turn
        else:
            fi["move"], fi["t"] = None, 0
    a, b = P[0]["hp"], P[1]["hp"]
    if a <= 0 or b <= 0:
        S["over"] = True
        S["winner"] = -1 if a <= 0 and b <= 0 else (1 if a <= 0 else 0)
    elif S["round"] >= DUEL_MAX_ROUNDS:
        S["over"] = True
        S["winner"] = -1 if a == b else (0 if a > b else 1)
    # ---- 4. the pictures: DUEL_SUB frames that play the turn out
    flat = [e for (_, e) in sorted(ev, key=lambda p: p[0])]
    frames = [_turn_frame(0, start, acts, hurt, seen, nx, P, ev)]
    frames += [_turn_frame(k, start, acts, hurt, seen, nx, P, ev)
               for k in range(1, DUEL_SUB + 1)]
    return frames, flat


def _turn_frame(k, st, acts, hurt, seen, nx, P, ev):
    """One animation frame (k = 0..DUEL_SUB) of a turn."""
    out = []
    last = k == DUEL_SUB
    for i in (0, 1):
        a_ = acts[i]
        if a_ == "wind":
            am, lo, hi = "heavy", 0, DUEL_MOVES["heavy"]["su"]
        elif a_ == "strike":
            am, lo, hi = "heavy", DUEL_MOVES["heavy"]["su"], \
                _anim_total("heavy")
        elif a_ == "dash_follow":
            am, lo, hi = st[i]["move"], 0, _anim_total(st[i]["move"])
        elif a_ in DUEL_MOVES and a_ != "wait":
            am, lo, hi = a_, 0, _anim_total(a_)
        else:
            am, lo, hi = None, 0, 0
        x = st[i]["x"] + (nx[i] - st[i]["x"]) * k / DUEL_SUB
        hit = seen[i] is not None and k >= seen[i]
        hp = max(0, st[i]["hp"] - (hurt[i] if hit else 0))
        if last:                                 # the state after the turn
            move, t = P[i]["move"], _art_t(P[i])
            hp = P[i]["hp"]
            reeling = P[i]["stun"] > 0
        else:
            move, t = am, lo + (hi - lo) * k // DUEL_SUB
            reeling = a_ == "stunned" or hit
        if reeling:
            move, t = None, 0
        out.append({"x": x, "f": P[i]["f"], "hp": hp, "move": move,
                    "stun": 1 if reeling else 0, "t": t, "ko": hp <= 0,
                    "ev": [], "guard": False, "active": False, "reach": 0})
    fr = {"p": out, "ev": []}
    if k:
        fr["ev"] = [e for (n, e) in ev if n == k]
    return fr


# ------------------------------------------------------------- duel art
# Nidhogg-1 look: flat-colour silhouette fencers (yellow vs orange) on
# posterised skies in front of black scenery. This part draws nothing
# itself: it turns a fight frame into a list of (x, y, w, h, colour)
# pixel rectangles on a small logical canvas, and the window scales them
# up. No Tk in here, so it can be tested by saving pictures.
DUEL_LW, DUEL_LH = 200, 100          # logical canvas, in pixels
DUEL_GY = 76                         # the ground line
DUEL_U = 16                          # logical pixels per space
DUEL_MX = 20                         # left margin
DUEL_COLS = ("#ffd21f", "#ff7a1a")   # yellow, orange
DUEL_STAGES = (
    dict(name="castle", sky=("#3b1f63", "#6f3482", "#c04a7e"), sun="#ffb347",
         sunat=(148, 30, 13), sil="#10081a", edge="#ff9a3c"),
    dict(name="wilds", sky=("#0f3d3b", "#17655c", "#2f9470"), sun="#eaf7a4",
         sunat=(40, 28, 11), sil="#04201e", edge="#b7f36b"),
    dict(name="dusk", sky=("#192a5f", "#2f50a3", "#6c93e6"), sun="#fff1cb",
         sunat=(120, 24, 9), sil="#070c24", edge="#8fd0ff"),
    dict(name="embers", sky=("#4b1016", "#8e1e1e", "#d24a20"), sun="#ffd9a3",
         sunat=(70, 34, 15), sil="#1c0507", edge="#ff6a3a"),
)
_BG_CACHE = {}


def duel_stage_for(gid, rnd):
    """Same stage on both laptops; the scenery changes every 10 rounds."""
    try:
        base = int(gid[:4], 16)
    except (TypeError, ValueError):
        base = 0
    return (base + (rnd - 1) // 10) % len(DUEL_STAGES)


def _lerp(a, b, u):
    return int(round(a + (b - a) * u))


def _line(x0, y0, x1, y1, th=1):
    """Pixels of a thick line (Bresenham with a square brush)."""
    pts = set()
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    for _ in range(600):
        for ox in range(th):
            for oy in range(th):
                pts.add((x0 + ox, y0 + oy))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def _runs(pts, colour):
    """Merge pixels into horizontal runs (fewer rectangles to draw)."""
    out, run = [], None
    for (x, y) in sorted(pts, key=lambda p: (p[1], p[0])):
        if run and run[1] == y and run[0] + run[2] == x:
            run[2] += 1
        else:
            if run:
                out.append((run[0], run[1], run[2], 1, colour))
            run = [x, y, 1]
    if run:
        out.append((run[0], run[1], run[2], 1, colour))
    return out


def _disc(cx, cy, r, colour):
    out = []
    for dy in range(-r, r + 1):
        w = int((r * r - dy * dy) ** 0.5)
        out.append((cx - w, cy + dy, 2 * w + 1, 1, colour))
    return out


def _scenery(stage):
    """Black silhouettes behind the fighters, built once per stage."""
    s = DUEL_STAGES[stage]
    sil, sky = s["sil"], s["sky"][2]
    gy = DUEL_GY
    out = []
    seed = [stage * 7919 + 13]

    def rnd(n):
        seed[0] = (seed[0] * 1103515245 + 12345) & 0x7FFFFFFF
        return (seed[0] >> 8) % n
    if s["name"] == "castle":
        out.append((0, 52, DUEL_LW, gy - 52, sil))
        for x in range(0, DUEL_LW, 10):
            out.append((x, 48, 6, 4, sil))
        for tx, tw, top in ((14, 16, 22), (118, 22, 14), (176, 14, 30)):
            out.append((tx, top, tw, 52 - top, sil))
            for x in range(tx, tx + tw, 4):
                out.append((x, top - 3, 2, 3, sil))
            out.append((tx + tw // 2 - 1, top + 8, 2, 4, sky))      # lit window
    elif s["name"] == "wilds":
        for x in range(0, DUEL_LW, 4):
            h = 54 + rnd(6)
            out.append((x, h, 4, gy - h, sil))
        for tx in (12, 52, 96, 140, 182):
            h = 14 + rnd(10)
            for row in range(h):
                w = 1 + row // 2
                out.append((tx - w // 2, 54 - h + row, w, 1, sil))
            out.append((tx - 1, 54, 2, 4, sil))
    elif s["name"] == "dusk":
        x = 0
        while x < DUEL_LW:
            w, h = 8 + rnd(10), 22 + rnd(24)
            out.append((x, 58 - h + 14, w, gy - (58 - h + 14), sil))
            for wy in range(58 - h + 18, 56, 6):
                if rnd(3) == 0:
                    out.append((x + 2, wy, 2, 3, sky))
            x += w
    else:                                                  # embers: ruins
        out.append((0, 56, DUEL_LW, gy - 56, sil))
        for cx in (10, 44, 80, 128, 160, 188):
            h = 14 + rnd(20)
            out.append((cx, 56 - h, 6, h, sil))
            out.append((cx - 2, 56 - h - 2, 10, 3, sil))
            if rnd(2):
                out.append((cx + 2, 56 - h - 6, 3, 4, sil))
    return out


def duel_bg_rects(stage):
    """Sky, sun, scenery and ground for one stage (cached)."""
    if stage in _BG_CACHE:
        return _BG_CACHE[stage]
    s = DUEL_STAGES[stage]
    out = [(0, 0, DUEL_LW, 26, s["sky"][0]), (0, 26, DUEL_LW, 22, s["sky"][1]),
           (0, 48, DUEL_LW, DUEL_GY - 48, s["sky"][2])]
    out += _disc(*s["sunat"][:2], s["sunat"][2], s["sun"])
    out += _scenery(stage)
    out.append((0, DUEL_GY, DUEL_LW, DUEL_LH - DUEL_GY, s["sil"]))
    out.append((0, DUEL_GY, DUEL_LW, 1, s["edge"]))
    _BG_CACHE[stage] = out
    return out


# ------------------------------------------------------------- fighters
def _phase(move, t):
    """('su'|'act'|'rec', progress 0..1, step inside the active part)."""
    d = DUEL_MOVES[move]
    if d["kind"] == "walk":
        return "walk", min(1.0, t / d["steps"]), t
    su, act, rec = d["su"], d["act"], d["rec"]
    if t <= su:
        return "su", (t / su if su else 1.0), 0
    if t <= su + act:
        return "act", (t - su) / act, t - su - 1
    return "rec", min(1.0, (t - su - act) / rec) if rec else 1.0, 0


def _pose(p, phase):
    """Where every limb goes, in pixels from the fighter's feet, with
    +x toward the opponent and -y up."""
    m = p["move"]
    R = DUEL_MOVES[m]["reach"] * DUEL_U if m and "reach" in DUEL_MOVES[m] else 0
    q = dict(lean=1, ff=5, bf=-4, ffy=0, bfy=0, drop=1 if phase % 8 < 4 else 0,
             hand=(8, -18), tip=(20, -22), bhand=(-4, -17), blade=None,
             two=False)
    if p["stun"] > 0 and m is None:
        q.update(lean=-4, ff=3, bf=-6, drop=1, hand=(1, -9), tip=(8, -2),
                 bhand=(-9, -16))
        return q
    if m is None or m == "wait":
        return q
    kind = DUEL_MOVES[m]["kind"]
    ph, u, k = _phase(m, p["t"])
    if kind == "walk":
        sw = 3 if (p["t"] % 2) else -3
        q.update(ff=5 + sw, bf=-4 - sw, ffy=-1 if sw > 0 else 0,
                 bfy=-1 if sw < 0 else 0, drop=0,
                 lean=2 if m in ("advance", "dash") else -1)
    elif m == "jab":
        if ph == "su":
            hx = _lerp(8, 1, u)
            q.update(lean=_lerp(1, -2, u), ff=_lerp(5, 3, u), hand=(hx, -17),
                     tip=(hx + 9, -17))
        elif ph == "act":
            q.update(lean=4, ff=9, bf=-5, drop=1, hand=(13, -17),
                     tip=(max(R, 20), -17))
        else:
            hx = _lerp(13, 8, u)
            q.update(lean=_lerp(4, 1, u), ff=_lerp(9, 5, u), hand=(hx, -17),
                     tip=(_lerp(R, hx + 12, u), _lerp(-17, -22, u)))
    elif m == "heavy":
        if ph == "su":
            hand = (_lerp(6, 3, u), _lerp(-20, -31, u))
            q.update(lean=_lerp(0, -3, u), ff=4, bf=-5, hand=hand,
                     tip=(hand[0] + 1, hand[1] - 15),
                     bhand=(hand[0] - 2, hand[1] + 3), two=True)
        elif ph == "act":
            s = min(1.0, (k + 1) / DUEL_MOVES[m]["act"])
            hand = (_lerp(5, 9, s), _lerp(-30, -18, s))
            q.update(lean=_lerp(0, 4, s), ff=_lerp(5, 9, s), bf=-5, drop=1,
                     hand=hand, tip=(_lerp(10, R, s), _lerp(-40, -5, s)),
                     bhand=(hand[0] - 2, hand[1] + 2), two=True)
        else:
            q.update(lean=_lerp(4, 1, u), ff=_lerp(9, 5, u),
                     drop=_lerp(2, 0, u), hand=(9, -14),
                     tip=(_lerp(int(R * 0.8), 14, u), _lerp(-4, -16, u)))
    elif m == "grab":
        if ph == "su":
            q.update(lean=_lerp(1, 3, u), ff=6, hand=(_lerp(7, 11, u), -18),
                     tip=None, bhand=(_lerp(2, 8, u), -15))
        elif ph == "act":
            q.update(lean=5, ff=10, bf=-5, drop=1, hand=(R - 1, -17),
                     tip=None, bhand=(R - 3, -14))
        else:
            q.update(lean=_lerp(5, 1, u), ff=_lerp(10, 5, u),
                     drop=_lerp(2, 0, u), hand=(_lerp(R - 1, 8, u), -17),
                     tip=None, bhand=(_lerp(R - 3, -4, u), -15))
    elif m == "block":
        up = {"su": 0.5 + 0.5 * u, "act": 1.0, "rec": 1.0 - u}[ph]
        q.update(lean=0, ff=4, hand=(9, -15), tip=None,
                 blade=((9, -3), (9, -3 - int(31 * up))), bhand=(2, -15))
    return q


def _fighter(p, cx, colour, phase, flash, goal=False):
    """Pixel rectangles of one fencer."""
    gy, f = DUEL_GY, p["f"]

    def X(dx):
        return cx + f * dx

    def Y(dy):
        return gy - 1 + dy
    col = "#ffffff" if flash else colour
    pts, sword = set(), set()
    if p["ko"]:                                     # lying in the blood
        pts |= _line(X(-14), Y(-3), X(-4), Y(-3), 3)
        pts |= _line(X(-4), Y(-2), X(5), Y(-1), 2)
        pts |= _line(X(-12), Y(-5), X(-8), Y(-1), 2)
        for dx in range(-20, -14):
            for dy in range(-6, -1):
                if not (dx in (-20, -19) and dy in (-6, -5)):
                    pts.add((X(dx), Y(dy)))
        sword |= _line(X(7), Y(-1), X(20), Y(-1), 1)
        out = _runs(pts, col) + _runs(sword, col)
        out.append((cx - 14, gy, 28, 1, colour))     # pool
        out.append((cx - 9, gy + 1, 18, 1, colour))
        return out
    q = _pose(p, phase)
    drop = q["drop"]
    hip = (q["lean"] // 2, -12 + drop)
    sho = (q["lean"], -21 + drop)
    head = (q["lean"] + 1, -26 + drop)
    pts |= _line(X(hip[0]), Y(hip[1]), X(sho[0]), Y(sho[1]), 3)
    for (fx_, fy_) in ((q["ff"], q["ffy"]), (q["bf"], q["bfy"])):
        pts |= _line(X(hip[0]), Y(hip[1]), X(fx_), Y(fy_), 2)
        pts.add((X(fx_ + 1), Y(fy_)))
        pts.add((X(fx_ + 2), Y(fy_)))
    pts |= _line(X(sho[0]), Y(sho[1] + 1), X(q["hand"][0]), Y(q["hand"][1]), 2)
    pts |= _line(X(sho[0]), Y(sho[1] + 1), X(q["bhand"][0]),
                 Y(q["bhand"][1]), 2)
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if abs(dx) + abs(dy) < 4:
                pts.add((X(head[0] + dx), Y(head[1] + dy)))
    if q["blade"]:
        (bx0, by0), (bx1, by1) = q["blade"]
        sword |= _line(X(bx0), Y(by0), X(bx1), Y(by1), 1)
        for dx in (-2, -1, 0, 1, 2):
            sword.add((X(q["hand"][0] + dx), Y(q["hand"][1] - 1)))
    elif q["tip"]:
        sword |= _line(X(q["hand"][0]), Y(q["hand"][1]),
                       X(q["tip"][0]), Y(q["tip"][1]),
                       2 if p["move"] == "heavy" else 1)
        for dy in (-1, 0, 1):
            sword.add((X(q["hand"][0]), Y(q["hand"][1] + dy)))
    out = []
    if p["move"] == "heavy" and _phase("heavy", p["t"])[0] == "act":
        R = DUEL_MOVES["heavy"]["reach"] * DUEL_U     # faint slash trail
        trail = set()
        for j in range(_phase("heavy", p["t"])[2]):
            s_ = (j + 1) / DUEL_MOVES["heavy"]["act"]
            hx, hy = _lerp(5, 9, s_), _lerp(-30, -18, s_)
            tx, ty = _lerp(10, R, s_), _lerp(-40, -5, s_)
            trail |= {pt for n, pt in enumerate(sorted(_line(
                X(hx), Y(hy), X(tx), Y(ty), 1))) if n % 2 == 0}
        out += _runs(trail, "#ffffff")
    out += _runs(pts, col) + _runs(sword, col)
    if q["blade"] and p["move"] == "block" and _phase("block", p["t"])[0] \
            == "act" and phase % 4 < 2:               # parry shimmer
        out += _runs({(X(9 + 1), Y(by1 + 2 + j)) for j in range(0, 20, 3)},
                     "#ffffff")
    return out


# ------------------------------------------------------------- effects
class DuelFx:
    """Blood, sparks, screen shake, white flashes. Only for looks, so
    nothing here has to match between laptops."""

    def __init__(self, seed=1):
        self.rng = random.Random(seed)
        self.parts = []          # [x, y, vx, vy, colour, size]
        self.splats = []         # blood left on the ground (x, y, colour)
        self.shake = 0
        self.flash = [0, 0]
        self.hold = 0            # extra frames of hit-stop
        self.ko_done = [False, False]
        self.stars = []          # [x, y, frames left] white impact flashes

    @staticmethod
    def _cx(p):
        return int(round(DUEL_MX + p["x"] * DUEL_U))

    def _burst(self, x, y, direction, n, colour, speed=2.4):
        for _ in range(n):
            self.parts.append([x + self.rng.uniform(-2, 2),
                               y + self.rng.uniform(-4, 4),
                               direction * self.rng.uniform(0.3, speed)
                               + self.rng.uniform(-0.4, 0.4),
                               -self.rng.uniform(0.2, speed + 0.8),
                               colour, 2 if self.rng.random() < 0.55 else 1])

    def on_frame(self, fr):
        P = fr["p"]
        for e in fr.get("ev", ()):
            b = e.split(":")
            if b[0] == "hit":
                d = int(b[1])
                a = 1 - d
                n = {"heavy": 44}.get(b[2], 20)
                self._burst(self._cx(P[d]), DUEL_GY - 18, P[a]["f"], n,
                            DUEL_COLS[d], 3.0)
                self.stars.append([self._cx(P[d]) - P[a]["f"] * 2,
                                   DUEL_GY - 18, 3])
                self.flash[d] = 3
                self.shake = max(self.shake, 6 if b[2] == "heavy" else 4)
                self.hold = max(self.hold, 3 if b[2] != "heavy" else 5)
            elif b[0] == "grab":
                d = int(b[1])
                self._burst(self._cx(P[d]), DUEL_GY - 18, P[1 - d]["f"], 8,
                            "#ffffff", 2.4)
                self.flash[d] = 3
                self.shake = max(self.shake, 3)
                self.hold = max(self.hold, 3)
            elif b[0] == "counter":
                d = int(b[1])
                self._burst(self._cx(P[d]), DUEL_GY - 22, P[1 - d]["f"], 12,
                            "#ffffff", 3.2)
                self.shake += 2
                self.hold += 2
            elif b[0] == "blocked":
                d = int(b[1])
                x = self._cx(P[d]) + P[d]["f"] * 10
                for c in ("#ffffff", "#ffe98a"):
                    self._burst(x, DUEL_GY - 22, -P[d]["f"], 6, c, 2.6)
                self.shake = max(self.shake, 2)
                self.hold = max(self.hold, 2)
            elif b[0] == "tech":
                x = (self._cx(P[0]) + self._cx(P[1])) / 2
                self._burst(x, DUEL_GY - 18, 1, 6, "#ffffff", 2)
                self._burst(x, DUEL_GY - 18, -1, 6, "#ffffff", 2)
        for i in (0, 1):
            if P[i]["ko"] and not self.ko_done[i]:
                self.ko_done[i] = True
                self._burst(self._cx(P[i]), DUEL_GY - 18, -P[i]["f"], 40,
                            DUEL_COLS[i], 3.2)
                self.shake = 9
                self.hold = 9

    def step(self):
        keep = []
        for p in self.parts:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.28
            if p[1] >= DUEL_GY - 1:
                if len(self.splats) < 500:
                    self.splats.append((int(p[0]), DUEL_GY - 1
                                        - self.rng.randrange(2), p[4]))
            elif -5 < p[0] < DUEL_LW + 5:
                keep.append(p)
        self.parts = keep
        self.flash = [max(0, n - 1) for n in self.flash]
        self.stars = [[x, y, n - 1] for (x, y, n) in self.stars if n > 1]
        if self.shake:
            self.shake -= 1

    def offset(self):
        if not self.shake:
            return 0, 0
        s = 1 if self.shake % 2 else -1
        return s * min(2, 1 + self.shake // 4), (s if self.shake > 3 else 0)


def _hud(fr, goal):
    """Health bars (one block per HP) and the 'GO' arrow."""
    out = []
    for i in (0, 1):
        segs = fr["p"][i]["hp"]
        x0 = 6 if i == 0 else DUEL_LW - 6 - DUEL_HP * 18
        for n in range(DUEL_HP):
            xi = x0 + (n if i == 0 else DUEL_HP - 1 - n) * 18
            out.append((xi, 12, 16, 5, DUEL_COLS[i] if n < segs else "#1a1226"))
    if goal is not None:
        w, loser = goal
        x = 140 if w == 0 else 30
        d = 1 if w == 0 else -1
        pts = set()
        for dx in range(0, 18):
            for dy in range(-1, 2):
                pts.add((x + d * dx, 38 + dy))
        for j in range(0, 6):
            for dy in range(-j, j + 1):
                pts.add((x + d * (18 + 5 - j), 38 + dy))
        out += _runs(pts, DUEL_COLS[w])
    return out


DUEL_TILE_COLS = ("#2c2542", "#1f1a33")      # the two chessboard shades
DUEL_HL = {"attack": "#e8453c", "grab": "#b06bff", "move": "#4a8fe0",
           "guard": "#3fbf6a"}


def duel_tile_rects(hl=None):
    """The row of tiles under the fighters. hl = (tiles, kind) lights some
    of them up (hovering over a move)."""
    on = {}
    if hl:
        for t in hl[0]:
            on[t] = hl[1]
    out = []
    for t in range(DUEL_W + 1):
        x = DUEL_MX + t * DUEL_U - DUEL_U // 2
        kind = on.get(t)
        if kind:
            col = DUEL_HL[kind]
            out.append((x, DUEL_GY + 1, DUEL_U - 1, 8, col))
            out.append((x, DUEL_GY - 3, DUEL_U - 1, 3, col))   # a bar above
        else:
            out.append((x, DUEL_GY + 1, DUEL_U - 1, 8,
                        DUEL_TILE_COLS[t % 2]))
    return out


def duel_fg_rects(fr, fx, phase, goal=None):
    """Everything in front of the backdrop for one frame. goal is
    (winner, loser) once the match is over, to show the GO arrow."""
    out = [(x, y, 1, 1, c) for (x, y, c) in fx.splats]
    for i in (0, 1):
        p = fr["p"][i]
        out += _fighter(p, int(round(DUEL_MX + p["x"] * DUEL_U)),
                        DUEL_COLS[i], phase,
                        fx.flash[i] > 0)
    for (x, y, vx, vy, c, sz) in fx.parts:
        out.append((int(x), int(y), sz, sz, c))
    for (x, y, n) in fx.stars:                     # white impact cross
        r = 2 + n
        out += [(int(x) - r, int(y), 2 * r + 1, 1, "#ffffff"),
                (int(x), int(y) - r, 1, 2 * r + 1, "#ffffff")]
    out += _hud(fr, goal if phase % 6 < 4 else None)
    return out


# ---------------------------------------------------------------- networking
# Quiet "ping" messages that carry one of these are real requests (a game
# move, a font file...), so the relay must retry them, never drop them.
LOUD_KEYS = ("items", "flip", "game", "duel", "fontreq", "blob")


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

    def send_image(self, data, extra=None):
        mid = uuid.uuid4().hex
        self.images[mid] = data
        while len(self.images) > 20:          # keep only the latest few
            self.images.pop(next(iter(self.images)))
        msg = {"app": "studychat", "room": self.room, "id": mid,
               "name": self.name, "text": "", "type": "img",
               "port": self.img_port, "size": len(data)}
        if extra:
            msg.update(extra)
        self.seen.add(mid)
        self._broadcast(msg)
        return dict(msg, data=data)

    def send_blob(self, data, extra):
        """A file meant for one person (a font). Announced like an image,
        but only the person named in extra["to"] downloads it."""
        mid = uuid.uuid4().hex
        self.images[mid] = data
        while len(self.images) > 20:
            self.images.pop(next(iter(self.images)))
        msg = {"app": "studychat", "room": self.room, "id": mid,
               "name": self.name, "text": "", "type": "ping",
               "uid": self.uid, "port": self.img_port, "size": len(data)}
        msg.update(extra)
        self.seen.add(mid)
        self._broadcast(msg)
        return msg

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
            if msg.get("blob") == "font":
                if msg.get("to") == self.uid:    # only the one who asked
                    threading.Thread(target=self._fetch,
                                     args=(msg, addr[0]), daemon=True).start()
                continue
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
            if msg.get("blob"):
                msg = {"type": "font_fail", "h": msg.get("h")}
            else:
                msg = {"type": "msg", "id": msg.get("id"),
                       "name": msg.get("name", "?"),
                       "text": "(sent an image that didn't load)"}
        self.inbox.put(msg)


def relay_keepalive_due(now, last_keepalive, last_published, interval):
    """Only send a presence ping after a full interval without any post."""
    return now - max(last_keepalive, last_published) > interval


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
        self.last_published_at = time.time()
        # The free relay allows only a few posts per minute for everyone on
        # the same internet address, so keep background chatter rare.
        self.ping_every = max(ONLINE_PING_EVERY, 180)
        self.cool_until = 0              # pause quiet signals after a 429
        self.cool_n = 0                  # 429s in a row (longer pause each time)
        self.deferred = {}               # quiet signals held back, to retry
        self.join_ok = False             # our "joined" reached the relay
        self.held_note = False           # told the person about a slow relay
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

    def send_image(self, data, extra=None):
        msg = {"app": "studychat", "room": self.room, "id": uuid.uuid4().hex,
               "name": self.name, "text": "", "type": "img",
               "size": len(data)}
        if extra:
            msg.update(extra)
        self.seen.add(msg["id"])
        self.sendq.put((msg, data))
        return dict(msg, data=data)

    def send_blob(self, data, extra):
        """A file meant for one person (a font), sent as an attachment."""
        msg = {"app": "studychat", "room": self.room, "id": uuid.uuid4().hex,
               "name": self.name, "text": "", "type": "ping",
               "uid": self.uid, "size": len(data)}
        msg.update(extra)
        self.seen.add(msg["id"])
        self.sendq.put((msg, data))
        return msg

    # Quiet signals (joined, who's here, still here) are not chat, but they
    # are how people see each other. If the relay is busy they used to be
    # thrown away, so nobody ever appeared. Now they are held and retried,
    # and a newer signal of the same kind replaces an older one.
    HOLD_FOR = {"join": 300, "ping:keepalive": 600, "ping:who": 30,
                "ping:roster": 30, "ping:fontlist": 300}

    @staticmethod
    def _key(msg):
        t = msg.get("type")
        if t == "ping":
            return "ping:" + ("who" if msg.get("text") == "who" else
                              "roster" if "roster" in msg else
                              "fontlist" if "fontlist" in msg else
                              "keepalive")
        return t

    def _hold(self, msg, data, born, tries, fresh):
        key = self._key(msg)
        if key not in self.HOLD_FOR:
            return                   # chat is never held
        if key in self.deferred and not fresh:
            return                   # a retry never replaces a newer signal
        self.deferred.pop(key, None)
        self.deferred[key] = (msg, data, born, tries)
        if not self.held_note and key == "join":
            self.held_note = True
            log("join held back by the relay")
            self._status("the chat server is busy, so others may not see "
                         "you yet. Retrying...")

    def _sender(self):
        url = f"{self.base}/{self.topic}"
        while True:
            from_queue = True
            try:
                msg, data = self.sendq.get(timeout=1)
                born, tries = time.time(), 0
            except queue.Empty:
                # nothing new: retry a held-back signal once the relay allows
                if not self.deferred or time.time() < self.cool_until:
                    continue
                key = next(iter(self.deferred))
                msg, data, born, tries = self.deferred.pop(key)
                from_queue = False
                if time.time() - born > self.HOLD_FOR.get(key, 0):
                    continue                     # too old to be useful
            quiet = (msg.get("type") in ("ping", "join", "leave")
                     # history, flips, game moves and font files must never
                     # be dropped
                     and not any(k in msg for k in LOUD_KEYS))
            try:
                if (quiet and msg.get("type") != "leave"
                        and time.time() < self.cool_until):
                    self._hold(msg, data, born, tries, from_queue)   # angry
                    continue
                meta = json.dumps(msg)           # one ASCII line
                for attempt in range(4):
                    if data is None:
                        req = urllib.request.Request(
                            url, data=meta.encode("utf-8"), method="POST")
                    else:
                        ext = ("png" if data.startswith(b"\x89PNG") else
                               "gif" if data.startswith(b"GIF8") else
                               "ttf" if msg.get("blob") == "font" else "jpg")
                        req = urllib.request.Request(
                            url, data=data, method="PUT",
                            headers={"Filename": f"image.{ext}",
                                     "Message": meta})
                    try:
                        self._open(req, 60).read()
                        self.last_published_at = time.time()
                        self.cool_n = 0
                        if msg.get("type") == "join":
                            self.join_ok = True
                            if self.held_note:
                                self.held_note = False
                                self._status("connected: others can see "
                                             "you now")
                        break
                    except urllib.error.HTTPError as ex:
                        if ex.code == 429:
                            self.cool_n += 1
                            self.cool_until = time.time() + min(
                                60, 15 * 2 ** (self.cool_n - 1))
                        if ex.code != 429 or quiet or attempt == 3:
                            raise
                        # the relay says slow down: wait, then try again
                        if attempt == 0:
                            self._status("relay is busy, retrying...")
                        time.sleep(5 * (attempt + 1))
            except urllib.error.HTTPError as ex:
                if quiet and msg.get("type") != "leave" and tries < 8:
                    self._hold(msg, data, born, tries + 1, from_queue)
                elif not quiet:
                    self._status("relay is too busy, message not sent; "
                                 "try again in a minute" if ex.code == 429
                                 else f"message not sent (error {ex.code})")
            except Exception:
                if quiet and msg.get("type") != "leave" and tries < 8:
                    self.cool_until = max(self.cool_until, time.time() + 5)
                    self._hold(msg, data, born, tries + 1, from_queue)
                elif not quiet:
                    self._status("message not sent (is the internet "
                                 "working?)")
            finally:
                if from_queue:
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
        if msg.get("blob") == "font":
            url = att.get("url") if isinstance(att, dict) else None
            if msg.get("to") == self.uid and url:    # only the one who asked
                threading.Thread(target=self._fetch, args=(msg, url),
                                 daemon=True).start()
            return
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
            if msg.get("blob"):
                msg = {"type": "font_fail", "h": msg.get("h")}
            else:
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
        self.closed = False
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
        snapshot = dict(self.snapshot)
        self.close()
        try:
            for key, value in snapshot.items():
                set_value(key, value)
            self.ov.apply_settings()
        except Exception:
            log("couldn't restore settings while closing: "
                + traceback.format_exc())

    def save(self):
        try:
            ok = save_settings()
        except Exception:
            log("couldn't save settings while closing: "
                + traceback.format_exc())
            ok = False
        finally:
            self.close()
        if not ok:
            self.ov.note("couldn't save your settings file")

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.job:
            try:
                self.win.after_cancel(self.job)
            except Exception:
                log("couldn't cancel settings preview: "
                    + traceback.format_exc())
            self.job = None
        if self.ov.settings_win is self:
            self.ov.settings_win = None
        self.ov.busy = False
        try:
            self.win.destroy()
        except Exception:
            log("couldn't destroy settings window: "
                + traceback.format_exc())
        finally:
            try:
                self.ov._focus_entry()
            except Exception:
                log("couldn't restore chat focus after settings: "
                    + traceback.format_exc())


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
        self.seq = 0                        # count of messages delivered
        self.seen_upto = 0                  # ...and how many you've seen
        self.last_activity = 0
        self.busy = False
        self.menu_until = 0                 # a popup menu is open until then
        self.settings_win = None
        self._focus_job = None
        self.font_tags = {}                 # text tag -> (family, bold, color)
        self.color_tags = set()             # name-color tags already made
        try:
            self.old_tk = str(root.tk.call("info", "patchlevel")
                              ).startswith("8.5")
        except Exception:
            self.old_tk = False
        self.anims = []                     # animated GIFs now in the chat
        self._installed = None              # fonts on this computer
        self.font_warned = set()
        self.font_offers = {}               # lower name -> free font to offer
        self.font_cache = {}                # shared folder: file -> hash
        self.font_mine = {}                 # hash -> info, files in my folder
        self.font_announced = frozenset()   # what the room was last told
        self.font_due = time.time() + 8     # when to look at the folder next
        self.font_share_offers = {}         # hash -> font a friend shared
        self.font_wanted = {}               # hash -> font I asked a friend for
        self.font_seen = set()              # hashes I have (never offer again)
        self.font_served = []               # when I last sent a font away
        self.font_folder_noted = False
        self.game = None                    # the number guesser now running
        self.duel = None                    # the duel now running
        self.full_anims = []                # ...and in full-size viewers
        self.presence = Presence()
        # Joining already says "I'm here", so the first "still here" signal
        # waits a full interval (it used to go out at once, wasting a post).
        self.last_ping = time.time()
        self.start_time = time.time()      # first-join roll call
        self.first_peer_at = None
        self.ready_at = None
        self.roll_sent = 0
        self.roll_done = False
        self.last_reply = 0
        self.reply_seq = 0
        self.update_info = None            # newer version found on GitHub
        self.hist_seq = 0                  # late-joiner history
        self.last_hist = 0
        self.hist_from = None
        self.flip_until = 0                # chat shown upside down until then
        self.mirrored = {}                 # frame -> left/right swapped?
        self.label_text = {}               # label -> its normal text
        self.last_flip_sent = 0
        self.last_flip_got = 0
        self.clip_box = None               # screen area of the reels window
        self.clipping = False
        self.wayland_warned = False

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
        self._dragging = False
        self._placed_geometry = None
        self._reset_anchor()

        # pieces
        self.pill = tk.Label(root, text=PILL_LABEL, bg=PILL_BG, fg=PILL_FG,
                             font=F(3, True), cursor="hand2")
        self.pill.bind("<Button-1>", lambda e: self.set_state("active"))
        for b in ("<Button-2>", "<Button-3>"):
            self.pill.bind(b, lambda e: self._pop_menu(e.x_root, e.y_root))

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
        self.menu_lbl = tk.Label(self.header, text="menu \u25be", bg=BAR,
                                 fg=MUTED, cursor="hand2", font=F(-2))
        self.menu_lbl.pack(side="right", padx=6)
        self.menu_lbl.bind("<Button-1>", self._header_menu)
        self.online_lbl = tk.Label(self.header, text="checking...", bg=BAR,
                                   fg=MUTED, cursor="hand2", font=F(-2))
        self.online_lbl.pack(side="right", padx=6)
        self.online_lbl.bind("<Button-1>", lambda e: self.show_who())
        self.update_lbl = tk.Label(self.header, text="", bg=BAR,
                                   fg="#7be08a", cursor="hand2", font=F(-2))
        self.update_lbl.bind("<Button-1>", lambda e: self.update_cmd())
        self.fonts_lbl = tk.Label(self.header, text="", bg=BAR,
                                  fg="#7be08a", cursor="hand2", font=F(-2))
        self.fonts_lbl.bind("<Button-1>", lambda e: self.fonts_cmd())
        for w in (self.header, self.title):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        self.text = SafeText(root, bg=BG, fg=FG, bd=0, highlightthickness=0,
                            wrap="word", font=F(), padx=6, pady=4,
                            state="disabled", cursor="arrow")
        self.text.tag_config("sys", foreground=MUTED)
        self.text.tag_config("link", foreground=LINK_COLOR, underline=True)
        self.link_urls = {}                 # link tag -> address
        self.text.bind("<Button-1>", self._on_text_click)
        self.text.bind("<<Copy>>", self._on_copy)
        for b in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.text.bind(b, self._text_menu)

        self.entry_wrap = tk.Frame(root, bg=BAR)
        self.plus = tk.Label(self.entry_wrap, text="+", bg=BAR, fg=FG,
                             cursor="hand2", font=F(3, True))
        self.plus.pack(side="right", padx=8)
        self.plus.bind("<Button-1>", lambda e: self.pick_image())
        # skull button: sends the skeleton-skyrim GIF that sits next to this
        # script. (A plain skull-and-crossbones sign, not an emoji: old Macs'
        # Tk crashes on emoji.)
        self.skull = tk.Label(self.entry_wrap, text="\u2620", bg=BAR, fg=FG,
                              cursor="hand2", font=F(3, True))
        self.skull.pack(side="right", padx=(0, 2))
        self.skull.bind("<Button-1>", lambda e: self.send_skeleton())
        self.entry = tk.Entry(self.entry_wrap, bg=BAR, fg=FG, bd=0,
                              insertbackground=FG, font=F(),
                              highlightthickness=0)
        self.entry.pack(side="left", fill="x", expand=True, padx=6, pady=5)
        self.entry.bind("<<Copy>>", self._on_copy)   # copy chat text too
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

        for w in (self.title, self.close_lbl, self.menu_lbl, self.plus):
            self.label_text[w] = w.cget("text")
        self.set_state("collapsed")
        self._geometry(fit=True)            # also fit startup on non-Windows
        self.root.after(100, self.poll)
        self.root.after(500, self.tick)
        self.root.after(60, self._animate)

    # ---- geometry / state
    def _reset_anchor(self, monitors=None):
        self._monitors = (display_monitors(self.root) if monitors is None
                          else monitors)
        primary = next(m for m in self._monitors if m.primary)
        self._monitor_name = primary.name
        self.anchor_x = primary.work[0] + ANCHOR_X
        self.anchor_bottom = primary.work[3] - BOTTOM_MARGIN

    def reset_window_position(self):
        """Return to the startup corner without losing the current chat."""
        self._dragging = False
        self._reset_anchor()
        self._placed_geometry = None
        self._geometry(fit=True)
        self._raise_chat()
        self._focus_entry()

    def _check_displays(self):
        if sys.platform != "win32" or self._dragging:
            return
        monitors = display_monitors(self.root)
        if monitors == self._monitors:
            return
        if not any(m.name == self._monitor_name for m in monitors):
            self._reset_anchor(monitors)
        else:
            self._monitors = monitors
        self._placed_geometry = None
        self._geometry()

    def _place(self, w, h, fit=False):
        x, y = self.anchor_x, self.anchor_bottom - h
        if not self._dragging and (sys.platform == "win32" or fit):
            # Expanding near an edge must stay on the display chosen at the
            # last drop (or reset), even if the larger rectangle crosses it.
            monitor = next(m for m in self._monitors
                           if m.name == self._monitor_name)
            x, y, w, h = fit_window(x, self.anchor_bottom, w, h, monitor.work)
            self.anchor_x, self.anchor_bottom = x, y + h
            self._monitor_name = monitor.name
        geometry = (x, y, w, h)
        if geometry != self._placed_geometry:
            # Keep the explicit '+' even for negative coordinates: '+-100'
            # is absolute; '-100' means 100px from Tk's right/bottom edge.
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self._placed_geometry = geometry

    def _popup_msgs(self):
        """What the popup shows: the newest message plus the ones before it
        that arrived since you last had the chat open (at most POPUP_LINES,
        so the new one and the 4 before it)."""
        fresh = [m for m in self.history if m.get("_n", 0) > self.seen_upto]
        return fresh[-max(1, min(5, POPUP_LINES)):] or self.history[-1:]

    def _geometry(self, fit=False):
        """Size, position and opacity for the current state."""
        if self.state == "collapsed":
            self._place(PILL_W, PILL_H, fit=fit)
            alpha = PILL_ALPHA
        elif self.state == "popup":
            has_img = any(m.get("type") == "img" for m in self._popup_msgs())
            self._place(WIDTH, POPUP_IMG_HEIGHT if has_img else POPUP_HEIGHT,
                        fit=fit)
            alpha = POPUP_ALPHA
        else:
            self._place(WIDTH, ACTIVE_HEIGHT, fit=fit)
            alpha = ACTIVE_ALPHA
        self.root.attributes("-alpha", alpha)

    def set_state(self, state):
        self._dragging = False
        if self._focus_job is not None:
            self.root.after_cancel(self._focus_job)
            self._focus_job = None
        self.state = state
        if state == "active":
            self.seen_upto = self.seq        # you're looking at everything now
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
            self._pack_active()
            self._geometry()
            self.redraw()
            self._touch()
            self._raise_chat()
            self._focus_entry()

    # ---- upside-down ("flip") layout
    def _upside(self):
        return time.time() < self.flip_until

    def _mirror(self, frame, on):
        """Swap left and right for everything packed inside a frame."""
        if self.mirrored.get(frame, False) == on:
            return
        self.mirrored[frame] = on
        for w in frame.pack_slaves():
            info = w.pack_info()
            info.pop("in", None)
            info["side"] = "right" if info["side"] == "left" else "left"
            w.pack_forget()
            w.pack(**info)

    def _pack_active(self):
        """The typing window. Turned around when the chat is flipped: top
        bar at the bottom, text box at the top, buttons mirrored."""
        up = self._upside()
        for w in (self.header, self.text, self.entry_wrap):
            w.pack_forget()
        if up:
            self.header.pack(side="bottom", fill="x")
            self.entry_wrap.pack(side="top", fill="x")
        else:
            self.header.pack(fill="x")
            self.entry_wrap.pack(side="bottom", fill="x")
        self.text.pack(fill="both", expand=True)
        self._mirror(self.header, up)
        self._mirror(self.entry_wrap, up)

    def _restyle_flip(self):
        """Put every label, the layout and the messages the right way up or
        upside down, depending on whether a flip is happening."""
        try:
            up = self._upside()
            for w, orig in self.label_text.items():
                w.config(text=flip_text(orig) if up else orig)
            self.update_online()
            if self.state == "active":
                self._pack_active()
            self.redraw()
        except Exception:
            log("flip restyle failed: " + traceback.format_exc())

    # ---- keeping popups above the chat
    # The chat re-asserts "always on top" every couple of seconds so other
    # apps can't bury it. That also lifted it over its own popup menu and
    # windows (settings, image viewer), hiding them behind the chat. So the
    # refresh now pauses while a menu is open, and any window the chat opened
    # is put back above it afterwards.
    def _menu_open(self):
        return time.time() < self.menu_until

    def _menu_closed(self, _e=None):
        self.menu_until = 0

    def _post_menu(self, menu, x, y):
        """Show a popup menu without letting the chat cover it."""
        self.menu_until = time.time() + 120         # safety net
        menu.bind("<Unmap>", self._menu_closed)     # fires when it closes
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
            if sys.platform in ("win32", "darwin"):  # these wait for it
                self._menu_closed()

    def _child_windows(self):
        """Windows opened by the chat (settings, image viewer...) now showing."""
        out = []
        for w in self.root.winfo_children():
            if isinstance(w, self.tk.Toplevel):
                try:
                    if w.winfo_viewable():
                        out.append(w)
                except Exception:
                    pass
        return out

    def _raise_chat(self):
        """Bring the chat forward, with its own windows still on top of it."""
        if self._menu_open():
            return
        self.root.lift()
        for w in self._child_windows():
            try:
                w.lift()
            except Exception:
                pass

    def _stay_on_top(self):
        """The periodic "stay above other apps" refresh."""
        if self._menu_open():
            return                       # don't cover an open menu
        self.root.attributes("-topmost", True)
        for w in self._child_windows():  # ...and keep our windows above it
            try:
                w.attributes("-topmost", True)
                w.lift()
            except Exception:
                pass

    def _focus_entry(self, _e=None):
        """Restore typing after geometry and default mouse bindings finish."""
        if self.state != "active" or self.busy or self._menu_open():
            return
        self._touch()
        if self._focus_job is not None:
            self.root.after_cancel(self._focus_job)
        self._focus_job = self.root.after_idle(self._restore_entry_focus)

    def _restore_entry_focus(self):
        self._focus_job = None
        if (self.state == "active" and not self.busy
                and not self._menu_open() and self.entry.winfo_viewable()):
            self.entry.focus_force()

    def apply_settings(self):
        """Re-style everything after a setting changes (no focus changes)."""
        self.root.configure(bg=BG)
        self.pill.config(text=PILL_LABEL, bg=PILL_BG, fg=PILL_FG,
                         font=F(3, True))
        self.header.config(bg=BAR)
        self.title.config(bg=BAR, fg=MUTED, font=F(-2))
        self.close_lbl.config(bg=BAR, fg=MUTED, font=F(-1))
        self.menu_lbl.config(bg=BAR, fg=MUTED, font=F(-2))
        self.fonts_lbl.config(bg=BAR, font=F(-2))
        self.online_lbl.config(bg=BAR, fg=MUTED, font=F(-2))
        self.text.config(bg=BG, fg=FG, font=F())
        self.text.tag_config("sys", foreground=MUTED)
        self.text.tag_config("link", foreground=LINK_COLOR, underline=True)
        self.entry_wrap.config(bg=BAR)
        self.plus.config(bg=BAR, fg=FG, font=F(3, True))
        self.skull.config(bg=BAR, fg=FG, font=F(3, True))
        self.entry.config(bg=BAR, fg=FG, insertbackground=FG, font=F())
        for tag, (fam, bold, color) in self.font_tags.items():
            self._config_tag(tag, fam, bold, color)
        for m in self.history:               # thumbnails may change size
            m.pop("_photo", None)
            m.pop("_anim", None)
        self._geometry()
        self.redraw()

    def _config_tag(self, tag, family, bold, color):
        font = (family, max(6, FONT_SIZE)) + (("bold",) if bold else ())
        opts = {"font": font}
        if color:
            opts["foreground"] = color
        try:
            self.text.tag_config(tag, **opts)
        except self.tk.TclError:             # odd font: keep the rest
            log("tag font failed: " + traceback.format_exc())
            opts.pop("font", None)
            if opts:
                self.text.tag_config(tag, **opts)

    def _color_tag(self, color):
        """A tag that only sets a text color (kept apart from the font tag,
        so a font problem on one computer can never turn names white)."""
        tag = "col_" + color.lstrip("#")
        if tag not in self.color_tags:
            self.text.tag_config(tag, foreground=color)
            self.color_tags.add(tag)         # only after it really worked
        return tag

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

    # ---- flip: everyone's chat text goes upside down for 5 seconds
    # Only the chat's own text is flipped; nothing on the computer outside
    # the chat is touched. Each person can turn it off in Settings.
    def flip_cmd(self):
        now = time.time()
        if now - self.last_flip_sent < 10:
            self.note("flip needs a few seconds to recharge")
            return
        self.last_flip_sent = now
        self.net.send("", kind="ping", extra={"flip": 1})
        self._flip(None)                    # your own window flips too

    def _flip(self, who):
        """Flip this window for 5 seconds. who is the sender's name, or None
        when you pressed the button yourself."""
        now = time.time()
        if not ALLOW_FLIP:
            if who is None:
                self.note("you flipped everyone's chat (yours stays normal "
                          "because flips are off in your Settings)")
            return
        if who is not None:
            if now - self.last_flip_got < 20:
                return
            self.last_flip_got = now
        log(f"flip started ({'you' if who is None else who})")
        self.flip_until = now + 5
        if self.state != "active":           # show the whole window
            self.set_state("active")
            self.last_activity = time.time() - ACTIVE_IDLE_SECONDS + 7
        self._restyle_flip()
        self._deliver({"type": "sys", "name": "", "text":
                       "you flipped everyone's chat" if who is None
                       else f"{who} flipped your chat!"})
        self.root.after(5100, self._restyle_flip)   # right way up again

    # ---- GIF of the reel (a short screen recording of the reels window)
    def pick_clip_area(self, then=None):
        """Dim the screen and let the person drag a box around the reel."""
        tk = self.tk
        self.busy = True
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        top = tk.Toplevel(self.root)
        top.configure(bg="black")
        if self.root.tk.call("tk", "windowingsystem") == "aqua":
            top.attributes("-fullscreen", True)
        else:
            top.overrideredirect(True)
            top.geometry(f"{sw}x{sh}+0+0")
        try:
            top.attributes("-alpha", 0.3)
        except Exception:
            pass
        top.attributes("-topmost", True)
        cv = tk.Canvas(top, bg="black", highlightthickness=0,
                       cursor="crosshair")
        cv.pack(fill="both", expand=True)
        cv.create_text(sw // 2, 60, fill="white", font=F(4, True),
                       text="Drag a box around the reel window.  "
                            "Right-click or Esc to cancel.")
        st = {}

        def close(_e=None):
            try:
                top.destroy()
            except Exception:
                pass
            self.busy = self.settings_win is not None
            self._touch()
            return "break"

        def down(e):
            st["x0"], st["y0"] = e.x_root, e.y_root
            st["r"] = cv.create_rectangle(e.x, e.y, e.x, e.y, width=3,
                                          outline="#7be08a")

        def move(e):
            if "r" in st:
                cv.coords(st["r"], st["x0"] - top.winfo_rootx(),
                          st["y0"] - top.winfo_rooty(), e.x, e.y)

        def up(e):
            if "x0" not in st:
                return
            x0, y0, x1, y1 = st["x0"], st["y0"], e.x_root, e.y_root
            close()
            box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            if box[2] - box[0] < 60 or box[3] - box[1] < 60:
                self.note("that box was too small, try again")
                return
            self.clip_box = box
            if then is not None:         # let the dim layer vanish first
                self.root.after(300, then)

        cv.bind("<ButtonPress-1>", down)
        cv.bind("<B1-Motion>", move)
        cv.bind("<ButtonRelease-1>", up)
        for b in ("<Button-2>", "<Button-3>"):
            cv.bind(b, close)
        top.bind("<Escape>", close)
        top.focus_force()

    def clip_reel(self, reselect=False):
        """The "gif" button: record a few seconds of the reels window and
        send it to the chat as a GIF."""
        if not PIL_OK:
            self.note("GIFs of the reel need Pillow:  python -m pip install "
                      "pillow  then restart the app")
            return
        if self.clipping:
            self.note("already recording...")
            return
        if self.clip_box is None or reselect:
            self.pick_clip_area(then=self.clip_reel)
            return
        if (sys.platform.startswith("linux") and not self.wayland_warned
                and os.environ.get("XDG_SESSION_TYPE", "").lower()
                == "wayland"):
            self.wayland_warned = True
            self.note("heads up: Wayland desktops often block screen "
                      "capture, so the GIF may come out black. Logging in "
                      "with an X11 session fixes that.")
        scale = 1.0
        if sys.platform == "win32":          # Windows display scaling
            try:
                scale = (ImageGrab.grab().width
                         / max(1, self.root.winfo_screenwidth()))
            except Exception:
                pass
        bbox = tuple(int(round(v * scale)) for v in self.clip_box)
        self.clipping = True
        self.note(f"recording {GIF_SECONDS} seconds of the reel...")
        threading.Thread(target=self._clip_worker,
                         args=(bbox, GIF_SECONDS, GIF_FPS, GIF_WIDTH),
                         daemon=True).start()

    def _clip_worker(self, bbox, seconds, fps, width):
        def say(text):
            self.inbox.put({"type": "sys", "name": "", "text": text})
        try:
            frames, gap = [], 1.0 / fps
            t0 = time.time()
            nxt = t0
            while time.time() - t0 < seconds:
                try:
                    frames.append(ImageGrab.grab(bbox=bbox,
                                                 all_screens=True))
                except TypeError:            # older Pillow
                    frames.append(ImageGrab.grab(bbox=bbox))
                nxt += gap
                wait = nxt - time.time()
                if wait > 0:
                    time.sleep(wait)
            elapsed = time.time() - t0
            if len(frames) < 2:
                say("couldn't record the reel (screen capture too slow)")
                return
            if frames[0].convert("RGB").getextrema() == ((0, 0),) * 3:
                say("the recording came out black: your system is blocking "
                    "screen capture (on a Mac, allow Screen Recording for "
                    "Python in System Settings; on Linux, use an X11 "
                    "session)")
                return
            dur = max(20, int(elapsed / len(frames) * 1000))
            w, h = frames[0].size
            nw = min(width, w)
            nh = max(16, int(h * nw / w))
            small = [f.convert("RGB").resize((nw, nh)) for f in frames]
            data = None
            for sc in (1.0, 0.8, 0.6, 0.45):
                size = (max(16, int(nw * sc)), max(16, int(nh * sc)))
                fr = small if sc == 1.0 else [s.resize(size) for s in small]
                buf = io.BytesIO()
                fr[0].save(buf, "GIF", save_all=True, append_images=fr[1:],
                           duration=dur, loop=0, optimize=True)
                if buf.tell() <= MAX_IMAGE_BYTES:
                    data = buf.getvalue()
                    break
            if data is None:
                say("that GIF came out too big to send; try a shorter or "
                    "narrower one in Settings")
                return
            self.inbox.put({"type": "gif_ready", "data": data})
        except Exception:
            log("reel gif failed: " + traceback.format_exc())
            say("couldn't record the reel (screen capture failed)")
        finally:
            self.clipping = False

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
        if self._upside():
            text = flip_text(text)
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

    # ---- history for people who join late
    # Nothing is saved to disk. Everyone in the room keeps the chat in
    # memory, and when someone joins, one person who is already here hands
    # them the recent text messages. When the last person leaves, the chat
    # is gone. (Sent as quiet "ping" messages, so older versions of the
    # app just ignore them.)
    def _schedule_history(self):
        now = time.time()
        if now - self.last_hist < 3:
            return
        self.last_hist = now
        self.hist_seq += 1
        seq = self.hist_seq
        top = 2500 if self.net.mode == "online" else 600

        def go():
            if seq != self.hist_seq:         # someone else already answered
                return
            try:
                self._send_history()
            except Exception:
                log("history send failed: " + traceback.format_exc())
        self.root.after(random.randint(200, top), go)

    def _send_history(self):
        online = self.net.mode == "online"
        chunk_cap = 3000 if online else 1000       # bytes per message
        total_cap = 7000 if online else 12000      # bytes in all
        picked, used = [], 0
        for m in reversed(self.history):
            if (m.get("type") != "msg" or not m.get("text")
                    or not isinstance(m.get("id"), str)):
                continue
            it = {"id": m["id"], "name": m.get("name", "?"),
                  "text": m["text"][:400], "uid": m.get("uid") or "",
                  "font": m.get("font") or "",
                  "color": m.get("color")
                  or name_color(str(m.get("name", "?")))}
            size = len(json.dumps(it)) + 2
            if size > chunk_cap:
                continue
            if used + size > total_cap:
                break
            picked.append(it)
            used += size
        picked.reverse()
        if not picked:
            return
        for k, it in enumerate(picked):
            it["k"] = k
        chunks, cur, cur_size = [], [], 0
        for it in picked:
            size = len(json.dumps(it)) + 2
            if cur and cur_size + size > chunk_cap:
                chunks.append(cur)
                cur, cur_size = [], 0
            cur.append(it)
            cur_size += size
        if cur:
            chunks.append(cur)
        for i, chunk in enumerate(chunks):
            self.root.after(i * 150, lambda c=chunk: self.net.send(
                "", kind="ping", extra={"items": c}))

    def _take_history(self, msg):
        """Add earlier messages sent by someone already in the room."""
        items, who = msg.get("items"), msg.get("uid")
        if not isinstance(items, list) or not isinstance(who, str):
            return
        if self.hist_from is None:
            self.hist_from = who             # keep to one sender's list
        elif self.hist_from != who:
            return
        have = {m.get("id") for m in self.history}
        lead = 0                             # earlier ones sit at the front
        while lead < len(self.history) and self.history[lead].get("_old"):
            lead += 1
        added = False
        for it in items[:60]:
            if not isinstance(it, dict):
                continue
            mid, k = it.get("id"), it.get("k")
            if (not isinstance(mid, str) or not mid or mid in have
                    or not isinstance(k, int)):
                continue
            name = str(it.get("name", "?"))[:20]
            font = "".join(c for c in str(it.get("font", ""))
                           if c.isprintable())[:60].strip()
            want = font
            if font:
                font = self._usable_font(font, name)
            col = str(it.get("color") or "").lower()
            if not re.fullmatch(r"#[0-9a-f]{6}", col):
                col = ""
            m = {"type": "msg", "id": mid, "name": name, "color": col,
                 "text": str(it.get("text", ""))[:2000], "font": font,
                 "font_want": want if (want and not font) else "",
                 "uid": it.get("uid") if isinstance(it.get("uid"), str)
                 else "", "_old": True, "_hk": k}
            pos = 0
            while pos < lead and self.history[pos]["_hk"] <= k:
                pos += 1
            self.history.insert(pos, m)
            lead += 1
            have.add(mid)
            self.net.seen.add(mid)
            added = True
        del self.history[:-MAX_HISTORY]
        if added and self.state != "collapsed":
            self.redraw()

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
        names = self.text.tag_names(f"@{e.x},{e.y}")
        if any(tag.startswith("img_") for tag in names):
            # The image tag opens a viewer; leave focus with that window.
            return "break"
        if self.state != "active" and any(
                tag.startswith("lnk_") for tag in names):
            return "break"           # a link: open it, don't open the chat
        if self.state != "active":
            self.set_state("active")
        else:
            # Text's default click binding takes focus even when disabled.
            # Restore it afterwards, retaining normal history selection.
            self._focus_entry()

    def _fill_menu(self, m):
        m.add_command(label="Who's online", command=self.show_who)
        m.add_separator()
        if self.game and not self.game["over"] and self.game["mine"]:
            m.add_command(label="End the number guesser",
                          command=self.game_end_cmd)
        else:
            m.add_command(label="Number guesser...", command=self.game_cmd)
        if self.duel and not self.duel["over"]:
            label = ("Stop spectating" if self.duel.get("spectator") else
                     "Quit the duel" if self.duel["state"] == "playing" else
                     "Cancel the duel")
            m.add_command(label=label, command=self.duel_quit_cmd)
        else:
            m.add_command(label="Duel...", command=self.duel_cmd)
            m.add_command(label="Watch duel in progress",
                          command=self._duel_watch_cmd)
            m.add_command(label="Duel solo (testing)",
                          command=self.duel_solo_cmd)
        m.add_command(label="Flip everyone's chat", command=self.flip_cmd)
        m.add_command(label="Send GIF of the reel", command=self.clip_reel)
        m.add_command(label="Pick the reel area again",
                      command=lambda: self.clip_reel(True))
        m.add_command(label="Instagram reels window",
                      command=self.open_reels)
        m.add_separator()
        if self.font_offers or self.font_share_offers:
            m.add_command(label="Get fonts ("
                          f"{len(self.font_offers) + len(self.font_share_offers)})",
                          command=self.fonts_cmd)
        m.add_command(label="Open shared fonts folder",
                      command=self.open_fonts_folder)
        if self.update_info:
            m.add_command(label=f"Update to v{self.update_info['version']}",
                          command=self.update_cmd)
        else:
            m.add_command(label="Check for updates", command=self.update_cmd)
        m.add_command(label="Settings...", command=self.open_settings)
        m.add_command(label="Reset window position",
                      command=self.reset_window_position)
        m.add_separator()
        m.add_command(label="Disconnect and quit", command=self.disconnect)

    def _pop_menu(self, x, y):
        menu = self.tk.Menu(self.root, tearoff=0)
        self._fill_menu(menu)
        self.busy = True                     # keep the chat open meanwhile
        try:
            self._post_menu(menu, x, y)
        finally:
            self.busy = self.settings_win is not None
            self._touch()

    def _header_menu(self, _e=None):
        """The "menu" dropdown in the top bar."""
        w = self.menu_lbl
        self._pop_menu(w.winfo_rootx(), w.winfo_rooty() + w.winfo_height())
        return "break"

    def disconnect(self):
        """Leave the room (everyone sees you leave) and close the program."""
        log("disconnect chosen")
        try:
            self.root.destroy()              # main() then says goodbye
        except Exception:
            pass

    def _link_at(self, index):
        for tag in self.text.tag_names(index):
            if tag in self.link_urls:
                return self.link_urls[tag]
        return None

    def open_link(self, url):
        try:
            host = (urllib.parse.urlparse(url).hostname or "").lower()
            if host == "instagram.com" or host.endswith(".instagram.com"):
                self.open_reels(url)         # the small reels window
            else:
                webbrowser.open(url)
        except Exception:
            log("open link failed: " + traceback.format_exc())
            self.note("couldn't open that link")

    def _link_release(self, url):
        if self.text.tag_ranges("sel"):      # they were selecting, not clicking
            return None
        self.open_link(url)
        return "break"

    def _copy_text(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            self.note("couldn't copy")

    def _selected_chat_text(self):
        try:
            return self.text.get("sel.first", "sel.last")
        except Exception:
            return ""

    def _on_copy(self, _e=None):
        """Ctrl/Cmd+C: copy what's selected in the chat. (Typing-box text
        still copies the normal way.)"""
        try:
            if self.entry.selection_present():
                return None
        except Exception:
            pass
        sel = self._selected_chat_text()
        if sel:
            self._copy_text(sel)
            return "break"
        return None

    def _text_menu(self, e):
        idx = self.text.index(f"@{e.x},{e.y}")
        url = self._link_at(idx)
        sel = self._selected_chat_text()
        line = self.text.get(f"{idx} linestart", f"{idx} lineend").strip()
        menu = self.tk.Menu(self.root, tearoff=0)
        if url:
            menu.add_command(label="Open link",
                             command=lambda: self.open_link(url))
            menu.add_command(label="Copy link",
                             command=lambda: self._copy_text(url))
        if sel:
            menu.add_command(label="Copy",
                             command=lambda: self._copy_text(sel))
        if line:
            menu.add_command(label="Copy this line",
                             command=lambda: self._copy_text(line))
        if menu.index("end") is None:
            return "break"
        self.busy = True                     # keep the chat open meanwhile
        try:
            self._post_menu(menu, e.x_root, e.y_root)
        finally:
            self.busy = self.settings_win is not None
            self._touch()
        return "break"

    def _touch(self):
        self.last_activity = time.time()

    def _drag_start(self, e):
        self._dragging = True
        self._drag_size = self._placed_geometry[2:]
        self._dx, self._dy = e.x_root, e.y_root
        self._touch()

    def _drag_move(self, e):
        if not self._dragging:
            return
        self.anchor_x += e.x_root - self._dx
        self.anchor_bottom += e.y_root - self._dy
        self._dx, self._dy = e.x_root, e.y_root
        self._place(*self._drag_size)
        self._touch()

    def _drag_end(self, _e):
        """Keep the drop reachable for this session; never persist it."""
        self._dragging = False
        self._monitors = display_monitors(self.root)
        self._monitor_name = monitor_for_window(
            *self._placed_geometry, self._monitors).name
        self._geometry()
        self._touch()

    # ---- images
    def _pil_photo(self, im):
        if ImageTk is not None:
            return ImageTk.PhotoImage(im)
        b = io.BytesIO()
        im.convert("RGBA").save(b, "PNG")
        return self.tk.PhotoImage(master=self.root,
                                  data=base64.b64encode(b.getvalue()))

    def make_anim(self, data, max_w, max_h, stream=False):
        """Frames for an animated GIF, or None if it isn't animated."""
        if not data.startswith(b"GIF8"):
            return None
        frames, delays = [], []
        try:
            if PIL_OK:
                im = Image.open(io.BytesIO(data))
                n = getattr(im, "n_frames", 1)
                if n > MAX_GIF_FRAMES and stream and ImageTk is not None:
                    # a long GIF: decode one frame at a time while it plays
                    first = im.convert("RGBA")
                    first.thumbnail((max_w, max_h))
                    return {"disp": ImageTk.PhotoImage(first), "stream": im,
                            "n": n, "size": first.size, "i": 0,
                            "next": time.time() + max(
                                20, int(im.info.get("duration", 100))) / 1000}
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

    def _step_anim(self, a, now):
        if now < a["next"]:
            return
        if a.get("stream"):                      # long GIF: next frame on demand
            a["i"] = (a["i"] + 1) % a["n"]
            im = a["stream"]
            im.seek(a["i"])
            fr = im.convert("RGBA")
            fr.thumbnail(a["size"])
            a["disp"].paste(fr)
            a["next"] = now + max(20, int(im.info.get("duration", 100))) / 1000
            return
        a["i"] = (a["i"] + 1) % len(a["frames"])
        self.root.tk.call(str(a["disp"]), "copy", str(a["frames"][a["i"]]))
        a["next"] = now + a["delays"][a["i"]] / 1000

    def _animate(self):
        try:
            now = time.time()
            self.full_anims[:] = [a for a in self.full_anims
                                  if a["widget"].winfo_exists()]
            for a in self.full_anims:            # viewer windows always play
                self._step_anim(a, now)
            if self.state != "collapsed":
                for a in self.anims:
                    self._step_anim(a, now)
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

    def open_full(self, data, title="Image", stream=False, focus=True,
                  seconds=0, center=False):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        anim = self.make_anim(data, int(sw * 0.8), int(sh * 0.8),
                              stream=stream)
        photo = anim["disp"] if anim else self.make_photo(
            data, int(sw * 0.8), int(sh * 0.8))
        if photo is None:
            return
        top = self.tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg=BG)
        top.attributes("-topmost", True)
        lbl = self.tk.Label(top, image=photo, bg=BG, cursor="hand2")
        lbl.image = photo
        lbl.pack()
        if anim:
            anim["widget"] = lbl
            self.full_anims.append(anim)

        def close(_e=None, refocus=True):
            try:
                top.destroy()
            except Exception:
                return "break"
            if refocus:
                self._focus_entry()
            return "break"

        for w in (top, lbl):
            w.bind("<Button-1>", close)
        top.bind("<Escape>", close)
        top.protocol("WM_DELETE_WINDOW", close)
        if center:
            top.update_idletasks()
            top.geometry(f"+{max(0, (sw - top.winfo_reqwidth()) // 2)}"
                         f"+{max(0, (sh - top.winfo_reqheight()) // 3)}")
        if seconds:                          # closes itself; never grabs focus
            top.after(int(seconds * 1000), lambda: close(refocus=False))
        if focus:
            top.focus_force()
        return top

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

    def _find_skeleton(self):
        """The skeleton-skyrim file next to this script, or None."""
        folder = os.path.dirname(os.path.abspath(__file__))
        try:
            names = os.listdir(folder)
        except OSError:
            return None
        for want in ("skeleton-skyrim.gif", "skeleton-skyrim"):
            for n in names:
                if n.lower() == want:
                    return os.path.join(folder, n)
        for n in sorted(names):
            if n.lower().startswith("skeleton-skyrim."):
                return os.path.join(folder, n)
        return None

    def open_skeleton(self, data, who=""):
        """Show the skeleton GIF in a window of its own."""
        old = getattr(self, "skel_top", None)
        try:
            if old is not None and old.winfo_exists():
                old.destroy()                # one at a time
        except Exception:
            pass
        title = f"{who} sent the skeleton" if who else "Skeleton"
        self.skel_top = self.open_full(
            data, title=title, stream=True, focus=False,
            seconds=SKELETON_SECONDS, center=True)

    def send_skeleton(self):
        """The skull button: the skeleton GIF opens on everyone's screen."""
        now = time.time()
        if now - getattr(self, "_skull_at", 0) < 6:
            if now - getattr(self, "_skull_at", 0) > 1.5:
                self.note("wait a few seconds before sending the skeleton "
                          "again")
            return
        path = self._find_skeleton()
        if path is None:
            self.note("couldn't find skeleton-skyrim.gif in the same folder "
                      "as studychat.py")
            return
        try:
            with open(path, "rb") as f:
                data = f.read(40 * 1024 * 1024)
            if not data.startswith(b"GIF8"):
                raise ValueError("not a GIF")
            if len(data) > MAX_IMAGE_BYTES:
                data = shrink_gif(data, MAX_IMAGE_BYTES)
                if data is None:
                    self.note("the skeleton GIF is too big to send"
                              + ("" if PIL_OK else
                                 " (install Pillow so it can be shrunk)"))
                    return
        except Exception:
            self.note("couldn't read the skeleton GIF (it must be a real "
                      ".gif file)")
            return
        self._skull_at = now
        self.net.send_image(data, extra={"popup": "skeleton"})
        self.open_skeleton(data)             # and on your own screen
        self.note("skeleton sent to everyone")
        self._touch()

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
        self._raise_chat()
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
                self.text.see("1.0" if self._upside() else "end")
            except Exception:
                pass

    def _redraw(self):
        t = self.text
        t.config(state="normal")
        t.delete("1.0", "end")
        msgs = (self._popup_msgs() if self.state == "popup"
                else self.history[-MAX_HISTORY:])
        self.anims = []
        gifs = [m for m in msgs if m.get("type") == "img"
                and isinstance(m.get("data"), bytes)
                and m["data"].startswith(b"GIF8")]
        live = {id(m) for m in gifs[-LIVE_GIFS:]}     # older ones hold still
        for m in gifs:
            if id(m) not in live:
                m.pop("_anim", None)
        self.link_urls = {}
        nlink = 0
        prev_old = False
        upside = time.time() < self.flip_until
        fx = flip_text if upside else str
        for m in (reversed(msgs) if upside else msgs):   # newest on top
            if prev_old and not m.get("_old") and not upside:
                t.insert("end", fx("- earlier messages above -") + "\n", "sys")
            prev_old = bool(m.get("_old"))
            kind = m.get("type")
            if kind in ("join", "leave"):
                word = "joined" if kind == "join" else "left"
                t.insert("end", fx(f"{m['name']} {word}") + "\n", "sys")
                continue
            if kind == "sys":
                t.insert("end", fx(m.get("text", "")) + "\n", "sys")
                continue
            if m.get("uid") == self.net.uid:      # mine: always my current font
                fam = MY_FONT or FONT_FAMILY
            else:                                 # theirs: the font they chose
                fam = m.get("font") or FONT_FAMILY
            # The sender's own color, so everyone sees the same one. (Old
            # versions don't send it, so fall back to the name's color.)
            col = str(m.get("color") or "").lower()
            if not re.fullmatch(r"#[0-9a-f]{6}", col):
                col = name_color(m["name"])
            tag = self._font_tag(fam, True, None, m["name"])
            ttag = self._font_tag(fam)
            ctag = self._color_tag(col)
            if upside and not (kind == "img"
                               and isinstance(m.get("data"), bytes)):
                # turned around, a line reads backwards: text, then name
                t.insert("end", fx(m.get("text", "")), ttag)
                t.insert("end", fx(": "), ttag)
                t.insert("end", fx(m["name"]) + "\n", (tag, ctag))
                t.tag_raise(ctag)
                continue
            t.insert("end", fx(m["name"] + ": "), (tag, ctag))
            t.tag_raise(ctag)
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
            elif upside:
                t.insert("end", fx(m.get("text", "")) + "\n", ttag)
            else:
                for piece, url in split_links(m.get("text", "")):
                    if url is None:
                        t.insert("end", piece, ttag)
                        continue
                    lt = f"lnk_{nlink}"
                    nlink += 1
                    self.link_urls[lt] = url
                    t.insert("end", piece, (ttag, "link", lt))
                    t.tag_bind(lt, "<ButtonRelease-1>",
                               lambda e, u=url: self._link_release(u))
                    t.tag_bind(lt, "<Enter>",
                               lambda e: t.config(cursor="hand2"))
                    t.tag_bind(lt, "<Leave>",
                               lambda e: t.config(cursor="arrow"))
                t.insert("end", "\n", ttag)
        t.config(state="disabled")
        t.see("1.0" if upside else "end")

    def add(self, msg):
        self.history.append(msg)
        del self.history[:-MAX_HISTORY]

    def _on_send(self, _e):
        text = self.entry.get().strip()
        self.entry.delete(0, "end")
        self._touch()
        if not text:
            return
        if text in ("/quit", "/disconnect"):
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
        if text == "/flip":
            self.flip_cmd()
            return
        if text in ("/reelgif", "/reelgif area"):
            self.clip_reel(text.endswith("area"))
            return
        if text == "/getfonts":
            self.fonts_cmd()
            return
        if text == "/fontsfolder":
            self.open_fonts_folder()
            return
        if text in ("/guess", "/numberguess"):
            self.game_cmd()
            return
        if text == "/duel":
            self.duel_cmd()
            return
        if text == "/duel watch":
            self._duel_watch_cmd()
            return
        if text in ("/duel solo", "/solo"):
            self.duel_solo_cmd()
            return
        if text == "/reels" or text.startswith("/reels "):
            self.open_reels(text[6:])
            return
        if text.startswith("/gif "):
            self.send_gif_link(text[5:].strip())
            return
        extra = {"color": name_color(self.net.name)}
        if MY_FONT:
            extra["font"] = MY_FONT
        self.add(self.net.send(text, extra=extra))
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

    # ---- shared fonts folder (see the notes above scan_font_folder)
    def _fonts_dir(self):
        return os.path.expanduser(
            getattr(self, "fonts_dir_override", None) or FONT_FOLDER)

    def _fonts_label(self):
        """The "get fonts (n)" link in the top bar."""
        n = len(self.font_offers) + len(self.font_share_offers)
        if n:
            self.fonts_lbl.config(text=f"get fonts ({n})")
            self.fonts_lbl.pack(side="right", padx=6)
        else:
            self.fonts_lbl.pack_forget()

    def open_fonts_folder(self):
        try:
            open_folder(self._fonts_dir())
        except Exception:
            log("open folder failed: " + traceback.format_exc())
        self.note("shared fonts folder: " + self._fonts_dir() + "  (font "
                  "files you put in it are offered to everyone in the room)")

    def _fonts_tick(self, now):
        """Every so often: look at the folder and tell the room what's in it."""
        if not FONT_SYNC or now < self.font_due:
            return
        self.font_due = now + 15
        folder = self._fonts_dir()
        try:
            fresh = not os.path.isdir(folder)
            os.makedirs(folder, exist_ok=True)
        except OSError:
            return
        if fresh and not self.font_folder_noted:
            self.font_folder_noted = True
            self.note("shared fonts folder: " + folder + "  (font files you "
                      "put in it are offered to everyone in the room)")
        self.font_mine = scan_font_folder(folder, self.font_cache)
        self.font_seen.update(self.font_mine)    # never offer me my own fonts
        mine = frozenset(self.font_mine)
        if (mine and mine != self.font_announced
                and getattr(self.net, "join_ok", True)):
            self.font_announced = mine
            items = [{"h": h, "n": i["n"], "s": i["s"]}
                     for h, i in self.font_mine.items()]
            self.net.send("", kind="ping", extra={"fontlist": items})
        elif not mine:
            self.font_announced = frozenset()
        for h, w in list(self.font_wanted.items()):      # nobody answered
            if now > w["until"]:
                del self.font_wanted[h]
                self.note(f"couldn't get the font \"{w['n']}\" from "
                          f"{w['who']}")

    def _fontlist_msg(self, msg):
        """Someone told the room which fonts are in their shared folder."""
        if not FONT_SYNC:
            return
        uid, who = msg.get("uid"), msg["name"]
        if not (isinstance(uid, str) and uid):
            return
        theirs, new = set(), []
        for it in msg["fontlist"][:MAX_SHARED_FONTS]:
            if not isinstance(it, dict):
                continue
            h, n, s = it.get("h"), it.get("n"), it.get("s")
            if not (isinstance(h, str) and re.fullmatch(r"[0-9a-f]{16}", h)
                    and isinstance(n, str) and isinstance(s, int)
                    and not isinstance(s, bool) and 0 < s <= MAX_FONT_BYTES):
                continue
            theirs.add(h)
            if (h in self.font_seen or h in self.font_wanted
                    or h in self.font_share_offers):
                continue
            n = safe_font_name(n)
            self.font_share_offers[h] = {"h": h, "n": n, "s": s,
                                         "uid": uid, "who": who}
            new.append(n)
        if theirs >= set(self.font_mine):    # they already told everyone mine
            self.font_announced = frozenset(self.font_mine)
        if new:
            self._fonts_label()
            more = "..." if len(new) > 3 else ""
            self._deliver({"type": "sys", "name": "", "text":
                           f"{who} shared {len(new)} font"
                           f"{'s' if len(new) != 1 else ''} "
                           f"({', '.join(new[:3])}{more}). Click \"get fonts\""
                           " in the top bar (or type /getfonts) to install."})

    def _request_fonts(self, offers):
        """The person said yes: ask each friend for the font they shared."""
        self.note("asking for fonts...")
        for k, o in enumerate(offers):
            self.font_share_offers.pop(o["h"], None)
            self.font_wanted[o["h"]] = {"n": o["n"], "uid": o["uid"],
                                        "who": o["who"],
                                        "until": time.time() + 90}
            self.root.after(300 * k, lambda o=o: self.net.send(
                "", kind="ping",
                extra={"fontreq": {"h": o["h"], "to": o["uid"]}}))

    def _fontreq_msg(self, msg):
        """Someone asks me for a font from my shared folder."""
        req = msg["fontreq"]
        h, who = req.get("h"), msg.get("uid")
        if (not FONT_SYNC or req.get("to") != self.net.uid
                or not isinstance(h, str) or not isinstance(who, str)
                or not who):
            return
        info = self.font_mine.get(h)         # only files in my shared folder
        if not info:
            return
        now = time.time()
        self.font_served = [t for t in self.font_served if now - t < 60]
        if len(self.font_served) >= 6:       # don't let anyone drain uploads
            return
        try:
            with open(info["path"], "rb") as f:
                data = f.read(MAX_FONT_BYTES + 1)
        except OSError:
            return
        if not looks_like_font(data) or font_hash(data) != h:
            return
        self.font_served.append(now)
        self.net.send_blob(data, {"blob": "font", "h": h, "fname": info["n"],
                                  "to": who})

    def _fontblob_msg(self, msg):
        """A font file arrived. Only accepted if I asked that friend for it."""
        h, data = msg.get("h"), msg.get("data")
        w = self.font_wanted.get(h) if isinstance(h, str) else None
        if (not w or msg.get("to") != self.net.uid
                or msg.get("uid") != w["uid"]):
            return                           # I never asked for this
        del self.font_wanted[h]
        if not looks_like_font(data) or font_hash(data) != h:
            self.note(f"the font \"{w['n']}\" from {w['who']} was damaged, "
                      "so it was skipped")
            return
        self.font_seen.add(h)
        threading.Thread(target=self._font_file_worker,
                         args=(bytes(data), w["n"], h), daemon=True).start()

    def _on_font_fail(self, msg):
        h = msg.get("h")
        w = self.font_wanted.pop(h, None) if isinstance(h, str) else None
        if w:
            self.note(f"couldn't download the font \"{w['n']}\" from "
                      f"{w['who']}")

    def _font_file_worker(self, data, name, h):
        fam = font_family_name(data) or os.path.splitext(name)[0]
        try:
            try:                             # keep a copy in the shared folder
                save_to_font_folder(self._fonts_dir(), data, name)
            except OSError:
                log("couldn't copy a font to the shared folder")
            ext = ".otf" if data[:4] == b"OTTO" else ".ttf"
            install_font_file(data, f"sc-{h[:8]}-{safe_font_name(name, ext)}")
            self.inbox.put({"type": "fonts_done", "ok": [fam], "failed": []})
        except Exception:
            log("font install failed: " + traceback.format_exc())
            self.inbox.put({"type": "fonts_done", "ok": [], "failed": [fam]})

    # ---- number guesser
    # One person picks a secret number. Everyone else gets a popup and one
    # guess, and a wrong guess ends that person's turn. The secret never
    # leaves the host's computer: guesses go to the host, who answers each
    # one. A wrong result ends the guesser's turn, but never exits their app.
    GAME_MAX = 1_000_000
    GAME_SECONDS = 900

    @staticmethod
    def _whole(v, lo, hi):
        """v if it's a whole number from lo to hi, else None."""
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            return None
        return v

    @staticmethod
    def _int_text(s):
        try:
            return int(str(s).strip())
        except ValueError:
            return None

    def game_cmd(self):
        """Menu or /guess: pick a secret number for everyone else to guess."""
        G = self.game
        if G and not G["over"]:
            who = "you are" if G["mine"] else f"{G['host']} is"
            self.note(f"{who} already running a number guesser")
            return
        self._game_host_window()

    def game_end_cmd(self):
        G = self.game
        if not (G and G["mine"] and not G["over"]):
            return
        self.net.send("", kind="ping",
                      extra={"game": {"op": "end", "gid": G["gid"]}})
        G["over"] = True
        self.note("you ended the number guesser")

    def _game_host_window(self):
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title("Number guesser")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        self.busy = True

        def label(text, fg=FG, font=None):
            lb = tk.Label(win, text=text, bg=BG, fg=fg, font=font or F(),
                          justify="left")
            lb.pack(anchor="w", padx=14, pady=(8, 0))
            return lb

        label("Pick a secret number", font=F(2, True))
        label("Everyone else gets a popup and one guess.\n"
              "A wrong guess ends their turn, but keeps chat connected.",
              fg=MUTED)
        label("Your number:")
        secret = tk.Entry(win, show="*", font=F())   # hidden: no peeking
        secret.pack(fill="x", padx=14)
        label("Highest it could be (they guess from 1 up to this):")
        top = tk.Entry(win, font=F())
        top.insert(0, "10")
        top.pack(fill="x", padx=14)
        err = label("", fg="#ff7a7a")

        def close(_e=None):
            try:
                win.destroy()
            except Exception:
                pass
            self.busy = self.settings_win is not None
            self._touch()

        def go(_e=None):
            mx = self._whole(self._int_text(top.get()), 2, self.GAME_MAX)
            if mx is None:
                err.config(text="The highest number must be a whole number "
                                f"from 2 to {self.GAME_MAX:,}.")
                return
            n = self._whole(self._int_text(secret.get()), 1, mx)
            if n is None:
                err.config(text=f"Your number must be a whole number from "
                                f"1 to {mx}.")
                return
            close()
            self._game_start(n, mx)

        row = tk.Frame(win, bg=BG)
        row.pack(pady=12)
        tk.Button(row, text="Start", width=10, command=go).pack(
            side="left", padx=6)
        tk.Button(row, text="Cancel", width=10, command=close).pack(
            side="left", padx=6)
        for w in (secret, top):
            w.bind("<Return>", go)
        win.bind("<Escape>", close)
        win.protocol("WM_DELETE_WINDOW", close)
        self._center(win)
        win.focus_force()
        secret.focus_force()

    def _center(self, win):
        try:
            win.update_idletasks()
            w, h = win.winfo_reqwidth(), win.winfo_reqheight()
            win.geometry("+%d+%d" % (
                max(0, (self.root.winfo_screenwidth() - w) // 2),
                max(0, (self.root.winfo_screenheight() - h) // 3)))
        except Exception:
            pass

    def _game_start(self, secret, mx):
        gid = uuid.uuid4().hex[:12]
        self.game = {"gid": gid, "host_uid": self.net.uid,
                     "host": self.net.name, "max": mx, "mine": True,
                     "secret": secret, "over": False, "t0": time.time(),
                     "guessed": {}, "my_guess": None, "win": None, "ui": None}
        self.net.send("", kind="ping",
                      extra={"game": {"op": "start", "gid": gid, "max": mx}})
        self.note(f"you started the number guesser (1 to {mx}). Everyone "
                  "else got a popup. Use the menu to end it.")

    def _game_msg(self, msg):
        """Everything the number guesser sends or receives. Messages come
        from other computers, so every field is checked."""
        g, uid = msg["game"], msg.get("uid")
        if not isinstance(uid, str) or not uid:
            return
        op, gid = g.get("op"), g.get("gid")
        if not (isinstance(gid, str) and re.fullmatch(r"[0-9a-f]{12}", gid)):
            return
        G = self.game
        if op == "start":
            mx = self._whole(g.get("max"), 2, self.GAME_MAX)
            if mx is None or (G and not G["over"]):   # one game at a time
                return
            self.game = {"gid": gid, "host_uid": uid, "host": msg["name"],
                         "max": mx, "mine": False, "secret": None,
                         "over": False, "t0": time.time(), "guessed": {},
                         "my_guess": None, "win": None, "ui": None}
            self.note(f"{msg['name']} started a number guesser")
            try:
                self._game_popup()
            except Exception:
                log("game popup failed: " + traceback.format_exc())
            return
        if not G or G["gid"] != gid or G["over"]:
            return
        if op == "guess" and G["mine"]:                # I'm the host
            n = self._whole(g.get("n"), 1, G["max"])
            if n is None:
                return
            first = uid not in G["guessed"]
            if first:
                G["guessed"][uid] = (n, n == G["secret"])
            n, ok = G["guessed"][uid]    # asked twice? same answer again
            res = {"op": "result", "gid": gid, "guid": uid,
                   "gname": msg["name"][:20], "n": n, "ok": ok}
            if ok:
                res["secret"] = G["secret"]
            self.net.send("", kind="ping", extra={"game": res})
            if first:
                self._game_announce(msg["name"], n, ok, G["secret"])
                if ok:
                    G["over"] = True
        elif op == "result" and not G["mine"] and uid == G["host_uid"]:
            n = self._whole(g.get("n"), 1, G["max"])
            guid, ok = g.get("guid"), g.get("ok")
            gname = str(g.get("gname", "?"))[:20]
            secret = self._whole(g.get("secret"), 1, G["max"])
            if (n is None or not isinstance(guid, str)
                    or type(ok) is not bool or (ok and secret != n)):
                return
            # Only a guess I made myself can disconnect me.
            mine = guid == self.net.uid and G["my_guess"] == n
            self._game_announce(gname, n, ok, secret)
            if mine and not ok:
                G["over"] = True
            elif ok:
                G["over"] = True
            self._game_result_ui(mine, ok, gname, n, secret)
        elif op == "end" and not G["mine"] and uid == G["host_uid"]:
            G["over"] = True
            self._game_close_window()
            self.note(f"{G['host']} ended the number guesser")

    def _game_announce(self, gname, n, ok, secret):
        self._deliver({"type": "sys", "name": "", "text":
                       f"{gname} guessed {n} and got it! The number was "
                       f"{secret}." if ok else
                       f"{gname} guessed {n}: wrong! {gname} is out for "
                       "this round."})

    def _game_popup(self):
        """The window that appears for everyone except the host."""
        G, tk = self.game, self.tk
        win = tk.Toplevel(self.root)
        win.title("Number guesser")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        self.busy = True
        title = tk.Label(win, text=f"{G['host']} is thinking of a number",
                         bg=BG, fg=FG, font=F(3, True))
        title.pack(padx=20, pady=(16, 4))
        info = tk.Label(win, bg=BG, fg=MUTED, font=F(), justify="center",
                        text=f"Pick a whole number from 1 to {G['max']}.\n"
                             "You only get one guess. A wrong guess ends "
                             "your turn, but keeps chat connected.")
        info.pack(padx=20)
        entry = tk.Entry(win, font=F(2), justify="center", width=10)
        entry.pack(pady=10)
        status = tk.Label(win, text="", bg=BG, fg="#ff7a7a", font=F())
        status.pack()
        row = tk.Frame(win, bg=BG)
        row.pack(pady=(4, 16))
        guess_btn = tk.Button(row, text="Guess", width=10,
                              command=self._game_submit)
        guess_btn.pack(side="left", padx=6)
        skip_btn = tk.Button(row, text="No thanks", width=10,
                             command=self._game_skip)
        skip_btn.pack(side="left", padx=6)
        entry.bind("<Return>", lambda e: self._game_submit())
        win.bind("<Escape>", lambda e: self._game_skip())
        win.protocol("WM_DELETE_WINDOW", self._game_skip)
        G["win"] = win
        G["ui"] = {"title": title, "info": info, "entry": entry,
                   "status": status, "guess": guess_btn, "skip": skip_btn}
        self._center(win)
        win.focus_force()
        entry.focus_force()

    def _game_submit(self):
        G = self.game
        if (not G or G["mine"] or G["over"] or G["my_guess"] is not None
                or not G.get("ui")):
            return
        ui = G["ui"]
        n = self._whole(self._int_text(ui["entry"].get()), 1, G["max"])
        if n is None:
            ui["status"].config(
                text=f"Enter a whole number from 1 to {G['max']}")
            return
        G["my_guess"], G["asked_at"], G["resent"] = n, time.time(), False
        self._game_send_guess(n)
        ui["status"].config(text=f"Waiting for {G['host']}...", fg=MUTED)
        for k in ("entry", "guess", "skip"):
            try:
                ui[k].config(state="disabled")
            except Exception:
                pass

    def _game_send_guess(self, n):
        G = self.game
        self.net.send("", kind="ping", extra={
            "game": {"op": "guess", "gid": G["gid"], "n": n}})

    def _game_skip(self):
        """"No thanks": close the popup. Skipping is never punished."""
        self._game_close_window()

    def _game_result_ui(self, mine, ok, gname, n, secret):
        G = self.game
        ui = G.get("ui") if G else None
        if not ui:
            if mine and not ok:
                self.root.after(3000, self.disconnect)
            return
        if ok:
            text = (f"Awesome! You got it!\nThe number was {n}." if mine else
                    f"{gname} got it!\nThe number was {secret}.")
            color = "#7be08a"
        elif mine:
            text = (f"Wrong! The number wasn't {n}.\n"
                    "Study Chat will now close.")
            color = "#ff7a7a"
        else:
            return                           # someone else missed: keep going
        for k in ("info", "entry", "status", "guess", "skip"):
            try:
                ui[k].pack_forget()
            except Exception:
                pass
        ui["title"].config(text=text, fg=color)
        gid = G["gid"]
        if mine and not ok:
            self.root.after(3000, self.disconnect)
        else:
            self.root.after(5000, lambda: self._game_close_window(gid))

    def _game_close_window(self, gid=None):
        G = self.game
        if gid is not None and (not G or G["gid"] != gid):
            return
        win = G.get("win") if G else None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
            G["win"] = G["ui"] = None
        self.busy = self.settings_win is not None
        self._touch()

    def _game_peer_left(self, uid):
        G = self.game
        if G and not G["mine"] and not G["over"] and uid == G["host_uid"]:
            G["over"] = True
            self._game_close_window()
            self.note(f"{G['host']} left, so the number guesser ended")

    def _game_tick(self, now):
        G = self.game
        if not G or G["over"]:
            return
        if now - G["t0"] > self.GAME_SECONDS:        # nobody finished it
            if G["mine"]:
                self.net.send("", kind="ping",
                              extra={"game": {"op": "end", "gid": G["gid"]}})
            G["over"] = True
            self._game_close_window()
            self.note("the number guesser timed out")
            return
        if G["mine"] or G["my_guess"] is None:
            return
        waited = now - G["asked_at"]
        if waited > 20 and not G["resent"]:          # the guess may be lost
            G["resent"] = True
            self._game_send_guess(G["my_guess"])
        elif waited > 50 and G.get("ui") and not G.get("gave_up"):
            G["gave_up"] = True                      # never kick without an answer
            G["ui"]["status"].config(
                text=f"No answer from {G['host']} yet.", fg="#ff7a7a")
            try:
                G["ui"]["skip"].config(state="normal")
            except Exception:
                pass

    # ---- duel
    # /duel challenges the room; the first person to click Accept fights
    # the challenger. The fight is turn based and every laptop plays the
    # identical fight with duel_round(), so the only thing ever sent is a
    # pick: ONE small message per pick, and none at all on a turn where a
    # player has no choice (winding up a heavy, or stunned). The free relay
    # allows very few posts a minute, so there is no per-turn ack or polling.
    # Spectators can request a single state snapshot; gameplay picks are only
    # said again if the other side stays silent for a long time.
    # Messages (all inside a "duel" ping, so old versions ignore them):
    #   challenge / cancel / accept / start / watch / watch_list / snap
    #   p  = a pick {r: turn, m: move}. The challenger's first pick also
    #        says who was chosen (vs) for older peers.
    #   n  = "I'm stuck on turn r, please say your pick again"
    #   q  = I quit
    DUEL_SECONDS = 1800
    DUEL_RESEND = (25, 50, 100)          # seconds before each repeat
    DUEL_ACCEPT_RESEND = (20, 40)        # then the accept is dropped at 60
    DUEL_REPLY_GAP = 8                   # min seconds between two replies

    def _duel_blank(self, gid, host_uid, host, mine):
        return {"gid": gid, "host_uid": host_uid, "host": host, "mine": mine,
                "state": "waiting" if mine else "invited", "over": False,
                "t0": time.time(), "me": None, "uids": [None, None],
                "names": ["", ""], "S": None, "r": 1, "picks": {},
                "hist": {}, "pick": None, "anim": False, "win": None,
                "ui": None, "accept_at": 0, "accept_n": 0, "last": "",
                "pop": None, "out": None, "resends": 0, "next_resend": 0,
                "reply_at": {}, "go": None, "quit": False,
                "spectator_requests": {}}

    def duel_cmd(self):
        """/duel or the menu: challenge the room (or cancel your challenge)."""
        D = self.duel
        if D and not D["over"]:
            if D["mine"] and D["state"] == "waiting":
                self._duel_send({"op": "cancel"})
                self._duel_over("you cancelled the duel challenge")
            elif D["state"] == "playing":
                self.duel_quit_cmd()
            else:
                self.note(f"{D['host']} already has a duel challenge up")
            return
        gid = uuid.uuid4().hex[:12]
        self.duel = self._duel_blank(gid, self.net.uid, self.net.name, True)
        self._duel_send({"op": "challenge"})
        self.note("you challenged the room to a duel. Waiting for someone "
                  "to accept (type /duel again to cancel)")

    def _duel_watch_cmd(self):
        D = self.duel
        if D and not D["over"]:
            self.note("finish or stop your current duel before spectating")
            return
        self.net.send("", kind="ping", extra={"duel": {"op": "watch_list"}})
        self.note("looking for a duel in progress...")

    def duel_solo_cmd(self):
        """Testing: one person plays both fighters. Nothing is sent."""
        D = self.duel
        if D and not D["over"]:
            self.note("finish or close the current duel first")
            return
        gid = uuid.uuid4().hex[:12]
        self.duel = self._duel_blank(gid, self.net.uid, self.net.name, True)
        self.duel["solo"] = True
        self._duel_start([self.net.uid, "solo"],
                         [self.net.name + " 1", self.net.name + " 2"])
        self.note("solo duel: you pick for both fighters")

    def duel_quit_cmd(self):
        D = self.duel
        if not D or D["over"]:
            return
        if D.get("spectator"):
            self._duel_close_window()
            return
        if D["state"] == "playing":
            self._duel_forfeit()
        elif D["mine"] and D["state"] == "waiting":
            self.duel_cmd()

    def _duel_send(self, d):
        if self.duel.get("solo"):
            return                           # solo: nobody to tell
        d = dict(d)
        d["gid"] = self.duel["gid"]
        self.net.send("", kind="ping", extra={"duel": d})

    def _duel_over(self, note=None):
        D = self.duel
        if not D:
            return
        D["over"] = True
        self._duel_close_popup()
        if note:
            self.note(note)

    def _duel_close_popup(self):
        D = self.duel
        pop = D.get("pop") if D else None
        if pop is not None:
            try:
                pop.destroy()
            except Exception:
                pass
            D["pop"] = None
        self.busy = (self.settings_win is not None
                     or bool(D and D.get("win")))
        self._touch()

    # ---- receiving
    def _duel_msg(self, msg):
        """Everything the duel receives. Fields come from other computers,
        so every one is checked."""
        d, uid = msg["duel"], msg.get("uid")
        if not isinstance(uid, str) or not uid:
            return
        op, gid = d.get("op"), d.get("gid")
        if op == "watch_list":
            D = self.duel
            if (D and D["mine"] and D["state"] == "playing"
                    and not D["over"] and not D.get("solo")
                    and uid not in D["uids"]):
                self._duel_send_snapshot(uid)
            return
        if not (isinstance(gid, str) and re.fullmatch(r"[0-9a-f]{12}", gid)):
            return
        D = self.duel
        name = str(msg.get("name", "?"))[:20]
        if op == "challenge":
            if D and not D["over"]:
                return                               # one duel at a time
            self.duel = self._duel_blank(gid, uid, name, False)
            self.note(f"{name} challenged the room to a duel")
            try:
                self._duel_popup()
            except Exception:
                log("duel popup failed: " + traceback.format_exc())
            return
        if op == "start" and (not D or D["gid"] != gid):
            return
        if op == "snap" and d.get("p2") == self.net.uid \
                and (not D or D["gid"] != gid or D["over"]):
            u2, n1, n2 = d.get("u2"), d.get("n1"), d.get("n2")
            if (isinstance(u2, str) and u2 and isinstance(n1, str)
                    and isinstance(n2, str) and uid != self.net.uid):
                self._duel_spectator_start(gid, uid, n1[:20], u2, n2[:20])
                if (self.duel and self.duel["gid"] == gid
                        and self.duel.get("spectator")):
                    self._duel_spectator_snapshot(d)
            return
        if not D or D["gid"] != gid:
            return
        if D["over"]:
            # A finished fight still answers "say that again": the other
            # side may be missing the pick that ended it.
            if D["state"] == "playing" and uid in D["uids"] \
                    and uid != self.net.uid and d.get("re") == 1:
                self._duel_reply(self._whole(d.get("r"), 1, 100000))
            elif D["state"] == "playing" and uid in D["uids"] \
                    and uid != self.net.uid:
                self._duel_rematch_msg(d, uid, name)
            return
        if op == "cancel" and uid == D["host_uid"] and not D["mine"] \
                and D["state"] in ("invited", "accepting"):
            self._duel_over(f"{D['host']} cancelled the duel")
        elif op == "accept" and D["mine"] and D["state"] == "waiting":
            # The first accept wins. A separate start message opens both
            # duel windows before either player has to pick a move.
            self._duel_send({"op": "start", "p2": uid,
                             "n1": self.net.name, "n2": name})
            self._duel_start([self.net.uid, uid], [self.net.name, name])
            D["go"] = {"vs": uid, "n1": name}
            self.note(f"{name} accepted your duel! Pick your first move")
        elif op == "accept" and D["mine"] and D["state"] == "playing" \
                and uid == D["uids"][1]:
            if D["hist"].get(1) is None:
                self._duel_send({"op": "start", "p2": uid,
                                 "n1": self.net.name,
                                 "n2": D["names"][1]})
            else:
                self._duel_reply(1)                  # they missed our pick
        elif op == "start" and not D["mine"] \
                and uid == D["host_uid"] \
                and D["state"] in ("invited", "accepting"):
            if d.get("p2") != self.net.uid:
                self._duel_over()
                return
            host_name = str(d.get("n1", D["host"]))[:20]
            self._duel_close_popup()
            self._duel_start([uid, self.net.uid],
                             [host_name, self.net.name])
        elif op == "p" and uid == D["host_uid"] and not D["mine"] \
                and D["state"] in ("invited", "accepting") and "vs" in d:
            if d.get("vs") == self.net.uid:          # the challenger chose us
                self._duel_close_popup()
                self._duel_start([uid, self.net.uid],
                                 [D["host"], self.net.name])
                self._duel_take(msg, d, uid)
            else:
                self._duel_over()                    # someone else was picked
        elif op == "watch" and D["mine"] and D["state"] == "playing" \
                and not D.get("spectator"):
            self._duel_send_snapshot(uid)
        elif D["state"] == "playing" and uid in D["uids"] \
                and uid != self.net.uid:
            if D.get("spectator") and op == "snap" and uid == D["host_uid"]:
                self._duel_spectator_snapshot(d)
            elif D.get("spectator") and op == "q":
                self._duel_finish(1 - D["uids"].index(uid), "forfeit")
            elif op == "watch" and D["mine"] and not D.get("spectator"):
                self._duel_send_snapshot(uid)
            else:
                self._duel_take(msg, d, uid)

    def _duel_spectator_start(self, gid, host_uid, host_name, guest_uid,
                              guest_name):
        D = self.duel
        if D and not D["over"] and D.get("gid") != gid:
            return
        if D and D.get("gid") == gid and D.get("spectator"):
            return
        if D:
            self._duel_close_popup()
            if D.get("win"):
                self._duel_close_window()
        D = self._duel_blank(gid, host_uid, host_name, False)
        D.update(state="playing", uids=[host_uid, guest_uid],
                 names=[host_name, guest_name], me=0, S=duel_new(),
                 r=1, spectator=True, picks={}, hist={})
        self.duel = D
        self.note(f"Watching {host_name} vs {guest_name}")
        self._duel_window()
        self._duel_begin_round()

    def _duel_send_snapshot(self, uid):
        D = self.duel
        if (not D or not D.get("S") or D["over"]
                or not isinstance(uid, str) or len(uid) > 100
                or uid in D["uids"]):
            return
        now = time.time()
        requests = D.setdefault("spectator_requests", {})
        if now - requests.get(uid, 0) < 3:
            return
        requests[uid] = now
        pending = []
        if not D["anim"]:
            pending = [[r, i, move] for (r, i), move in D["picks"].items()
                       if r == D["r"]]
        self._duel_send({
            "op": "snap", "p2": uid, "u2": D["uids"][1],
            "n1": D["names"][0], "n2": D["names"][1],
            "r": D["S"]["round"] + 1 if D["anim"] else D["r"],
            "S": D["S"], "picks": pending,
            "last": D["last"][:300],
        })

    @staticmethod
    def _duel_valid_snapshot(state):
        if not isinstance(state, dict):
            return False
        players = state.get("p")
        if not isinstance(players, list) or len(players) != 2:
            return False
        for fighter in players:
            if not isinstance(fighter, dict):
                return False
            x, facing = fighter.get("x"), fighter.get("f")
            hp, stun = fighter.get("hp"), fighter.get("stun")
            move, timer = fighter.get("move"), fighter.get("t")
            if (type(x) is not int or not 0 <= x <= DUEL_W
                    or type(facing) is not int or facing not in (-1, 1)
                    or type(hp) is not int or not 0 <= hp <= DUEL_HP
                    or type(stun) is not int or not 0 <= stun <= 100
                    or type(timer) is not int or not 0 <= timer <= 100
                    or (move is not None and (
                        not isinstance(move, str) or move not in DUEL_MOVES))):
                return False
        winner = state.get("winner")
        return (type(state.get("round")) is int
                and 0 <= state["round"] <= 100000
                and type(state.get("over")) is bool
                and (winner is None or
                     (type(winner) is int and winner in (-1, 0, 1))))

    def _duel_spectator_snapshot(self, d):
        D = self.duel
        if (not D or not D.get("spectator")
                or d.get("p2") != self.net.uid
                or D.get("anim")
                or not self._duel_valid_snapshot(d.get("S"))):
            return
        round_no = self._whole(d.get("r"), 1, 100000)
        if round_no is None:
            return
        if D["S"] and d["S"]["round"] < D["S"]["round"]:
            return
        picks = {}
        raw_picks = d.get("picks", [])
        if not isinstance(raw_picks, list) or len(raw_picks) > 2:
            return
        for item in raw_picks:
            if (not isinstance(item, list) or len(item) != 3
                    or type(item[0]) is not int or item[0] != round_no
                    or type(item[1]) is not int or item[1] not in (0, 1)
                    or not isinstance(item[2], str)
                    or item[2] not in DUEL_MOVES):
                return
            picks[(item[0], item[1])] = item[2]
        D["S"] = d["S"]
        D["r"] = round_no
        D["picks"] = picks
        D["last"] = str(d.get("last", ""))[:300]
        if D["S"]["over"]:
            self._duel_finish(D["S"]["winner"], "ko")
        else:
            self._duel_begin_round()

    def _duel_take(self, msg, d, uid):
        """A pick, a nudge or a quit from our opponent."""
        D = self.duel
        idx = D["uids"].index(uid)
        op = d.get("op")
        r = self._whole(d.get("r"), 1, 100000)
        if op == "q":
            self._duel_finish(1 - idx, "forfeit")
            return
        if op not in ("p", "n") or r is None:
            return
        if d.get("re") == 1:
            self._duel_reply(r)          # they are missing something of ours
        m = d.get("m")
        if (op == "p" and isinstance(m, str) and m in DUEL_MOVES
                and D["r"] <= r <= D["r"] + 3
                and (r, idx) not in D["picks"]):
            D["picks"][(r, idx)] = m
            self._duel_progress()

    def _duel_reply(self, r):
        """Say our pick for turn r again (the other side asked for it), but
        never more than once every few seconds for the same turn."""
        D = self.duel
        now = time.time()
        if r is None or now - D["reply_at"].get(r, 0) < self.DUEL_REPLY_GAP:
            return
        if D["quit"]:
            D["reply_at"][r] = now
            self._duel_send({"op": "q"})
            return
        m = D["hist"].get(r)
        if m is None:
            return
        D["reply_at"][r] = now
        out = {"op": "p", "r": r, "m": m}
        if D["mine"] and r == 1 and D["go"]:
            out.update(D["go"])
        self._duel_send(out)

    # ---- starting
    def _duel_popup(self):
        D, tk = self.duel, self.tk
        win = tk.Toplevel(self.root)
        win.title("Duel")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        self.busy = True
        tk.Label(win, text=f"{D['host']} wants to duel!", bg=BG, fg=FG,
                 font=F(3, True)).pack(padx=24, pady=(16, 4))
        tk.Label(win, text="A tiny turn-based fighting game. Each turn you\n"
                 f"both pick a move. {DUEL_HP} HP each, first to 0 loses.\n"
                 "Only one person can accept.", bg=BG, fg=MUTED, font=F(),
                 justify="center").pack(padx=20)
        status = tk.Label(win, text="", bg=BG, fg=MUTED, font=F())
        status.pack(pady=(6, 0))
        row = tk.Frame(win, bg=BG)
        row.pack(pady=(6, 16))
        acc = tk.Button(row, text="Accept", width=10,
                        command=self._duel_accept)
        acc.pack(side="left", padx=6)
        tk.Button(row, text="No thanks", width=10,
                  command=self._duel_decline).pack(side="left", padx=6)
        win.bind("<Escape>", lambda e: self._duel_decline())
        win.protocol("WM_DELETE_WINDOW", self._duel_decline)
        D["pop"], D["pop_status"], D["pop_acc"] = win, status, acc
        self._center(win)

    def _duel_accept(self):
        D = self.duel
        if not D or D["over"] or D["state"] != "invited":
            return
        D["state"] = "accepting"
        D["accept_at"], D["accept_n"] = time.time(), 1
        self._duel_send({"op": "accept"})
        try:
            D["pop_status"].config(text=f"Waiting for {D['host']}...")
            D["pop_acc"].config(state="disabled")
        except Exception:
            pass

    def _duel_decline(self):
        D = self.duel
        if D and not D["over"] and D["state"] in ("invited", "accepting"):
            D["over"] = True                         # ignoring is never punished
        self._duel_close_popup()

    def _duel_start(self, uids, names):
        D = self.duel
        D.update(state="playing", uids=uids, names=names,
                 me=uids.index(self.net.uid), S=duel_new(), r=1,
                 t0=time.time())
        self._duel_window()
        self._duel_begin_round()

    def _duel_rematch(self):
        D = self.duel
        if not D or not D["over"] or D["state"] != "playing":
            return
        if D.get("solo"):
            self._duel_restart(uuid.uuid4().hex[:12])
            return
        if D.get("rematch_state") not in (None, "ready", "declined"):
            return
        D["rematch_state"] = "waiting"
        self._duel_send({"op": "rematch"})
        ui = D.get("ui")
        if ui:
            ui["rematch"].config(state="disabled", text="Waiting...")
            ui["info"].config(text="Waiting for your opponent to accept.")

    def _duel_rematch_msg(self, d, uid, name):
        D = self.duel
        if uid != D["uids"][1 - D["me"]]:
            return
        op = d.get("op")
        if op == "rematch" and D.get("rematch_state") in (
                None, "ready", "declined"):
            D["rematch_state"] = "incoming"
            from tkinter import messagebox
            try:
                accept = messagebox.askyesno(
                    "Rematch", f"{name} wants a rematch.",
                    parent=D.get("win") or self.root)
            except Exception:
                D["rematch_state"] = "ready"
                log("duel rematch prompt failed: " + traceback.format_exc())
                self._duel_send({"op": "rematch_decline"})
                return
            if not accept:
                D["rematch_state"] = "ready"
                self._duel_send({"op": "rematch_decline"})
                return
            if D["mine"]:
                self._duel_begin_rematch()
            else:
                D["rematch_state"] = "accepting"
                self._duel_send({"op": "rematch_accept"})
                ui = D.get("ui")
                if ui:
                    ui["rematch"].config(state="disabled",
                                         text="Starting...")
                    ui["info"].config(
                        text="Accepted. Waiting for the rematch to start.")
        elif op == "rematch_accept" and D["mine"] \
                and D.get("rematch_state") == "waiting":
            self._duel_begin_rematch()
        elif op == "rematch_decline" \
                and D.get("rematch_state") == "waiting":
            D["rematch_state"] = "declined"
            ui = D.get("ui")
            if ui:
                ui["rematch"].config(state="normal", text="Rematch")
                ui["info"].config(text="Your opponent declined the rematch.")
        elif op == "rematch_start" and not D["mine"] \
                and D.get("rematch_state") in ("waiting", "accepting"):
            new_gid = d.get("ngid")
            if (d.get("p2") == self.net.uid
                    and isinstance(new_gid, str)
                    and re.fullmatch(r"[0-9a-f]{12}", new_gid)):
                self._duel_restart(new_gid)

    def _duel_begin_rematch(self):
        D = self.duel
        new_gid = uuid.uuid4().hex[:12]
        self._duel_send({"op": "rematch_start", "p2": D["uids"][1],
                         "ngid": new_gid})
        self._duel_restart(new_gid)

    def _duel_restart(self, gid):
        D = self.duel
        uids, names = D["uids"][:], D["names"][:]
        host_uid, host, mine = D["host_uid"], D["host"], D["mine"]
        solo = D.get("solo")
        self._duel_close_window()
        D.update(self._duel_blank(gid, host_uid, host, mine))
        if solo:
            D["solo"] = True
        self._duel_start(uids, names)

    # ---- window
    DUEL_SCALE = 4                                   # screen px per art px

    def _duel_window(self):
        D, tk = self.duel, self.tk
        win = tk.Toplevel(self.root)
        win.title(f"Duel: {D['names'][0]} vs {D['names'][1]}")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        self.busy = True
        sc = self.DUEL_SCALE
        w = DUEL_LW * sc
        cv = tk.Canvas(win, width=w, height=DUEL_LH * sc, bg="black",
                       highlightthickness=0)
        cv.pack(padx=10, pady=(10, 4))
        status = tk.Label(win, text="", bg=BG, fg=FG, font=F(1, True))
        status.pack()
        info = tk.Label(win, text="", bg=BG, fg=MUTED, font=F(),
                        wraplength=w, justify="center", height=3)
        info.pack(padx=10)
        rematch = tk.Button(win, text="Rematch", command=self._duel_rematch,
                            state="disabled")
        rematch.pack(pady=(0, 4))
        row = tk.Frame(win, bg=BG)
        row.pack(pady=(8, 2))
        btns = {}
        for n, m in enumerate(DUEL_ORDER, 1):
            b = tk.Button(row, text=f"{n} {m}", width=8,
                          command=lambda m=m: self._duel_pick(m))
            b.pack(side="left", padx=2)
            b.bind("<Enter>", lambda e, m=m: self._duel_hint(m))
            b.bind("<Leave>", lambda e: self._duel_hint(None))
            btns[m] = b
            win.bind(str(n), lambda e, m=m: self._duel_pick(m))
        move_row = tk.Frame(win, bg=BG)
        move_row.pack(pady=(2, 8))
        tk.Label(move_row, text="Direction (facing):", bg=BG, fg=MUTED,
                 font=F(-1)).pack(side="left", padx=(0, 3))
        direction_buttons = {}
        for label, direction in (("Forward", "forward"), ("Back", "back")):
            button = tk.Button(
                move_row, text=label, width=8,
                command=lambda direction=direction:
                self._duel_direction(direction))
            button.pack(side="left", padx=2)
            direction_buttons[direction] = button
            btns["direction_" + direction] = button
            win.bind("<Right>" if direction == "forward" else "<Left>",
                     lambda e, direction=direction:
                     self._duel_direction(direction))
        movement_buttons = {}
        for label, action, key in (("Advance", "advance", "6"),
                                   ("Dash", "dash", "7")):
            button = tk.Button(
                move_row, text=label, width=8,
                command=lambda action=action: self._duel_move(action))
            button.pack(side="left", padx=2)
            button.bind("<Enter>", lambda e, action=action:
                        self._duel_hint_move(action))
            button.bind("<Leave>", lambda e: self._duel_hint(None))
            btns["move_" + action] = button
            movement_buttons[action] = button
            win.bind(key, lambda e, action=action:
                     self._duel_move(action))
        # fixed room for the hint, so a long one can't stretch the window
        helpl = tk.Label(win, text="", bg=BG, fg=MUTED, font=F(-1),
                         wraplength=w, justify="center", height=3)
        helpl.pack(pady=(0, 10))
        win.protocol("WM_DELETE_WINDOW", self._duel_close_window)
        D["win"] = win
        D["ui"] = {"cv": cv, "status": status, "info": info,
                   "btns": btns, "direction_buttons": direction_buttons,
                   "movement_buttons": movement_buttons, "help": helpl,
                   "rematch": rematch}
        D["fx"] = DuelFx(int(D["gid"], 16) & 0xFFFF)
        D["phase"], D["stage"], D["bg_off"] = 0, None, (0, 0)
        D["frame"], D["goal"] = duel_frame(D["S"]), None
        self._center(win)
        try:                                 # and the window never resizes
            win.update_idletasks()
            win.geometry(f"{win.winfo_reqwidth()}x{win.winfo_reqheight()}")
        except Exception:
            pass
        self._duel_draw(D["frame"])
        self.root.after(130, self._duel_idle)

    def _duel_idle(self):
        """Keep the fighters breathing (and the blood settling) between turns."""
        D = self.duel
        if not D or not D.get("ui"):
            return                                   # window closed: stop
        try:
            if not D["anim"]:
                D["phase"] += 1
                D["fx"].step()
                self._duel_draw(D["frame"])
        except Exception:
            log("duel idle failed: " + traceback.format_exc())
        self.root.after(130, self._duel_idle)

    def _duel_hint(self, m):
        D = self.duel
        ui = D.get("ui") if D else None
        if not ui:
            return
        ui["help"].config(text=f"{m}: {DUEL_MOVES[m]['help']}" if m else "")
        D["hl"] = None
        if m and D.get("S"):
            i = D["me"]
            if D.get("solo"):                # the fighter who picks next
                todo = [j for j in duel_need(D["S"])
                        if (D["r"], j) not in D["picks"]]
                i = todo[0] if todo else i
            p = D["S"]["p"][i]
            D["hl"] = duel_move_tiles(m, p["x"], p["f"])
        if D.get("frame") and not D.get("anim"):
            self._duel_draw(D["frame"])

    def _duel_picker(self):
        D = self.duel
        if not D or D["state"] != "playing" or D["over"] or D["anim"]:
            return None
        if D.get("solo"):
            todo = [i for i in duel_need(D["S"])
                    if (D["r"], i) not in D["picks"]]
            return todo[0] if todo else None
        if D["pick"] is None and D["me"] in duel_need(D["S"]):
            return D["me"]
        return None

    def _duel_direction(self, direction):
        D = self.duel
        if direction not in ("forward", "back") or self._duel_picker() is None:
            return
        self._duel_set_move_direction(direction)
        self._duel_buttons(True)

    def _duel_set_move_direction(self, direction):
        D = self.duel
        D["move_dir"] = direction
        ui = D.get("ui")
        if ui and ui.get("movement_buttons"):
            ui["movement_buttons"]["advance"].config(
                text="Retreat" if direction == "back" else "Advance")

    def _duel_move(self, action):
        D = self.duel
        if not D or self._duel_picker() is None or D.get("move_dir") is None:
            return
        self._duel_pick(duel_movement_action(D["move_dir"], action))

    def _duel_hint_move(self, action):
        D = self.duel
        if not D or D.get("move_dir") is None:
            self._duel_hint(None)
            return
        self._duel_hint(duel_movement_action(D["move_dir"], action))

    def _duel_buttons(self, on):
        D = self.duel
        ui = D.get("ui") if D else None
        if not ui:
            return
        for name, b in ui["btns"].items():
            enabled = on and (not name.startswith("move_")
                              or D.get("move_dir") is not None)
            try:
                b.config(state="normal" if enabled else "disabled")
            except Exception:
                pass
        for direction, button in ui.get("direction_buttons", {}).items():
            try:
                button.config(relief=(
                    "sunken" if D.get("move_dir") == direction else "raised"))
            except Exception:
                pass

    def _duel_close_window(self):
        D = self.duel
        if not D:
            return
        if D.get("spectator") and not D["over"]:
            D["over"] = True
        if D.get("solo"):
            D["over"] = True                 # no forfeit question when alone
        if D["state"] == "playing" and not D["over"]:
            self._duel_forfeit()
            return
        win = D.get("win")
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        D["win"] = D["ui"] = None
        self.busy = self.settings_win is not None
        self._touch()

    def _duel_forfeit(self):
        D = self.duel
        if D.get("solo") or D.get("spectator"):
            self._duel_close_window()
            return
        from tkinter import messagebox
        self.busy = True
        try:
            ok = messagebox.askyesno(
                "Duel", "Forfeit the duel? Your opponent wins.",
                parent=D.get("win") or self.root)
        except Exception:
            ok = False
        if ok and not D["over"]:
            D["quit"] = True
            self._duel_send({"op": "q"})     # asked for again if it's lost
            self._duel_finish(1 - D["me"], "forfeit")
        self.busy = self.settings_win is not None or bool(D.get("win"))

    def _duel_draw(self, fr):
        """Paint one frame: the backdrop only when the stage changes, the
        fighters and effects every time."""
        D = self.duel
        ui = D.get("ui") if D else None
        if not ui:
            return
        D["frame"] = fr
        cv, sc, fx = ui["cv"], self.DUEL_SCALE, D["fx"]
        stage = duel_stage_for(D["gid"], D["r"])
        if D["stage"] != stage:
            cv.delete("bg")
            for (x, y, w, h, c) in duel_bg_rects(stage):
                cv.create_rectangle(x * sc, y * sc, (x + w) * sc,
                                    (y + h) * sc, fill=c, outline="",
                                    tags="bg")
            cv.tag_lower("bg")
            D["stage"], D["bg_off"] = stage, (0, 0)
        ox, oy = fx.offset()                         # screen shake
        dx, dy = ox - D["bg_off"][0], oy - D["bg_off"][1]
        if dx or dy:
            cv.move("bg", dx * sc, dy * sc)
            D["bg_off"] = (ox, oy)
        cv.delete("fg")
        rects = duel_tile_rects(D.get("hl")) + duel_fg_rects(
            fr, fx, D["phase"], D["goal"])
        for (x, y, w, h, c) in rects:
            cv.create_rectangle((x + ox) * sc, (y + oy) * sc,
                                (x + ox + w) * sc, (y + oy + h) * sc,
                                fill=c, outline="", tags="fg")
        font = ("Courier New", 10, "bold")
        for i in (0, 1):
            p = fr["p"][i]
            x0 = 6 if i == 0 else DUEL_LW - 6
            cv.create_text((x0 + ox) * sc, (4 + oy) * sc,
                           text=f"{D['names'][i]}  {max(0, p['hp'])}/{DUEL_HP}",
                           fill=DUEL_COLS[i], font=font, tags="fg",
                           anchor="nw" if i == 0 else "ne")
        perspective = 0 if D.get("solo") or D.get("spectator") else D["me"]
        advantage = duel_turn_lead(D["S"], perspective)
        if D.get("spectator") and advantage > 0:
            lead_text, lead_color = f"{D['names'][0]} +{advantage} turns", \
                "#7be08a"
        elif D.get("spectator") and advantage < 0:
            lead_text, lead_color = f"{D['names'][1]} +{-advantage} turns", \
                "#7be08a"
        elif advantage > 0:
            lead_text = f"+{advantage} turns"
            lead_color = "#7be08a"
        elif advantage < 0:
            lead_text = f"{advantage} turns"
            lead_color = "#ff7a7a"
        else:
            lead_text, lead_color = "0 turns", MUTED
        if D.get("solo") and advantage:
            lead_text = f"{D['names'][perspective]} {lead_text}"
        cv.create_text((DUEL_LW // 2 + ox) * sc, (4 + oy) * sc,
                       text=lead_text, fill=lead_color, font=font,
                       tags="fg", anchor="n")
        for i in (0, 1):
            p = fr["p"][i]
            label = ("K.O." if p["ko"] else p["move"]
                     or ("stunned" if p["stun"] else "ready")).upper()
            cx = DUEL_MX + p["x"] * DUEL_U
            cv.create_text((cx + ox) * sc, (DUEL_GY + 9 + oy) * sc,
                           text=label, fill=DUEL_COLS[i],
                           font=("Courier New", 9, "bold"), tags="fg")

    # ---- playing
    def _duel_begin_round(self):
        D = self.duel
        S = D["S"]
        D["r"] = S["round"] + 1
        D["pick"], D["anim"], D["out"] = None, False, None
        self._duel_set_move_direction(None)
        D["hl"] = None
        D["resends"], D["next_resend"] = 0, time.time() + self.DUEL_RESEND[0]
        for key in [k for k in D["picks"] if k[0] < D["r"]]:
            D["picks"].pop(key, None)
        need = duel_need(S)
        ui = D.get("ui")
        me = D["me"]
        if D.get("spectator"):
            self._duel_buttons(False)
            if ui:
                ui["status"].config(
                    text=f"Spectating — Turn {D['r']}", fg=MUTED)
                ui["info"].config(text=D["last"])
            self._duel_progress()
            return
        if ui and D.get("solo"):
            n = D["r"]
            self._duel_buttons(bool(need))
            if len(need) == 2:
                text = (f"Turn {n}: pick for {D['names'][0]}, "
                        f"then for {D['names'][1]}")
            elif need:
                text = f"Turn {n}: pick for {D['names'][need[0]]} only"
            else:
                text = f"Turn {n}: ..."
            ui["status"].config(text=text,
                                fg=DUEL_COLS[need[0]] if need else MUTED)
            ui["info"].config(text=D["last"])
        elif ui:
            mine = me in need
            self._duel_buttons(mine)
            P, other = S["p"], D["names"][1 - me]
            n = D["r"]
            if mine and len(need) == 2:
                text, col = (f"Turn {n}: pick your move "
                             f"(1-{len(DUEL_ORDER)})", FG)
            elif mine:
                if P[1 - me]["move"] == "heavy":
                    text = (f"Turn {n}: {other} is winding up a heavy attack, "
                            "and it lands this turn. Your move!")
                elif P[1 - me]["move"] in ("dash", "dash_back"):
                    text = f"Turn {n}: {other} is finishing a dash. Your move!"
                else:
                    text = f"Turn {n}: {other} lost this turn. Your move!"
                text, col = text, "#7be08a"
            elif P[me]["move"] == "heavy":
                text, col = (f"Turn {n}: your heavy attack strikes now. "
                             f"{other} is choosing...", MUTED)
            elif P[me]["move"] in ("dash", "dash_back"):
                text, col = (f"Turn {n}: your dash finishes now. "
                             f"{other} is choosing...", MUTED)
            elif need:
                text, col = (f"Turn {n}: you lost this turn. {other} is "
                             "choosing...", MUTED)
            else:
                text, col = f"Turn {n}: ...", MUTED
            ui["status"].config(text=text, fg=col)
            ui["info"].config(text=D["last"])
        self._duel_progress()

    def _duel_pick(self, move):
        D = self.duel
        if (not D or D["state"] != "playing" or D["over"] or D["anim"]
                or D.get("spectator") or D["pick"] is not None
                or move not in DUEL_MOVES):
            return
        S, me, r = D["S"], D["me"], D["r"]
        if D.get("solo"):                    # fill in whoever still needs one
            todo = [i for i in duel_need(S) if (r, i) not in D["picks"]]
            if not todo:
                return
            D["picks"][(r, todo[0])] = move
            self._duel_set_move_direction(None)
            remaining = [i for i in todo[1:]
                         if (r, i) not in D["picks"]]
            if remaining and D.get("ui"):
                D["ui"]["status"].config(
                    text=f"Turn {r}: now pick for {D['names'][remaining[0]]}",
                    fg=DUEL_COLS[remaining[0]])
            self._duel_buttons(bool(remaining))
            self._duel_progress()
            return
        if me not in duel_need(S):
            return                           # no choice this turn
        D["pick"] = move
        D["hist"][r] = move
        D["picks"][(r, me)] = move
        out = {"op": "p", "r": r, "m": move}
        if D["mine"] and r == 1 and D["go"]:
            out.update(D["go"])              # this pick also starts the duel
        D["out"] = out
        self._duel_send(out)
        self._duel_buttons(False)
        ui = D.get("ui")
        if ui:
            ui["status"].config(text=f"Locked in: {move}. Waiting for "
                                f"{D['names'][1 - me]}...", fg=MUTED)
        self._duel_progress()

    def _duel_progress(self):
        """Play the turn as soon as every pick it needs is known (a turn
        nobody picks for, like a heavy's strike, plays by itself)."""
        D = self.duel
        if not D or D["state"] != "playing" or D["over"] or D["anim"]:
            return
        S = D["S"]
        r, need = D["r"], duel_need(S)
        choices = {}
        for i in need:
            m = D["picks"].get((r, i))
            if m is None:
                return
            choices[i] = m
        D["anim"] = True
        D["hl"] = None
        labels = []
        for i in (0, 1):
            if i in choices:
                labels.append(choices[i] + (" (wind-up)"
                                            if choices[i] == "heavy" else ""))
            elif S["p"][i]["stun"] > 0:
                labels.append("lost turn")
            elif S["p"][i]["move"] in ("dash", "dash_back"):
                labels.append("dash follow-through")
            else:
                labels.append("heavy strike")
        frames, ev = duel_round(S, choices)
        D["last"] = self._duel_describe(labels, ev)
        self._duel_buttons(False)
        self._duel_animate(frames, 0)

    def _duel_describe(self, labels, ev):
        D = self.duel
        n = D["names"]
        parts = [f"{n[i]}: {labels[i]}" for i in (0, 1)]
        out = []
        for e in ev:
            bits = e.split(":")
            if bits[0] == "hit":
                out.append(f"{n[int(bits[1])]} got hit by {bits[2]}")
            elif bits[0] == "blocked":
                d = int(bits[1])
                out.append(f"{n[d]} blocked it, so {n[1 - d]} loses the "
                           "next turn")
            elif bits[0] == "grab":
                out.append(f"{n[int(bits[1])]} was grabbed and loses "
                           "2 turns")
            elif bits[0] == "grab_fail":
                penalty = bits[2]
                out.append(f"{n[int(bits[1])]} missed the grab and loses "
                           f"{penalty} turns")
            elif bits[0] == "whiff":
                out.append(f"{n[int(bits[1])]} blocked nothing and loses "
                           "the next turn")
            elif bits[0] == "tech":
                out.append("both grabs failed")
        return "   ".join(parts) + ("  -  " + ", ".join(out) if out else
                                    "  -  nothing connected")

    def _duel_animate(self, frames, i):
        D = self.duel
        if not D or D["over"] and not D.get("ui"):
            return
        if i < len(frames) and D.get("ui"):
            fx = D["fx"]
            fx.on_frame(frames[i])
            D["phase"] += 1
            self._duel_draw(frames[i])
            fx.step()
            delay = 45
            if fx.hold:                              # hit-stop: freeze a beat
                fx.hold -= 1
                delay = 120
            self.root.after(delay, lambda: self._duel_animate(frames, i + 1))
            return
        S = D["S"]
        if S["over"]:
            self._duel_finish(S["winner"], "ko" if S["winner"] != -1 or
                              S["p"][0]["hp"] == 0 else "time")
        else:
            self._duel_begin_round()

    def _duel_finish(self, winner, why):
        D = self.duel
        if not D or D["over"]:
            return
        D["over"] = True
        D["anim"] = False                    # let the idle loop paint the end
        D["rematch_state"] = "ready"
        D["over_at"] = time.time()           # keep resending a little longer
        if winner in (0, 1):
            D["goal"] = (winner, 1 - winner)  # the flashing GO arrow
        n = D["names"]
        if winner == -1:
            text = "Draw!"
        elif D.get("solo") or D.get("spectator"):
            text = f"{n[winner]} wins!"
        elif winner == D["me"]:
            text = "You win!" + (" (they forfeited)" if why == "forfeit" else "")
        else:
            text = "You lose." + (" (you forfeited)" if why == "forfeit" else "")
        ui = D.get("ui")
        if ui:
            ui["status"].config(
                text=text, fg=(DUEL_COLS[winner]
                               if (D.get("solo") or D.get("spectator"))
                               and winner != -1
                               else "#7be08a" if winner == D["me"]
                               else "#ff7a7a" if winner != -1 else FG))
            suffix = ("\nClose this window to stop spectating."
                      if D.get("spectator") else
                      "\nRematch or close this window when done.")
            ui["info"].config(text=D["last"] + suffix)
            ui["rematch"].config(
                state="disabled" if D.get("spectator") else "normal",
                text=("Spectating" if D.get("spectator") else
                      "Rematch" if not D.get("solo") else "Play again"))
            self._duel_buttons(False)
        if D["mine"] and not D.get("solo"):          # the host tells the room
            hp = [p["hp"] for p in D["S"]["p"]] if D["S"] else [0, 0]
            if winner == -1:
                msg = f"Duel: {n[0]} and {n[1]} drew."
            else:
                msg = (f"Duel: {n[winner]} beat {n[1 - winner]}"
                       f" ({hp[winner]} HP left"
                       f"{', by forfeit' if why == 'forfeit' else ''}).")
            self.add(self.net.send(msg, extra={"color": name_color(
                self.net.name)}))
            self.redraw()

    def _duel_peer_left(self, uid):
        D = self.duel
        if (D and not D["over"] and uid in D["uids"]
                and uid != self.net.uid):
            self._duel_finish(1 - D["uids"].index(uid), "forfeit")
        elif D and not D["over"] and uid == D["host_uid"] \
                and D["state"] in ("invited", "accepting"):
            self._duel_over(f"{D['host']} left, so the duel was cancelled")

    def _duel_tick(self, now):
        D = self.duel
        if not D or D["over"]:
            return
        if now - D["t0"] > self.DUEL_SECONDS:
            if D["state"] == "playing":
                self._duel_finish(-1, "time")
            else:
                self._duel_over("the duel timed out")
            return
        if D["state"] == "accepting":
            # say "accept" again twice at most, then drop it
            if now - D["accept_at"] > self.DUEL_ACCEPT_RESEND[
                    min(D["accept_n"] - 1, 1)] and D["accept_n"] <= 2:
                D["accept_n"] += 1
                D["accept_at"] = now
                self._duel_send({"op": "accept"})
            elif D["accept_n"] > 2 and now - D["accept_at"] > 20:
                self._duel_over(f"{D['host']} didn't answer, so the duel "
                                "was dropped")
        elif D["state"] == "playing" and not D["anim"] \
                and not D.get("solo") and now > D["next_resend"]:
            # Stuck waiting. Only speak once our own pick is in (or we
            # had none to make): if they are waiting on US, nothing was lost.
            me = D["me"]
            if (me not in duel_need(D["S"]) or D["pick"] is not None) \
                    and D["resends"] < 12:
                D["resends"] += 1
                D["next_resend"] = now + self.DUEL_RESEND[
                    min(D["resends"], len(self.DUEL_RESEND) - 1)]
                if D["out"]:
                    self._duel_send(dict(D["out"], re=1))
                else:
                    self._duel_send({"op": "n", "r": D["r"], "re": 1})
            else:
                D["next_resend"] = now + 30

    def _font_set(self):
        """Fonts installed on this computer (lower case)."""
        try:
            from tkinter import font as tkfont
            return {f.lower() for f in tkfont.families(self.root)}
        except Exception:
            return set()

    def _usable_font(self, family, who):
        """The font to draw someone's message in. If it isn't installed on
        this computer, use our normal font, and check (in the background)
        whether it's a free font we can offer to download."""
        if self._installed is None:
            self._installed = self._font_set()
        if not self._installed or family.lower() in self._installed:
            return family
        key = family.lower()
        if key not in self.font_warned:
            self.font_warned.add(key)
            threading.Thread(target=self._font_check_worker,
                             args=(who, family), daemon=True).start()
        return ""

    def _font_check_worker(self, who, family):
        try:
            res = google_font_files(family)
            state = "offer" if res else "nodl"
        except Exception:
            res, state = None, "error"
        self.inbox.put({"type": "font_result", "who": who, "family": family,
                        "state": state, "res": res})

    def _on_font_result(self, msg):
        who, family = msg["who"], msg["family"]
        if msg["state"] == "offer":
            self.font_offers[family.lower()] = {
                "family": family, "name": msg["res"]["name"],
                "urls": msg["res"]["urls"]}
            self._fonts_label()
            text = (f'{who} uses the font "{family}". It\'s a free font: '
                    'click "get fonts" in the top bar (or type /getfonts) '
                    "to install it.")
        elif msg["state"] == "nodl":
            text = (f'{who} uses the font "{family}", which isn\'t installed '
                    "here and isn't a free font that can be downloaded, so "
                    "you see the normal font.")
        else:
            text = (f'{who} uses the font "{family}", which isn\'t installed '
                    "on this computer, so you see the normal font.")
        self._deliver({"type": "sys", "name": "", "text": text})

    def fonts_cmd(self):
        """Click on "get fonts" or /getfonts: ask, then download."""
        if not (self.font_offers or self.font_share_offers):
            self.note("no fonts to download right now")
            return
        from tkinter import messagebox
        offers = list(self.font_offers.values())
        shared = list(self.font_share_offers.values())[:8]
        parts = []
        if offers:
            parts.append("Free fonts from Google Fonts:\n" + "\n".join(
                "  " + o["family"] for o in offers[:12]))
        if shared:
            parts.append("Fonts your friends shared (only accept fonts from "
                         "people you trust):\n" + "\n".join(
                             f"  {o['n']} ({max(1, o['s'] // 1024)} KB) from "
                             f"{o['who']}" for o in shared))
        self.busy = True
        try:
            ok = messagebox.askyesno(
                "Study chat",
                "Install these fonts?\n\n" + "\n\n".join(parts) +
                "\n\nThey are installed for your user only, and you "
                "can remove them any time from your computer's font list.",
                parent=self.root)
        finally:
            self.busy = False
        if not ok:
            return
        self.font_offers = {}
        if shared:
            self._request_fonts(shared)
        self._fonts_label()
        if offers:
            self.note("downloading fonts...")
            threading.Thread(target=self._font_install_worker,
                             args=(offers,), daemon=True).start()

    def _font_install_worker(self, offers):
        done, failed = [], []
        for o in offers:
            try:
                stem = re.sub(r"[^A-Za-z0-9]+", "", o["name"]) or "font"
                for i, url in enumerate(o["urls"]):
                    ext = ".otf" if url.split("?")[0].lower().endswith(
                        ".otf") else ".ttf"
                    data = download_font(url)
                    install_font_file(data, f"{stem}-{i + 1}{ext}")
                    try:             # keep a copy in the shared fonts folder
                        save_to_font_folder(self._fonts_dir(), data,
                                            f"{stem}-{i + 1}{ext}")
                    except OSError:
                        log("couldn't copy a font to the shared folder")
                done.append(o["family"])
            except Exception:
                log("font install failed: " + traceback.format_exc())
                failed.append(o["family"])
        self.inbox.put({"type": "fonts_done", "ok": done, "failed": failed})

    def _on_fonts_done(self, msg):
        ok, failed = msg["ok"], msg["failed"]
        if failed:
            self.note("couldn't install: " + ", ".join(failed))
        if not ok:
            return
        self._installed = self._font_set()
        shown = [f for f in ok if f.lower() in self._installed]
        for m in self.history:               # redraw earlier messages
            want = m.get("font_want")
            if want and want.lower() in self._installed:
                m["font"] = want
                m.pop("font_want", None)
        for f in ok:                         # allow another try if it failed
            self.font_warned.discard(f.lower())
        self.font_tags.clear()
        self.apply_settings()
        if len(shown) == len(ok):
            self.note("installed: " + ", ".join(ok))
            return
        from tkinter import messagebox
        self.busy = True
        try:
            again = messagebox.askyesno(
                "Study chat",
                "Installed: " + ", ".join(ok) + "\n\nThis computer needs "
                "the chat restarted before it can use them. Restart now?",
                parent=self.root)
        finally:
            self.busy = False
        if not again:
            self.note("installed: " + ", ".join(ok) + " (restart the chat "
                      "to see them)")
            return
        self._restart_app()

    def _restart_app(self):
        args = [sys.executable, os.path.abspath(__file__),
                "--name", self.net.name, "--room", self.net.room,
                "--online" if self.net.mode == "online" else "--lan"]
        try:
            subprocess.Popen(args)
            self.root.destroy()
        except Exception:
            self.note("couldn't restart by itself; please close and reopen")

    def _handle_incoming(self, msg):
        if msg.get("type") == "summon":
            self.set_state("active")
            self.reset_window_position()
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
        if (msg.get("type") == "img" and msg.get("popup") == "skeleton"
                and isinstance(msg.get("data"), bytes)):
            now = time.time()
            if (ALLOW_SKELETON and msg["data"].startswith(b"GIF8")
                    and now - getattr(self, "_skel_shown", 0) > 10):
                self._skel_shown = now
                self.open_skeleton(msg["data"],
                                   str(msg.get("name", "?"))[:20])
            return                           # not added to the chat
        if msg.get("type") == "gif_ready":
            self.send_gif(msg["data"])
            return
        if msg.get("type") == "font_result":
            self._on_font_result(msg)
            return
        if msg.get("type") == "fonts_done":
            self._on_fonts_done(msg)
            return
        if msg.get("type") == "font_fail":
            self._on_font_fail(msg)
            return
        if msg.get("type") == "update_done":
            self._on_update_done(str(msg.get("version", "")))
            return
        msg["name"] = str(msg.get("name", "?"))[:20]
        msg["text"] = str(msg.get("text", ""))[:2000]
        col = str(msg.get("color") or "").lower()
        msg["color"] = col if re.fullmatch(r"#[0-9a-f]{6}", col) else ""
        msg["font"] = "".join(c for c in str(msg.get("font", ""))
                              if c.isprintable())[:60].strip()
        if msg["font"] and msg.get("uid") != self.net.uid:
            want = msg["font"]
            msg["font"] = self._usable_font(want, msg["name"])
            if not msg["font"]:
                msg["font_want"] = want      # so it can be shown once installed
        self.presence.seen(msg, time.time())
        mine = msg.get("uid") == self.net.uid
        if not mine and msg.get("type") == "leave":
            self._game_peer_left(msg.get("uid"))
            self._duel_peer_left(msg.get("uid"))
        if not mine and msg.get("type") == "join" and FONT_SYNC \
                and self.font_mine:
            # a newcomer doesn't know our fonts yet: tell them again soon
            self.font_announced = frozenset()
            self.font_due = min(self.font_due,
                                time.time() + random.uniform(1, 8))
        if not mine and msg.get("type") == "ping":
            # Game moves and shared fonts travel as quiet "pings", so older
            # versions of the app just ignore them.
            if isinstance(msg.get("game"), dict):
                self._game_msg(msg)
                return
            if isinstance(msg.get("duel"), dict):
                self._duel_msg(msg)
                return
            if isinstance(msg.get("fontlist"), list):
                self._fontlist_msg(msg)
                return
            if isinstance(msg.get("fontreq"), dict):
                self._fontreq_msg(msg)
                return
            if msg.get("blob") == "font":
                self._fontblob_msg(msg)
                return
        greet = JOIN_GREETINGS.get(msg["name"].strip().lower())
        if (greet and msg.get("type") == "join"
                and msg.get("uid") != self.net.uid):
            def say(text=greet):
                # Comes from "Admin", who isn't a real person in the room.
                # The empty uid keeps Admin out of the online list.
                self.add(self.net.send(
                    text, extra={"name": GREETING_SENDER, "uid": "",
                                 "color": name_color(GREETING_SENDER)}))
                self.redraw()
            self.root.after(1200, say)       # a moment after they appear
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
        if (msg.get("type") == "ping" and isinstance(msg.get("items"), list)
                and msg.get("uid") != self.net.uid):
            self.hist_seq += 1               # someone answered, so we needn't
            self._take_history(msg)
            return
        if (msg.get("type") == "ping" and msg.get("flip")
                and msg.get("uid") != self.net.uid):
            self._flip(msg["name"])
            return
        if (msg.get("hist_req") and msg.get("uid") != self.net.uid
                and msg.get("type") in ("join", "ping")):
            self._schedule_history()         # newcomer wants earlier messages
        if msg.get("type") == "ping":          # quiet "still here" signal
            return
        self._deliver(msg)

    def _deliver(self, msg):
        self.seq += 1
        msg["_n"] = self.seq                 # order it arrived in
        self.add(msg)
        if self.state == "active":
            self.seen_upto = self.seq
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
            # first-join roll call: our "joined" already asks everyone to
            # answer, so only ask again if nobody has (and, online, only once
            # the join has really reached the relay)
            online = self.net.mode == "online"
            if (self.ready_at is None and getattr(self.net, "connected", True)
                    and getattr(self.net, "join_ok", True)):
                self.ready_at = now
            if self.ready_at is not None and not self.roll_done:
                waited = now - self.ready_at
                others = len(self.presence.peers)
                ask_at = (6.0,) if online else (0.3, 3.0, 8.0)
                if (others == 0 and self.roll_sent < len(ask_at)
                        and waited >= ask_at[self.roll_sent]):
                    self.roll_sent += 1
                    self.net.send("who", kind="ping",
                                  extra={"hist_req": 1})
                if others and self.first_peer_at is None:
                    self.first_peer_at = now
                if online:
                    # a trip to the relay and back, plus the random delay
                    # before people answer, takes several seconds. Show the
                    # list shortly after the first answer, or give up at 12s.
                    done = (waited > 12 or (self.first_peer_at is not None
                                            and now - self.first_peer_at > 2))
                else:
                    done = waited > 3.5
                if done:
                    self.roll_done = True
                    self.update_online()
                    self.show_who_popup()
            # stop saying "checking..." eventually, whatever happens
            if not self.roll_done and now - self.start_time > (
                    120 if online else 15):
                self.roll_done = True
                self.update_online()
            for job in (self._fonts_tick, self._game_tick, self._duel_tick):
                try:
                    job(now)
                except Exception:
                    log("background job failed: " + traceback.format_exc())
            # tell others we're still here, and notice when someone stops
            if online:
                due = relay_keepalive_due(
                    now, self.last_ping,
                    getattr(self.net, "last_published_at", self.last_ping),
                    self.net.ping_every)
            else:
                due = now - self.last_ping > self.net.ping_every
            if due:
                self.last_ping = now
                self.net.send("", kind="ping")
            for pname in self.presence.expired(now, 3 * self.net.ping_every):
                self._deliver({"type": "leave", "name": pname, "text": ""})
            if self.state == "popup" and now > self.popup_until:
                self.set_state("collapsed")
            elif (self.state == "active" and not self.busy and not self._dragging
                  and not self._menu_open() and not self.entry.get()
                  and now - self.last_activity > ACTIVE_IDLE_SECONDS):
                self.set_state("collapsed")
            # keep sitting above other windows (every couple of seconds),
            # but never above the chat's own menu or windows
            self.tick_n += 1
            if self.tick_n % 4 == 0:
                self._stay_on_top()
                self._check_displays()
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
    net.send("joined", kind="join", extra={"hist_req": 1})
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
