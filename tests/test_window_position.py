"""Headless positioning regressions; run with python -B -m unittest discover -s tests."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import studychat as chat


PRIMARY = chat.Monitor("primary", (0, 0, 1920, 1080),
                       (0, 0, 1920, 1040), True)
RIGHT = chat.Monitor("right", (1920, 0, 3200, 1024),
                     (1920, 0, 3200, 984))
LEFT = chat.Monitor("left", (-1280, 0, 0, 1024),
                    (-1280, 0, 0, 984))
ABOVE = chat.Monitor("above", (0, -900, 1600, 0),
                     (0, -900, 1600, -40))
MONITORS = [PRIMARY, RIGHT, LEFT, ABOVE]


class GeometryTests(unittest.TestCase):
    def test_monitor_selection_uses_overlap_and_negative_coordinates(self):
        cases = [((1800, 300, 360, 330), RIGHT),
                 ((-500, 100, 360, 330), LEFT),
                 ((100, -500, 360, 330), ABOVE),
                 ((20, 640, 360, 330), PRIMARY)]
        for geometry, expected in cases:
            with self.subTest(geometry=geometry):
                self.assertEqual(chat.monitor_for_window(*geometry, MONITORS),
                                 expected)

    def test_offscreen_drop_selects_nearest_monitor(self):
        self.assertEqual(chat.monitor_for_window(4000, 100, 360, 330, MONITORS),
                         RIGHT)

    def test_gap_between_displays_is_not_a_usable_area(self):
        first = chat.Monitor("first", (0, 0, 1000, 800),
                             (0, 0, 1000, 760), True)
        second = chat.Monitor("second", (2000, 0, 3000, 800),
                              (2000, 0, 3000, 760))
        chosen = chat.monitor_for_window(1500, 100, 100, 200, [first, second])
        self.assertEqual(chosen, second)
        self.assertEqual(chat.fit_window(1500, 300, 100, 200, chosen.work),
                         (2000, 100, 100, 200))

    def test_fit_keeps_all_edges_inside_work_area(self):
        for work in (PRIMARY.work, LEFT.work, ABOVE.work, (48, 40, 900, 700)):
            for x, bottom in ((-9000, -9000), (9000, 9000), (400, 500)):
                with self.subTest(work=work, x=x, bottom=bottom):
                    gx, gy, w, h = chat.fit_window(x, bottom, 360, 330, work)
                    self.assertGreaterEqual(gx, work[0])
                    self.assertGreaterEqual(gy, work[1])
                    self.assertLessEqual(gx + w, work[2])
                    self.assertLessEqual(gy + h, work[3])

    def test_oversized_window_fits_without_negative_sizes(self):
        self.assertEqual(chat.fit_window(20, 130, 900, 1000, (0, 0, 300, 200)),
                         (0, 0, 300, 200))

    def test_native_query_failure_uses_tk_screen(self):
        root = Mock()
        root.winfo_screenwidth.return_value = 1366
        root.winfo_screenheight.return_value = 768
        with patch.object(chat.sys, "platform", "win32"), \
                patch.object(chat, "_windows_monitors", side_effect=OSError):
            monitors = chat.display_monitors(root)
        self.assertEqual(monitors, [chat.Monitor(
            "tk-screen", (0, 0, 1366, 768), (0, 0, 1366, 768), True)])

    def test_non_windows_does_not_call_windows_api(self):
        root = Mock()
        root.winfo_screenwidth.return_value = 1440
        root.winfo_screenheight.return_value = 900
        with patch.object(chat.sys, "platform", "darwin"), \
                patch.object(chat, "_windows_monitors") as native:
            self.assertEqual(chat.display_monitors(root)[0].work,
                             (0, 0, 1440, 900))
            native.assert_not_called()


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(chat.__dict__, chat.DEFAULTS))
        self.enterContext(patch.object(chat.sys, "platform", "win32"))
        self.displays = self.enterContext(patch.object(
            chat, "display_monitors", return_value=MONITORS))

    def overlay(self):
        # Exercise the actual placement/state methods without Tk or networking.
        ov = object.__new__(chat.Overlay)
        ov.root = Mock()
        ov.root.winfo_children.return_value = []
        ov._dragging = False
        ov._placed_geometry = None
        ov._focus_job = None
        ov.history = []
        ov.font_tags = {}
        ov.state = "collapsed"
        ov.seq = 0
        ov.busy = False
        ov.menu_until = 0
        for name in ("pill", "header", "text", "entry_wrap", "entry", "title",
                     "close_lbl", "menu_lbl", "fonts_lbl", "online_lbl", "plus", "skull"):
            setattr(ov, name, Mock())
        ov._pack_active = Mock()
        ov._focus_entry = Mock()
        ov.redraw = Mock()
        ov._reset_anchor()
        ov.set_state("collapsed")
        return ov

    def drop(self, ov, x, bottom):
        ov.set_state("active")
        ov._drag_start(SimpleNamespace(x_root=0, y_root=0))
        ov._drag_move(SimpleNamespace(x_root=x - ov.anchor_x,
                                     y_root=bottom - ov.anchor_bottom))
        ov._drag_end(None)

    def assert_inside(self, ov, work):
        x, y, w, h = ov._placed_geometry
        self.assertGreaterEqual(x, work[0])
        self.assertGreaterEqual(y, work[1])
        self.assertLessEqual(x + w, work[2])
        self.assertLessEqual(y + h, work[3])

    def test_restart_ignores_last_session_position(self):
        first = self.overlay()
        startup = first._placed_geometry
        self.drop(first, 2400, 800)
        self.assertNotEqual(first._placed_geometry, startup)
        self.assertEqual(self.overlay()._placed_geometry, startup)
        self.assertEqual(startup, (20, 932, 96, 38))

    def test_startup_respects_taskbar_on_left_and_bottom(self):
        self.displays.return_value = [chat.Monitor(
            "primary", PRIMARY.bounds, (48, 0, 1920, 1000), True)]
        ov = self.overlay()
        self.assertEqual((ov.anchor_x, ov.anchor_bottom), (68, 930))

    def test_drag_is_free_until_release_and_does_not_save(self):
        ov = self.overlay()
        ov.set_state("active")
        ov._drag_start(SimpleNamespace(x_root=0, y_root=0))
        ov._drag_move(SimpleNamespace(x_root=5000, y_root=0))
        self.assertEqual(ov.anchor_x, 5020)
        with patch.object(chat, "save_settings") as save:
            ov._drag_end(None)
            save.assert_not_called()
        self.assertEqual(ov._monitor_name, RIGHT.name)
        self.assert_inside(ov, RIGHT.work)
        self.assertEqual((chat.ANCHOR_X, chat.BOTTOM_MARGIN), (20, 70))

    def test_left_and_above_display_coordinates_are_absolute(self):
        for x, bottom, monitor in ((-700, 800, LEFT), (100, -200, ABOVE)):
            with self.subTest(monitor=monitor.name):
                ov = self.overlay()
                self.drop(ov, x, bottom)
                self.assertEqual(ov._monitor_name, monitor.name)
                self.assert_inside(ov, monitor.work)
                gx, gy, w, h = ov._placed_geometry
                ov.root.geometry.assert_called_with(f"{w}x{h}+{gx}+{gy}")
                self.assertIn("+-", ov.root.geometry.call_args.args[0])

    def test_every_state_fits_and_keeps_selected_monitor(self):
        ov = self.overlay()
        self.drop(ov, 3190, 100)
        ov.history = [{"type": "img"}]
        for state in ("collapsed", "popup", "active", "collapsed"):
            with self.subTest(state=state):
                ov.set_state(state)
                self.assertEqual(ov._monitor_name, RIGHT.name)
                self.assert_inside(ov, RIGHT.work)

    def test_expanding_near_top_stays_on_primary_display(self):
        ov = self.overlay()
        ov.anchor_x, ov.anchor_bottom = 100, 50
        ov._geometry()
        ov.set_state("active")
        self.assertEqual(ov._monitor_name, PRIMARY.name)
        self.assert_inside(ov, PRIMARY.work)

    def test_sizes_are_capped_temporarily_and_restore_on_larger_display(self):
        tiny = chat.Monitor("tiny", (1920, 0, 2220, 200),
                            (1920, 0, 2220, 180))
        self.displays.return_value = [PRIMARY, tiny]
        ov = self.overlay()
        self.drop(ov, 2000, 180)
        self.assertEqual(ov._placed_geometry[2:], (300, 180))
        self.assertEqual((chat.WIDTH, chat.ACTIVE_HEIGHT), (360, 330))
        self.drop(ov, 500, 800)
        self.assertEqual(ov._placed_geometry[2:], (360, 330))

    def test_unrelated_settings_preserve_session_position(self):
        ov = self.overlay()
        self.drop(ov, -700, 800)
        before = ov._placed_geometry
        with patch.object(chat, "BG", "#123456"):
            ov.apply_settings()
        self.assertEqual(ov._placed_geometry, before)

    def test_settings_resize_remains_inside_current_display(self):
        ov = self.overlay()
        self.drop(ov, 3000, 950)
        with patch.object(chat, "WIDTH", 900), \
                patch.object(chat, "ACTIVE_HEIGHT", 1000):
            ov.apply_settings()
            self.assert_inside(ov, RIGHT.work)
            self.assertEqual(ov._placed_geometry[2:], (900, 984))

    def test_monitor_removal_returns_to_primary_startup_position(self):
        ov = self.overlay()
        self.drop(ov, -700, 800)
        self.displays.return_value = [PRIMARY]
        ov._check_displays()
        self.assertEqual((ov.anchor_x, ov.anchor_bottom), (20, 970))
        self.assertEqual(ov._monitor_name, PRIMARY.name)
        self.assert_inside(ov, PRIMARY.work)

    def test_monitor_changes_wait_until_drag_finishes(self):
        ov = self.overlay()
        self.drop(ov, 2400, 800)
        ov._drag_start(SimpleNamespace(x_root=0, y_root=0))
        self.displays.return_value = [PRIMARY]
        before = ov._placed_geometry
        ov._check_displays()
        self.assertEqual(ov._placed_geometry, before)
        ov._drag_end(None)
        self.assert_inside(ov, PRIMARY.work)

    def test_work_area_change_clamps_without_stealing_focus(self):
        ov = self.overlay()
        self.drop(ov, 2700, 950)
        smaller = chat.Monitor(RIGHT.name, RIGHT.bounds, (1920, 0, 3200, 600))
        self.displays.return_value = [PRIMARY, smaller]
        ov._focus_entry.reset_mock()
        ov._check_displays()
        self.assert_inside(ov, smaller.work)
        self.assertEqual(ov._monitor_name, RIGHT.name)
        ov._focus_entry.assert_not_called()

    def test_unchanged_displays_do_not_reapply_geometry(self):
        ov = self.overlay()
        ov.root.geometry.reset_mock()
        ov._check_displays()
        ov.root.geometry.assert_not_called()

    def test_menu_reset_preserves_state_and_history(self):
        ov = self.overlay()
        self.drop(ov, 2400, 800)
        ov.history.append({"type": "chat", "text": "keep this"})
        with patch.object(chat, "save_settings") as save:
            ov.reset_window_position()
            save.assert_not_called()
        self.assertEqual(ov.state, "active")
        self.assertEqual(ov.history[0]["text"], "keep this")
        self.assertEqual((ov.anchor_x, ov.anchor_bottom), (20, 970))

    def test_reset_of_oversized_chat_stays_on_small_primary(self):
        small = chat.Monitor(PRIMARY.name, (0, 0, 800, 480),
                             (0, 0, 800, 440), True)
        self.displays.return_value = [small, ABOVE]
        ov = self.overlay()
        with patch.object(chat, "ACTIVE_HEIGHT", 1000):
            ov.set_state("active")
            ov.reset_window_position()
            self.assertEqual(ov._monitor_name, small.name)
            self.assert_inside(ov, small.work)

    def test_summon_resets_and_opens_collapsed_chat_without_pynput(self):
        ov = self.overlay()
        self.drop(ov, 2400, 800)
        ov.set_state("collapsed")
        ov._handle_incoming({"type": "summon"})
        self.assertEqual(ov.state, "active")
        self.assertEqual((ov.anchor_x, ov.anchor_bottom), (20, 970))
        ov._focus_entry.assert_called()

    def test_non_windows_dragging_is_not_restricted_to_tk_primary(self):
        with patch.object(chat.sys, "platform", "darwin"):
            ov = self.overlay()
            self.drop(ov, -2000, 800)
            self.assertEqual(ov.anchor_x, -2000)
            ov.reset_window_position()
            self.assertEqual((ov.anchor_x, ov.anchor_bottom), (20, 970))


class SettingsWindowCloseTests(unittest.TestCase):
    def window(self):
        settings = chat.SettingsWindow.__new__(chat.SettingsWindow)
        settings.snapshot = {"FONT_SIZE": 16}
        settings.job = None
        settings.closed = False
        settings.win = Mock()
        settings.ov = Mock()
        settings.ov.settings_win = settings
        settings.ov.busy = True
        return settings

    def test_cancel_closes_before_restoring_preview(self):
        settings = self.window()
        order = []
        settings.close = Mock(side_effect=lambda: order.append("close"))
        settings.ov.apply_settings.side_effect = (
            lambda: order.append("apply"))

        with patch.object(chat, "set_value",
                          side_effect=lambda *args: order.append("restore")), \
                patch.object(chat, "log"):
            chat.SettingsWindow.cancel(settings)

        self.assertEqual(order, ["close", "restore", "apply"])

    def test_cancel_stays_closed_if_preview_restore_fails(self):
        settings = self.window()

        with patch.object(chat, "set_value",
                          side_effect=RuntimeError("preview failure")), \
                patch.object(chat, "log"):
            chat.SettingsWindow.cancel(settings)

        settings.win.destroy.assert_called_once_with()
        self.assertIsNone(settings.ov.settings_win)
        self.assertFalse(settings.ov.busy)


class SettingsTests(unittest.TestCase):
    def test_old_position_keys_are_ignored_and_other_preferences_survive(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(chat.__dict__, chat.DEFAULTS), \
                patch.object(chat, "SETTINGS_PATH",
                             os.path.join(directory, "settings.json")):
            with open(chat.SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump({"ANCHOR_X": 5000, "BOTTOM_MARGIN": 3000,
                           "BG": "#abcdef", "DEFAULT_NAME": "Lucy"}, f)
            chat.load_settings()
            self.assertEqual((chat.ANCHOR_X, chat.BOTTOM_MARGIN), (20, 70))
            self.assertEqual(chat.BG, "#abcdef")
            self.assertEqual(chat.DEFAULT_NAME, "Lucy")
            self.assertTrue(chat.save_settings())
            with open(chat.SETTINGS_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertNotIn("ANCHOR_X", saved)
            self.assertNotIn("BOTTOM_MARGIN", saved)
            self.assertEqual(saved["BG"], "#abcdef")
            self.assertEqual(saved["DEFAULT_NAME"], "Lucy")


if __name__ == "__main__":
    unittest.main()
