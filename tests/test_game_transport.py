"""Two real protocol clients with fake HTTP, clocks and headless windows."""
import copy
import io
import json
import queue
import random
import threading
import time
import unittest
from unittest.mock import Mock

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
            net.stop = threading.Event()
            net.inbox = queue.Queue()
            net.outbox = chat.RelayOutbox(net.inbox, clock=self.clock.mono,
                                         wall=self.clock.wall, jitter=lambda a, b: a)
            net.outbox.set_members(count)
            net._open = lambda req, timeout, net=net: self.publish(net, req)
            ov = chat.Overlay.__new__(chat.Overlay)
            ov.net, ov.root, ov.game, ov.duel = net, Mock(), None, None
            ov.settings_win, ov.busy = None, False
            for method in ("note", "add", "redraw", "_touch", "_duel_popup",
                           "_duel_window", "_duel_close_popup"):
                setattr(ov, method, Mock())
            self.clients.append(ov)

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
            for ov in self.clients:
                ov.net._send_once()
            self.receive()
            if not any(j.state in ("queued", "sending", "delayed")
                       for ov in self.clients for j in ov.net.outbox.jobs.values()):
                return
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


if __name__ == "__main__":
    unittest.main()
