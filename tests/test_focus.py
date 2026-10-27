"""UI regressions: run with a Tk-enabled Python in a desktop session.

    python3 -m unittest discover -s tests -v

The windows are local test fixtures; no network or settings files are used.
"""

import queue
import time
import unittest
from unittest.mock import Mock

try:
    import tkinter as tk
except ImportError:
    tk = None

import studychat


@unittest.skipIf(tk is None, "requires a Python installation with Tkinter")
class FocusTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Study chat focus test")
        net = Mock(room="test", name="Tester", mode="offline",
                   ping_every=10**12)
        self.overlay = studychat.Overlay(self.root, net, queue.Queue())
        self.root.deiconify()
        self.pump()

    def tearDown(self):
        for job in self.root.tk.call("after", "info"):
            self.root.after_cancel(job)
        self.root.destroy()

    def pump(self):
        # Run the real event loop, including native focus and idle callbacks.
        done = tk.BooleanVar(master=self.root, value=False)
        self.root.after(80, done.set, True)
        self.root.wait_variable(done)

    def click(self, widget, x=10, y=10):
        widget.event_generate("<Motion>", x=x, y=y)
        widget.event_generate("<ButtonPress-1>", x=x, y=y)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y)
        self.pump()

    def assert_can_type(self):
        self.assertEqual(self.root.focus_get(), self.overlay.entry)
        self.overlay.entry.event_generate("<KeyPress>", keysym="a")
        self.assertEqual(self.overlay.entry.get(), "a")
        self.overlay.entry.delete(0, "end")

    def other_input(self):
        window = tk.Toplevel(self.root)
        window.title("Other focus test window")
        entry = tk.Entry(window)
        entry.pack()
        self.pump()
        entry.focus_force()
        self.pump()
        self.assertEqual(self.root.focus_get(), entry)
        return entry

    def test_history_click_keeps_typing_in_entry(self):
        self.overlay.set_state("active")
        self.pump()
        self.click(self.overlay.text)
        self.assert_can_type()
        self.assertEqual(self.overlay.text.cget("state"), "disabled")

    def test_popup_click_opens_working_input(self):
        self.overlay._deliver({"type": "text", "name": "Friend",
                               "text": "Hello"})
        self.pump()
        self.click(self.overlay.text)
        self.assertEqual(self.overlay.state, "active")
        self.assert_can_type()

    def test_repeated_reopen_and_return_from_other_window(self):
        other = self.other_input()
        for _ in range(3):
            self.overlay.set_state("collapsed")
            self.pump()
            self.click(self.overlay.pill)
            self.assert_can_type()
            other.focus_force()
            self.pump()
            self.click(self.overlay.entry)
            self.assert_can_type()

    def test_settings_keep_focus_then_return_it_on_close(self):
        # Opening Settings immediately must not race pending chat focus.
        self.overlay.set_state("active")
        self.overlay.open_settings()
        self.pump()
        settings = self.overlay.settings_win
        self.assertIsNotNone(settings)
        self.assertEqual(self.root.focus_get().winfo_toplevel(), settings.win)
        self.overlay.last_activity = time.time() - 1000
        settings.cancel()
        self.pump()
        self.overlay.tick()
        self.assertEqual(self.overlay.state, "active")
        self.assert_can_type()

    def test_incoming_message_does_not_take_focus(self):
        self.overlay.set_state("active")
        self.pump()
        other = self.other_input()
        for state in ("active", "collapsed"):
            if state == "collapsed":
                self.overlay.set_state(state)
            self.overlay._deliver({"type": "text", "name": "Friend",
                                   "text": "Hello"})
            self.pump()
            self.assertEqual(self.root.focus_get(), other)

    def test_collapse_cancels_pending_focus(self):
        other = self.other_input()
        self.overlay.set_state("active")
        self.overlay.set_state("collapsed")
        self.pump()
        self.assertEqual(self.root.focus_get(), other)

    def test_image_viewer_keeps_focus_then_returns_it(self):
        self.overlay.set_state("active")
        photo = tk.PhotoImage(master=self.root, width=30, height=30)
        self.overlay.make_photo = Mock(return_value=photo)
        self.overlay.add({"type": "img", "id": "test", "name": "Friend",
                          "data": b"test image"})
        self.overlay.redraw()
        self.pump()
        start = self.overlay.text.tag_ranges("img_test")[0]
        x, y, _, _ = self.overlay.text.bbox(start)
        self.click(self.overlay.text, x + 2, y + 2)
        viewer = self.root.focus_get().winfo_toplevel()
        self.assertNotEqual(viewer, self.root)
        self.assertEqual(viewer.title(), "Image")
        viewer.event_generate("<Escape>")
        self.pump()
        self.assert_can_type()


if __name__ == "__main__":
    unittest.main()
