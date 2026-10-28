"""Two real protocol clients with fake HTTP, clocks and headless windows."""
import copy
import io
import json
import os
import queue
import random
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import studychat as chat


class Clock:
    def __init__(self):
        self.now = 1000.0

    def mono(self):
        return self.now

    def wall(self):
        return 1800000000 + self.now

    def advance(self, seconds=1):
        self.now += seconds


class Room:
    def __init__(self, count=2):
        self.clock = Clock()
        self.messages = []
        self.clients = []
        for i in range(count):
            net = chat.RelayNet.__new__(chat.RelayNet)
            net.uid, net.name, net.room = str(i), f"Player {i}", "test"
            net.base, net.topic, net.token = "https://relay.invalid", "test", None
            net.seen, net.last_id = set(), None
            net.connected, net.join_ok, net.closed = True, True, False
            net.ping_every = 240
            net.stop = threading.Event()
            net.inbox = queue.Queue()
            net.outbox = chat.RelayOutbox(net.inbox, clock=self.clock.mono,
                                         wall=self.clock.wall, jitter=lambda a, b: a)
            net._open = lambda req, timeout, net=net: self.publish(net, req)
            ov = chat.Overlay.__new__(chat.Overlay)
            ov.net, ov.root, ov.game, ov.duel = net, Mock(), None, None
            ov.settings_win, ov.busy = None, False
            for method in ("note", "add", "redraw", "_touch", "_duel_popup",
                           "_duel_window", "_duel_close_popup"):
                setattr(ov, method, Mock())
            self.clients.append(ov)
        for ov in self.clients:
            ov.presence = chat.Presence()
            ov.presence.peers = {peer.net.uid: (peer.net.name, time.time())
                                 for peer in self.clients if peer is not ov}
            ov.last_tick = ov.last_ping = ov.start_time = ov.ready_at = time.time()
            ov.roll_done, ov.tick_n, ov.state = True, 0, "collapsed"
            ov._fonts_tick = Mock()
            ov.tick()  # exercise the real room/presence integration

    def publish(self, net, req):
        msg = json.loads(req.data)
        ev = {"event": "message", "id": str(len(self.messages) + 1),
              "message": json.dumps(msg)}
        self.messages.append(ev)
        for client in self.clients:
            if client.net.connected:
                client.net._handle(json.dumps(ev))
        return io.BytesIO(json.dumps({"id": ev["id"]}).encode())

    def receive(self):
        count = 0
        for ov in self.clients:
            while not ov.net.inbox.empty():
                msg = ov.net.inbox.get_nowait()
                count += 1
                if msg.get("type") == "delivery":
                    ov._delivery_msg(msg)
                elif "duel2" in msg or "duel" in msg:
                    ov._duel_msg(msg)
                elif "game" in msg:
                    ov._game_msg(msg)
        return count

    def flush(self):
        for _ in range(10000):
            progressed = sum(ov.net._send_once() for ov in self.clients)
            progressed += self.receive()
            if not any(j.state in ("queued", "sending", "delayed")
                       for ov in self.clients for j in ov.net.outbox.jobs.values()):
                return
            if not progressed:
                self.clock.advance()
        raise AssertionError("send queue did not settle")

    def start(self):
        self.clients[0].duel_cmd()
        self.flush()
        self.clients[1]._duel_accept()
        self.flush()

    def packets(self):
        return [json.loads(ev["message"]) for ev in self.messages]


