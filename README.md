# Study Chat

Run `python3 studychat.py` on each computer and choose the same room and
connection mode. Use `--online` if the computers cannot reach each other on
the local network.

On Fedora, install Tkinter with `sudo dnf install python3-tkinter` if needed.
Linux uses a normal window with a native title bar so keyboard input works
with X11 and XWayland. Closing it returns to the small Chat button.

Run the local UI regression tests in a desktop session:

```sh
python3 -m unittest discover -s tests -v
```

The X11 native keyboard test also needs `xdotool`. Use an isolated test display
such as Xvfb when running it, since it sends keys to the display's actual focus.