class DuelProtocolTests(unittest.TestCase):
    def test_idle_spectators_do_not_delay_startup_or_ten_rounds(self):
        timings = []
        for count in (2, 4, 8):
            with self.subTest(members=count):
                room = Room(count)
                for ov in room.clients:
                    # Account for the normal health check and subscription.
                    self.assertEqual(ov.net.outbox.reserve_read(), 0)
                    self.assertEqual(ov.net.outbox.reserve_read(), 0)
                started = room.clock.mono()
                room.start()
                for _ in range(10):
                    for ov in room.clients:
                        ov.tick()
                    for ov in room.clients[:2]:
                        ov._duel_pick("wait")
                    room.flush()
                timings.append(room.clock.mono() - started)
                self.assertEqual(len(room.messages), 33)
                self.assertEqual(room.clients[0].duel["S"], room.clients[1].duel["S"])
        self.assertEqual(timings, [0, 0, 0])

    def test_full_fifty_round_match_has_154_publications(self):
        room = Room()
        room.start()
        a, b = room.clients
        self.assertEqual(len(room.messages), 3)
        for r in range(1, 51):
            before = len(room.messages)
            # Reverse the selection order on alternating rounds.
            for ov in room.clients[::1 if r % 2 else -1]:
                ov._duel_pick("wait")
            room.flush()
            packets = room.packets()[before:]
            moves = [p for p in packets if "duel2" in p]
            self.assertEqual([p["duel2"]["op"] for p in moves],
                             ["commit", "commit_reveal", "reveal"])
            self.assertEqual(moves[0]["uid"], str((r - 1) % 2))
            self.assertEqual(a.duel["S"], b.duel["S"])
        self.assertTrue(a.duel["over"] and b.duel["over"])
        self.assertEqual(len(room.messages), 154)
        self.assertEqual(sum(p["type"] == "msg" for p in room.packets()), 1)
        for ov in room.clients:
            for offset in range(1, 60):
                ov._duel_tick(ov.duel["over_at"] + offset)
        room.flush()
        self.assertEqual(len(room.messages), 154)

    def test_thinking_does_not_publish_and_responder_keeps_pick_hidden(self):
        room = Room()
        room.start()
        a, b = room.clients
        b._duel_pick("heavy")
        room.flush()
        for ov in room.clients:
            for offset in range(1, 120):
                ov._duel_tick(ov.duel["t0"] + offset)
        room.flush()
        self.assertEqual(len(room.messages), 3)
        self.assertNotIn((1, 1), a.duel["reveals"])
        b._duel_pick("jab")
        self.assertEqual(b.duel["pick"], "heavy")
        a._duel_pick("wait")
        room.flush()
        self.assertEqual(len(room.messages), 6)

    def test_solo_round_waits_for_publication_then_uses_one_message(self):
        room = Room()
        room.start()
        for ov in room.clients:
            ov.duel["S"]["p"][1]["stun"] = 4
        a, b = room.clients
        a._duel_pick("jab")
        self.assertEqual(a.duel["S"]["round"], 0)
        room.flush()
        self.assertEqual(len(room.messages), 4)
        self.assertEqual(a.duel["S"], b.duel["S"])
        self.assertEqual(a.duel["S"]["round"], 1)

    def test_combat_matches_pure_simulation(self):
        room = Room()
        room.start()
        rng = random.Random(219)
        expected = chat.duel_new()
        for _ in range(50):
            choices = {i: rng.choice(chat.DUEL_ORDER) for i in chat.duel_need(expected)}
            for i, move in choices.items():
                room.clients[i]._duel_pick(move)
            chat.duel_round(expected, choices)
            room.flush()
            for ov in room.clients:
                self.assertEqual(ov.duel["S"], expected)
            if expected["over"]:
                break

    def test_dash_moves_two_then_one_and_opponent_acts_each_turn(self):
        state = chat.duel_new()

        chat.duel_round(state, {0: "dash", 1: "wait"})

        self.assertEqual(state["p"][0]["x"], chat.DUEL_START[0] + 2)
        self.assertEqual(state["p"][0]["move"], "dash")
        self.assertEqual(chat.duel_need(state), [1])
        self.assertEqual(chat.duel_turn_lead(state, 0), -1)
        self.assertEqual(
            chat.duel_move_tiles("dash", 3, 1), ([4, 5, 6], "move"))

        chat.duel_round(state, {1: "wait"})

        self.assertEqual(state["p"][0]["x"], chat.DUEL_START[0] + 3)
        self.assertIsNone(state["p"][0]["move"])
        self.assertEqual(chat.duel_turn_lead(state, 0), 0)
        self.assertEqual(chat.duel_need(state), [0, 1])

    def test_selected_direction_controls_advance_and_dash(self):
        self.assertEqual(
            chat.duel_movement_action("forward", "advance"), "advance")
        self.assertEqual(
            chat.duel_movement_action("back", "advance"), "retreat")
        self.assertEqual(
            chat.duel_movement_action("forward", "dash"), "dash")
        self.assertEqual(
            chat.duel_movement_action("back", "dash"), "dash_back")

        state = chat.duel_new()
        chat.duel_round(state, {0: "dash_back", 1: "wait"})
        self.assertEqual(state["p"][0]["x"], chat.DUEL_START[0] - 2)
        self.assertEqual(state["p"][0]["move"], "dash_back")
        chat.duel_round(state, {1: "wait"})
        self.assertEqual(state["p"][0]["x"], chat.DUEL_START[0] - 3)

    def test_successful_grab_costs_two_turns_for_target(self):
        state = chat.duel_new()
        state["p"][1]["x"] = state["p"][0]["x"] + 1

        _, events = chat.duel_round(state, {0: "grab", 1: "wait"})

        self.assertEqual(state["p"][1]["stun"], 2)
        self.assertEqual(chat.duel_turn_lead(state, 0), 2)
        self.assertIn("grab:1", events)
        chat.duel_round(state, {0: "wait"})
        self.assertEqual(state["p"][1]["stun"], 1)
        chat.duel_round(state, {0: "wait"})
        self.assertEqual(state["p"][1]["stun"], 0)

    def test_turn_advantage_draws_signed_and_centered_between_healthbars(self):
        state = chat.duel_new()
        state["p"][1]["stun"] = 1
        overlay = chat.Overlay.__new__(chat.Overlay)
        canvas = Mock()
        gid = "0123456789ab"
        overlay.duel = {
            "ui": {"cv": canvas}, "gid": gid, "r": 1, "stage": 0,
            "bg_off": (0, 0), "fx": Mock(offset=Mock(return_value=(0, 0))),
            "phase": 0, "goal": None, "hl": None, "me": 0, "solo": False,
            "S": state, "names": ["Player 0", "Player 1"],
        }
        frame = chat.duel_frame(state)

        with patch.object(chat, "duel_stage_for", return_value=0), \
                patch.object(chat, "duel_tile_rects", return_value=[]), \
                patch.object(chat, "duel_fg_rects", return_value=[]):
            overlay._duel_draw(frame)

        indicator = next(call for call in canvas.create_text.call_args_list
                         if call.kwargs.get("text") == "+1 turns")
        self.assertEqual(indicator.args, (400, 16))
        self.assertEqual(indicator.kwargs["fill"], "#7be08a")
        self.assertEqual(indicator.kwargs["anchor"], "n")

        canvas.reset_mock()
        overlay.duel["me"] = 1
        with patch.object(chat, "duel_stage_for", return_value=0), \
                patch.object(chat, "duel_tile_rects", return_value=[]), \
                patch.object(chat, "duel_fg_rects", return_value=[]):
            overlay._duel_draw(frame)

        indicator = next(call for call in canvas.create_text.call_args_list
                         if call.kwargs.get("text") == "-1 turns")
        self.assertEqual(indicator.kwargs["fill"], "#ff7a7a")

    def test_failed_grab_costs_three_turns_for_grabber(self):
        state = chat.duel_new()

        _, events = chat.duel_round(state, {0: "grab", 1: "wait"})

        self.assertEqual(state["p"][0]["stun"], 3)
        self.assertEqual(chat.duel_turn_lead(state, 1), 3)
        self.assertIn("grab_fail:0:3", events)

    def test_grabbing_jabber_fails_and_costs_four_turns(self):
        state = chat.duel_new()
        state["p"][1]["x"] = state["p"][0]["x"] + 1

        _, events = chat.duel_round(state, {0: "grab", 1: "jab"})

        self.assertEqual(state["p"][0]["stun"], 4)
        self.assertIn("grab_fail:0:4", events)

    def test_grabbing_heavy_windup_fails_and_costs_three_turns(self):
        state = chat.duel_new()
        state["p"][1]["x"] = state["p"][0]["x"] + 1
        state["p"][1]["move"] = "heavy"

        _, events = chat.duel_round(state, {0: "grab"})

        self.assertEqual(state["p"][0]["stun"], 3)
        self.assertEqual(state["p"][1]["hp"], chat.DUEL_HP)
        self.assertIn("grab_fail:0:3", events)

    def test_grabbing_during_heavy_windup_fails_without_canceling_attack(self):
        state = chat.duel_new()
        state["p"][1]["x"] = state["p"][0]["x"] + 1

        _, events = chat.duel_round(state, {0: "grab", 1: "heavy"})

        self.assertEqual(state["p"][0]["stun"], 3)
        self.assertEqual(state["p"][1]["move"], "heavy")
        self.assertIn("grab_fail:0:3", events)

    def test_simultaneous_grabs_fail_for_both_players(self):
        state = chat.duel_new()
        state["p"][1]["x"] = state["p"][0]["x"] + 1

        _, events = chat.duel_round(state, {0: "grab", 1: "grab"})

        self.assertEqual([p["stun"] for p in state["p"]], [3, 3])
        self.assertIn("grab_fail:0:3", events)
        self.assertIn("grab_fail:1:3", events)

    def test_duplicate_events_and_reconnect_replay_do_not_repeat_turn(self):
        room = Room()
        room.start()
        a, b = room.clients
        b.net.connected = False
        a._duel_pick("wait")
        room.flush()
        b.net.connected = True
        cursor = int(b.net.last_id)
        for ev in room.messages[cursor:]:
            b.net._handle(json.dumps(ev))
        room.receive()
        b._duel_pick("wait")
        room.flush()
        before = copy.deepcopy(a.duel["S"])
        for packet in room.packets():
            if "duel2" in packet and packet["duel2"].get("r"):
                receiver = b if packet["uid"] == a.net.uid else a
                receiver._duel_msg(packet)  # logical duplicate, bypass envelope dedup
        room.flush()
        self.assertEqual(a.duel["S"], before)
        self.assertEqual(a.duel["S"], b.duel["S"])
        self.assertEqual(len(room.messages), 6)

    def test_future_solo_rounds_are_buffered_during_slow_animation(self):
        room = Room()
        room.start()
        a, b = room.clients
        for ov in room.clients:
            ov.duel["S"]["p"][1]["stun"] = 100
        b.duel["anim"] = True
        for _ in range(4):
            a._duel_pick("wait")
            room.flush()
        self.assertEqual(a.duel["S"]["round"], 4)
        self.assertIn((4, 0), b.duel["reveals"])
        b.duel["anim"] = False
        b._duel_progress()
        self.assertEqual(a.duel["S"], b.duel["S"])

    def test_invalid_combined_commitment_cannot_advance(self):
        room = Room()
        room.start()
        a, b = room.clients
        a._duel_pick("wait")
        room.flush()
        a._duel_msg({"uid": b.net.uid, "duel2": {
            "gid": a.duel["gid"], "v": 2, "op": "commit_reveal", "r": 1,
            "h": "0" * 64, "m": "heavy", "nonce": "invalid"}})
        self.assertNotIn((1, 1), a.duel["reveals"])
        self.assertEqual(a.duel["S"]["round"], 0)

    def test_cancel_drops_stale_move_and_timeout_never_announces_winner(self):
        room = Room()
        room.start()
        a, _ = room.clients
        a._duel_pick("wait")
        a._duel_tick(a.duel["t0"] + a.DUEL_SECONDS + 1)
        room.flush()
        self.assertTrue(a.duel["over"])
        self.assertEqual(len(room.messages), 3)

    def test_legacy_invitation_is_update_notice_only(self):
        room = Room()
        a, _ = room.clients
        a._duel_msg({"uid": "peer", "duel": {"op": "challenge", "gid": "0" * 12}})
        self.assertIsNone(a.duel)
        self.assertIn("updated app", a.note.call_args.args[0])
        a.net.mode = "wifi"
        a._duel_msg({"uid": "peer", "duel2": {"v": 2, "op": "challenge", "gid": "0" * 12}})
        self.assertIsNone(a.duel)

    def test_lan_still_uses_legacy_commit_reveal_and_retries(self):
        room = Room()
        a, _ = room.clients
        a.net.mode = "wifi"
        a.duel = a._duel_blank("0" * 12, a.net.uid, a.net.name, True)
        a._duel_start(["0", "1"], ["A", "B"])
        a._duel_pick("wait")
        jobs = list(a.net.outbox.jobs.values())
        self.assertEqual(jobs[0].msg["duel"]["op"], "commit")
        a._duel_tick(a.duel["resend_at"] + 1)
        self.assertGreater(len(a.net.outbox.jobs), 1)


class DuelHandshakeTests(unittest.TestCase):
    def overlay(self, mine, state, uid, host_uid="host"):
        ov = chat.Overlay.__new__(chat.Overlay)
        ov.net = Mock()
        ov.net.uid, ov.net.name = uid, "Player"
        ov.duel = {
            "gid": "0123456789ab", "host_uid": host_uid, "host": "Host",
            "mine": mine, "state": state, "over": False,
            "uids": ["host", "guest"], "names": ["Host", "Guest"],
            "hist": {}, "reply_at": {},
        }
        ov._duel_send = Mock()
        ov._duel_start = Mock()
        ov._duel_close_popup = Mock()
        ov._duel_over = Mock()
        ov._duel_reply = Mock()
        ov.note = Mock()
        return ov

    def test_challenger_acks_accept_and_starts_without_waiting_for_a_move(self):
        host = self.overlay(True, "waiting", "host")

        host._duel_msg({
            "uid": "guest", "name": "Guest",
            "duel": {"op": "accept", "gid": "0123456789ab"},
        })

        host._duel_send.assert_called_once_with({
            "op": "start", "p2": "guest", "n1": "Player",
        })
        host._duel_start.assert_called_once_with(
            ["host", "guest"], ["Player", "Guest"])
        self.assertEqual(host.duel["state"], "waiting")
        self.assertEqual(host.duel["go"], {"vs": "guest", "n1": "Guest"})

    def test_acceptor_opens_duel_when_host_start_ack_arrives(self):
        guest = self.overlay(False, "accepting", "guest")

        guest._duel_msg({
            "uid": "host", "name": "Host",
            "duel": {"op": "start", "gid": "0123456789ab",
                     "p2": "guest", "n1": "Host"},
        })

        guest._duel_close_popup.assert_called_once_with()
        guest._duel_start.assert_called_once_with(
            ["host", "guest"], ["Host", "Player"])
        guest._duel_over.assert_not_called()

    def test_start_ack_for_another_acceptor_does_not_start_duel(self):
        guest = self.overlay(False, "accepting", "guest")

        guest._duel_msg({
            "uid": "host", "name": "Host",
            "duel": {"op": "start", "gid": "0123456789ab",
                     "p2": "someone-else", "n1": "Host"},
        })

        guest._duel_start.assert_not_called()
        guest._duel_over.assert_called_once_with()


class DuelRematchTests(unittest.TestCase):
    def overlay(self, mine, uid, rematch_state="ready"):
        ov = chat.Overlay.__new__(chat.Overlay)
        ov.net = Mock()
        ov.net.uid, ov.net.name = uid, "Player"
        ov.root = Mock()
        ov.duel = {
            "gid": "0123456789ab", "host_uid": "host", "host": "Host",
            "mine": mine, "state": "playing", "over": True,
            "uids": ["host", "guest"], "names": ["Host", "Guest"],
            "me": 0 if uid == "host" else 1,
            "rematch_state": rematch_state, "ui": None, "solo": False,
        }
        ov._duel_send = Mock()
        ov._duel_begin_rematch = Mock()
        ov._duel_restart = Mock()
        return ov

    def test_rematch_button_sends_request_and_waits_for_acceptance(self):
        host = self.overlay(True, "host")

        host._duel_rematch()

        host._duel_send.assert_called_once_with({"op": "rematch"})
        self.assertEqual(host.duel["rematch_state"], "waiting")

    def test_host_accepting_guest_request_starts_the_rematch(self):
        host = self.overlay(True, "host")
        message = {"uid": "guest", "name": "Guest",
                   "duel": {"op": "rematch", "gid": "0123456789ab"}}

        with patch("tkinter.messagebox.askyesno", return_value=True):
            host._duel_msg(message)

        host._duel_begin_rematch.assert_called_once_with()

    def test_guest_acceptance_starts_host_initiated_rematch(self):
        host = self.overlay(True, "host", "waiting")
        message = {"uid": "guest", "name": "Guest",
                   "duel": {"op": "rematch_accept", "gid": "0123456789ab"}}

        host._duel_msg(message)

        host._duel_begin_rematch.assert_called_once_with()

    def test_rematch_start_uses_a_new_id_and_targets_the_opponent(self):
        host = self.overlay(True, "host")
        host._duel_begin_rematch = chat.Overlay._duel_begin_rematch.__get__(
            host)
        with patch.object(chat.uuid, "uuid4") as uuid4:
            uuid4.return_value.hex = "abcdef0123456789"

            host._duel_begin_rematch()

        host._duel_send.assert_called_once_with({
            "op": "rematch_start", "p2": "guest", "ngid": "abcdef012345",
        })
        host._duel_restart.assert_called_once_with("abcdef012345")

    def test_guest_starts_only_after_valid_host_rematch_start(self):
        guest = self.overlay(False, "guest", "accepting")
        message = {
            "uid": "host", "name": "Host",
            "duel": {"op": "rematch_start", "gid": "0123456789ab",
                     "p2": "guest", "ngid": "abcdef012345"},
        }

        guest._duel_msg(message)

        guest._duel_restart.assert_called_once_with("abcdef012345")

    def test_guest_requester_starts_after_host_accepts(self):
        guest = self.overlay(False, "guest", "waiting")
        message = {
            "uid": "host", "name": "Host",
            "duel": {"op": "rematch_start", "gid": "0123456789ab",
                     "p2": "guest", "ngid": "abcdef012345"},
        }

        guest._duel_msg(message)

        guest._duel_restart.assert_called_once_with("abcdef012345")

    def test_guest_ignores_rematch_start_for_another_player(self):
        guest = self.overlay(False, "guest", "accepting")
        message = {
            "uid": "host", "name": "Host",
            "duel": {"op": "rematch_start", "gid": "0123456789ab",
                     "p2": "someone-else", "ngid": "abcdef012345"},
        }

        guest._duel_msg(message)

        guest._duel_restart.assert_not_called()


class DuelStatusTests(unittest.TestCase):
    def setUp(self):
        self.room = Room()
        self.ov = self.room.clients[0]
        self.ov.duel = self.ov._duel_blank("0" * 12, "0", "Player 0", True)
        self.ov._duel_start(["0", "1"], ["Player 0", "Player 1"])
        self.ov.duel["ui"] = {"status": Mock(), "info": Mock(), "btns": {}}
        self.ov.duel["retry_button"] = Mock()
        self.go = self.ov._duel_send({"op": "go", "p1": "1"})

    def deliver(self, msg, state, **extra):
        self.ov._delivery_msg({"id": msg["id"], "gid": self.ov.duel["gid"],
                               "state": state, "text": "", **extra})

    def status(self):
        return self.ov.duel["ui"]["status"].config.call_args.kwargs["text"]

    def delayed(self, msg):
        self.deliver(msg, "delayed", text="Queued to send.", reason="budget",
                     retry_at=self.room.clock.mono() + 5)

    def test_successful_startup_publication_restores_pick_instruction(self):
        self.delayed(self.go)
        self.assertIn("Queued to send", self.status())
        self.assertIn("~5s", self.status())
        self.deliver(self.go, "published")
        self.assertEqual(self.status(), "Round 1: pick your move (1-5)")
        self.delayed(self.go)  # stale callback cannot reopen a completed send
        self.assertEqual(self.status(), "Round 1: pick your move (1-5)")

    def test_countdown_changes_without_extra_delivery_events(self):
        self.delayed(self.go)
        self.room.clock.advance(2)
        self.ov._duel_tick(time.time())
        self.assertIn("~3s", self.status())

    def test_old_round_delay_does_not_overwrite_current_instruction(self):
        old = self.ov._duel_send({"op": "commit", "r": 1, "h": "0" * 64})
        self.ov.duel["S"]["round"] = 1
        self.ov._duel_begin_round()
        self.delayed(old)
        self.assertEqual(self.status(), "Round 2: pick your move (1-5)")
        self.deliver(old, "failed", text="Old failure")
        self.assertEqual(self.status(), "Round 2: pick your move (1-5)")
        self.ov.duel["retry_button"].config.assert_called_with(state="disabled")

    def test_old_success_does_not_clear_current_move_delay(self):
        self.ov._duel_pick("wait")
        move = {"id": self.ov.duel["delivery"][(1, "commit")]["id"]}
        self.delayed(move)
        self.deliver(self.go, "published")
        self.assertIn("Queued to send", self.status())

    def test_cancel_and_late_success_keep_no_result_status(self):
        self.delayed(self.go)
        self.ov._duel_abort("Interrupted duel cancelled. No result.")
        self.deliver(self.go, "cancelled")
        self.deliver(self.go, "published")
        self.assertEqual(self.status(), "Interrupted duel cancelled. No result.")

    def test_disconnection_is_distinct_from_local_budget_wait(self):
        self.deliver(self.go, "published")
        self.ov.net.connected = False
        self.ov._duel_tick(time.time())
        self.assertEqual(self.status(), "Waiting for the relay connection.")
        self.ov.net.connected = True
        self.ov._duel_tick(time.time())
        self.assertEqual(self.status(), "Round 1: pick your move (1-5)")


class NumberGuesserTests(unittest.TestCase):
    def test_published_guess_is_not_republished_by_timer(self):
        room = Room()
        a = room.clients[0]
        a.game = {"gid": "0" * 12, "mine": False, "over": False, "host": "Host",
                  "my_guess": 3, "t0": time.time(), "asked_at": time.time(), "resent": False,
                  "ui": None}
        a._game_send_guess(3)
        # Publish only to our own stream; no host/UI required for this test.
        room.clients = [a]
        room.flush()
        for seconds in (21, 40, 60):
            a._game_tick(a.game["asked_at"] + seconds)
        self.assertEqual(len(room.messages), 1)


class NumberGuesserOutcomeTests(unittest.TestCase):
    def make_overlay(self, with_ui=True):
        ov = chat.Overlay.__new__(chat.Overlay)
        ov.game = {"gid": "0123456789ab", "ui": None}
        ov.root = Mock()
        if with_ui:
            ov.game["ui"] = {
                key: Mock() for key in
                ("title", "info", "entry", "status", "guess", "skip")
            }
        return ov

    def test_wrong_guess_eliminates_player_without_quitting_chat(self):
        ov = self.make_overlay()

        ov._game_result_ui(True, False, "Player", 4, None)

        text = ov.game["ui"]["title"].config.call_args.kwargs["text"]
        self.assertIn("out for this round", text)
        ov.root.after.assert_called_once()
        self.assertEqual(ov.root.after.call_args.args[0], 5000)

    def test_wrong_result_after_popup_was_closed_does_not_quit_chat(self):
        ov = self.make_overlay(with_ui=False)

        ov._game_result_ui(True, False, "Player", 4, None)

        ov.root.after.assert_not_called()

    def test_another_players_wrong_guess_does_not_close_my_popup(self):
        ov = self.make_overlay()
        title = ov.game["ui"]["title"]

        ov._game_result_ui(False, False, "Player", 4, None)

        title.config.assert_not_called()
        ov.root.after.assert_not_called()

    def test_host_does_not_disclose_secret_for_a_wrong_guess(self):
        ov = chat.Overlay.__new__(chat.Overlay)
        ov.game = {
            "gid": "0123456789ab", "mine": True, "over": False,
            "max": 10, "secret": 7, "guessed": {},
        }
        ov.net = Mock(uid="host")
        ov._deliver = Mock()
        ov.net.send.return_value = {}

        ov._game_msg({
            "uid": "guest", "name": "Guest",
            "game": {"op": "guess", "gid": "0123456789ab", "n": 4},
        })

        result = ov.net.send.call_args.kwargs["extra"]["game"]
        self.assertFalse(result["ok"])
        self.assertNotIn("secret", result)


class SharedFontFolderTests(unittest.TestCase):
    def test_saved_font_is_discovered_and_not_duplicated(self):
        data = b"\x00\x01\x00\x00" + b"\x00" * 20
        with tempfile.TemporaryDirectory() as folder:
            path = chat.save_to_font_folder(folder, data, "Demo.ttf")

            self.assertTrue(os.path.isfile(path))
            found = chat.scan_font_folder(folder, {})
            digest = chat.font_hash(data)
            self.assertEqual(found[digest]["n"], "Demo.ttf")
            self.assertIsNone(chat.save_to_font_folder(folder, data, "Copy.ttf"))

    def test_folder_fonts_are_announced_to_the_room(self):
        data = b"\x00\x01\x00\x00" + b"\x00" * 20
        with tempfile.TemporaryDirectory() as folder:
            chat.save_to_font_folder(folder, data, "Demo.ttf")
            ov = chat.Overlay.__new__(chat.Overlay)
            ov.fonts_dir_override = folder
            ov.font_due = 0
            ov.font_cache = {}
            ov.font_mine = {}
            ov.font_announced = frozenset()
            ov.font_seen = set()
            ov.font_wanted = {}
            ov.font_folder_noted = True
            ov.net = Mock(join_ok=True)
            ov.note = Mock()

            ov._fonts_tick(10)

            sent = ov.net.send.call_args.kwargs["extra"]["fontlist"]
            self.assertEqual(sent[0]["h"], chat.font_hash(data))
            self.assertEqual(sent[0]["n"], "Demo.ttf")


if __name__ == "__main__":
    unittest.main()
