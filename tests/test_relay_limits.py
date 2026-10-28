import io
import json
import os
import queue
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

import studychat as chat
from test_game_transport import Clock, Room


def packet(mid, op=None, gid="0123456789ab", **extra):
    msg = {"app": "studychat", "room": "test", "uid": "0", "id": mid,
           "name": "Player", "type": "ping" if op else "msg", "text": ""}
    if op:
        msg["duel2"] = {"v": 2, "gid": gid, "op": op, "r": 1}
    msg.update(extra)
    return msg


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.inbox = queue.Queue()
        self.out = chat.RelayOutbox(self.inbox, clock=self.clock.mono,
                                   wall=self.clock.wall, jitter=lambda a, b: a)

    def publish(self, mid):
        self.out.enqueue(packet(mid))
        job = self.out.take()
        self.assertIsNotNone(job)
        self.out.published(job.msg["id"], "receipt-" + mid)

    def test_default_burst_and_exact_five_second_refill(self):
        for i in range(60):
            self.publish(str(i))
        self.out.enqueue(packet("next"))
        self.assertIsNone(self.out.take())
        self.clock.advance(4.999)
        self.assertIsNone(self.out.take())
        self.clock.advance(.001)
        self.assertEqual(self.out.take().msg["id"], "next")

    def test_request_cooldown_includes_game_chat_terminal_and_read_requests(self):
        for mid, op in (("game", "commit"), ("chat", None), ("quit", "quit")):
            self.out.enqueue(packet(mid, op))
        self.out.throttle(42901, 90)
        self.clock.advance(89)
        self.assertIsNone(self.out.take())
        self.assertGreater(self.out.reserve_read(), 0)
        self.clock.advance(1)
        job = self.out.take()
        self.assertEqual(job.msg["id"], "quit")
        self.out.published("quit")
        self.assertIsNone(self.out.take())  # only one request at cooldown expiry
        self.clock.advance(5)
        self.assertEqual(self.out.take().msg["id"], "chat")

    def test_backoff_is_capped_and_idle_restores_normal_capacity(self):
        for i, expected in enumerate((15, 30, 60, 120, 240, 300, 300)):
            self.out.throttle(42901)
            self.assertEqual(self.out.cool_until - self.clock.mono(), expected)
            self.clock.advance(expected)
        self.clock.advance(600)
        for i in range(60):
            self.publish(f"after-idle-{i}")
        self.out.enqueue(packet("next"))
        self.assertIsNone(self.out.take())
        self.clock.advance(5)
        self.assertIsNotNone(self.out.take())

    def test_only_fresh_post_cooldown_http_success_resets_streak(self):
        old_stamp = self.out.request_stamp()
        self.out.enqueue(packet("echo"))
        self.out.throttle(42901, 15)
        self.clock.advance(15)
        self.out.published("echo")
        self.out.http_success(old_stamp)
        self.assertEqual(self.out.cool_n, 1)
        self.out.http_success(self.out.request_stamp())
        self.assertEqual(self.out.cool_n, 0)
        self.out.throttle(42901)
        self.assertEqual(self.out.cool_until - self.clock.mono(), 15)

    def test_zero_retry_after_allows_one_request_immediately(self):
        self.out.throttle(42901, 0)
        self.publish("probe")
        self.out.enqueue(packet("next"))
        self.assertIsNone(self.out.take())
        self.clock.advance(5)
        self.assertIsNotNone(self.out.take())

    def test_chat_can_pass_game_retry_but_game_events_stay_in_order(self):
        self.out.enqueue(packet("commit", "commit"))
        job = self.out.take()
        self.out.failed(job, "temporary")
        self.out.enqueue(packet("reveal", "reveal"))
        self.out.enqueue(packet("chat"))
        selected = self.out.take()
        self.assertEqual(selected.msg["id"], "chat")
        self.out.published("chat")
        self.assertIsNone(self.out.take())
        self.clock.advance(5)
        selected = self.out.take()
        self.assertEqual(selected.msg["id"], "commit")
        self.out.published("commit")
        self.assertEqual(self.out.take().msg["id"], "reveal")

    def test_three_automatic_retries_then_explicit_retry_keeps_id(self):
        self.out.enqueue(packet("fixed", "commit"))
        for i in range(4):
            job = self.out.take()
            self.assertEqual(job.msg["id"], "fixed")
            self.out.failed(job, "offline")
            self.clock.advance((5, 15, 30, 30)[i])
        self.assertEqual(job.state, "failed")
        self.assertIsNone(self.out.take())
        self.out.retry("fixed")
        self.assertEqual(self.out.take().msg["id"], "fixed")

    def test_successful_publish_or_echo_cannot_be_retried(self):
        self.out.enqueue(packet("fixed", "commit"))
        job = self.out.take()
        self.out.published("fixed", "ntfy-event")
        self.out.failed(job, "lost response")
        self.out.retry("fixed")
        self.assertIsNone(self.out.take())
        self.out.published("fixed", "ntfy-event")
        self.assertEqual(self.out.count, 1)
        self.out.published("fixed", "another-accepted-http-attempt")
        self.assertEqual(self.out.count, 2)

    def test_daily_exhaustion_persists_and_does_not_stop_receiving(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "usage.json")
            self.clock.now = (int(self.clock.wall() // 86400) + 1) * 86400 - 1800000000 - 30
            out = chat.RelayOutbox(self.inbox, path, self.clock.mono, self.clock.wall)
            out.enqueue(packet("before"))
            out.published("before", "receipt")
            out.throttle(42908)
            restarted = chat.RelayOutbox(self.inbox, path, self.clock.mono, self.clock.wall)
            self.assertEqual(restarted.count, 1)
            restarted.enqueue(packet("after", "commit"))
            self.assertIsNone(restarted.take())
            self.assertEqual(restarted.reserve_read(), 0)
            self.clock.advance(31)
            self.assertIsNotNone(restarted.take())
            self.assertEqual(restarted.count, 0)
            self.assertEqual(restarted.quota_until, 0)

    def test_warning_labels_local_usage_not_remaining_quota(self):
        self.out.count = 199
        self.publish("warning")
        events = []
        while not self.inbox.empty():
            events.append(self.inbox.get_nowait())
        note = next(e["text"] for e in events if e["type"] == "sys")
        self.assertIn("This device", note)
        self.assertIn("shared", note)
        self.assertNotIn("remaining", note)

    def test_background_signals_coalesce_but_moves_do_not(self):
        self.out.enqueue(packet("old", type="ping"))
        self.out.enqueue(packet("new", type="ping"))
        self.out.enqueue(packet("commit", "commit"))
        self.out.enqueue(packet("reveal", "reveal"))
        self.assertEqual(self.out.jobs["old"].state, "cancelled")
        self.assertEqual(self.out.jobs["new"].state, "queued")
        self.assertEqual(self.out.jobs["commit"].state, "queued")
        self.assertEqual(self.out.jobs["reveal"].state, "queued")

    def test_cancel_keeps_terminal_message_and_drops_obsolete_moves(self):
        self.out.enqueue(packet("move", "commit"))
        self.out.enqueue(packet("quit", "quit"))
        self.out.cancel_game("0123456789ab")
        self.assertEqual(self.out.jobs["move"].state, "cancelled")
        self.assertEqual(self.out.take().msg["id"], "quit")

    def test_game_waits_for_subscription_but_chat_can_publish(self):
        self.out.enqueue(packet("move", "commit"))
        self.out.enqueue(packet("chat"))
        self.assertEqual(self.out.take(connected=False).msg["id"], "chat")
        self.out.published("chat")
        self.assertIsNone(self.out.take(connected=False))
        self.assertEqual(self.out.take().msg["id"], "move")

    def test_settings_allow_custom_relay_limits(self):
        with patch.object(chat, "RELAY_REFILL_SECONDS", 1), patch.object(chat, "RELAY_BURST", 1):
            self.publish("one")
            self.out.enqueue(packet("two"))
            self.assertIsNone(self.out.take())
            self.clock.advance(1)
            self.assertEqual(self.out.take().msg["id"], "two")

    def test_replay_bandwidth_quota_does_not_block_text_publications(self):
        self.out.throttle(42905)
        self.assertGreater(self.out.reserve_read(), 0)
        self.publish("chat-still-works")

    def test_aborted_game_cannot_later_publish_a_forfeit(self):
        self.out.enqueue(packet("quit", "quit"))
        job = self.out.take()
        self.out.failed(job, "failed", transient=False)
        self.out.cancel_game("0123456789ab", keep_terminal=False)
        self.assertEqual(self.out.retry_failed(), 0)
        self.assertIsNone(self.out.take())

    def test_wait_metadata_is_distinct_and_diagnostics_exclude_content(self):
        diagnostics = []
        self.out.logger = diagnostics.append
        self.out.tokens = 0
        self.out.enqueue(packet("move", "commit", text="PRIVATE CONTENT", name="PRIVATE NAME"))
        self.assertIsNone(self.out.take())
        job = self.out.jobs["move"]
        self.assertEqual((job.reason, job.http_code), ("budget", None))
        self.assertEqual(job.retry_at, self.clock.mono() + 5)
        self.out.throttle(42901, 30, "duel")
        self.assertIsNone(self.out.take())
        self.assertEqual((job.reason, job.http_code), ("server_limit", 429))
        self.assertEqual(job.retry_at, self.clock.mono() + 30)
        before = len(diagnostics)
        for _ in range(4):
            self.clock.advance(.25)
            self.out.take()
        self.assertEqual(len(diagnostics), before)
        self.out.throttle(42908, category="duel")
        self.out.take()
        self.assertEqual(job.reason, "daily_quota")
        logs = "\n".join(diagnostics)
        self.assertIn("reason=budget category=duel duration=5.0s http=-", logs)
        self.assertIn("reason=server_limit category=duel duration=30.0s http=429", logs)
        self.assertNotIn("PRIVATE", logs)

    def test_saved_custom_limits_are_not_migrated_to_new_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = os.path.join(folder, "settings.json")
            with open(settings, "w") as f:
                json.dump({"RELAY_BURST": 12, "RELAY_REFILL_SECONDS": 7}, f)
            with patch.object(chat, "SETTINGS_PATH", settings), \
                    patch.object(chat, "RELAY_BURST", 60), \
                    patch.object(chat, "RELAY_REFILL_SECONDS", 5):
                chat.load_settings()
                self.assertEqual(chat.RELAY_BURST, 12)
                self.assertEqual(chat.RELAY_REFILL_SECONDS, 7)


class RelayHTTPTests(unittest.TestCase):
    def test_shared_server_budget_backoffs_without_changing_match(self):
        room = Room(8)
        publish = room.publish
        server = {"tokens": 60.0, "last": room.clock.mono(), "limited": 0}
        def rate_limited(net, req):
            now = room.clock.mono()
            self.assertGreaterEqual(now, net.outbox.cool_until)
            server["tokens"] = min(60, server["tokens"] + (now - server["last"]) / 5)
            server["last"] = now
            if server["tokens"] < 1:
                server["limited"] += 1
                raise urllib.error.HTTPError(net.base, 429, "request limit",
                    {"Retry-After": "5"}, io.BytesIO(b'{"code":42901}'))
            server["tokens"] -= 1
            return publish(net, req)
        room.publish = rate_limited
        room.start()
        for _ in range(50):
            for ov in room.clients[:2]:
                ov._duel_pick("wait")
            room.flush()
        self.assertGreater(server["limited"], 0)
        self.assertLessEqual(server["limited"], 100)
        self.assertEqual(len(room.messages), 154)
        self.assertEqual(room.clients[0].duel["S"], room.clients[1].duel["S"])
        self.assertTrue(all(ov.duel["over"] for ov in room.clients[:2]))
        for msg in room.packets():
            self.assertTrue({"reason", "retry_at", "http_code"}.isdisjoint(msg))
            self.assertTrue({"reason", "retry_at", "http_code"}.isdisjoint(msg.get("duel2", {})))

    def test_successful_http_read_resets_request_backoff(self):
        room = Room()
        net = room.clients[0].net
        net.outbox.throttle(42901, 15)
        room.clock.advance(15)
        net._open = Mock(return_value=io.BytesIO(b'{}'))
        with net._read_open(chat.urllib.request.Request(net.base + "/v1/health"), 8):
            pass
        self.assertEqual(net.outbox.cool_n, 0)

    def test_retry_after_seconds_date_and_invalid_header(self):
        for raw, expected in (("120", 120), ("Thu, 01 Jan 1970 00:02:00 GMT", 20),
                              ("invalid", None)):
            ex = urllib.error.HTTPError("https://relay.invalid", 429, "busy",
                {"Retry-After": raw}, io.BytesIO(b'{"code":42901}'))
            self.assertEqual(chat.relay_error(ex, 100), (42901, expected))

    def test_http_429_uses_daily_code_and_stops_next_post(self):
        room = Room()
        net = room.clients[0].net
        net._open = Mock(side_effect=urllib.error.HTTPError(net.base, 429, "quota", {},
                         io.BytesIO(b'{"code":42908}')))
        net.send("test")
        net._send_once()
        for _ in range(10):
            room.clock.advance(5)
            net._send_once()
        self.assertEqual(net._open.call_count, 1)
        self.assertGreater(net.outbox.quota_until, room.clock.wall())

    def test_lost_response_with_self_echo_does_not_publish_again(self):
        room = Room()
        net = room.clients[0].net
        def accepted_but_response_lost(req, timeout):
            room.publish(net, req)
            raise OSError("lost HTTP response")
        net._open = accepted_but_response_lost
        msg = net.send("one")
        net._send_once()
        room.clock.advance(60)
        net._send_once()
        self.assertEqual(len(room.messages), 1)
        self.assertEqual(net.outbox.jobs[msg["id"]].state, "published")
        self.assertEqual(net.outbox.count, 1)

    def test_reconnect_requests_resume_at_last_message_id(self):
        room = Room()
        net = room.clients[0].net
        net.last_id = "cursor123"
        net._server_now = lambda: room.clock.wall()
        urls = []
        class Stream(io.BytesIO):
            def __exit__(self, *args):
                net.stop.set()
                return super().__exit__(*args)
        def read(req, timeout):
            urls.append(req.full_url)
            return Stream(b'')
        net._read_open = read
        net._subscribe()
        self.assertEqual(urls, [net.base + "/test/json?since=cursor123"])

    def test_wire_cannot_forge_local_delivery_status(self):
        room = Room()
        net = room.clients[0].net
        while not net.inbox.empty():
            net.inbox.get_nowait()
        net._handle(json.dumps({"event": "message", "id": "fake",
            "message": json.dumps(packet("fake", type="delivery", state="published"))}))
        self.assertTrue(net.inbox.empty())

    def test_oversized_message_is_rejected_before_publication(self):
        room = Room()
        net = room.clients[0].net
        msg = net.send("", extra={"items": ["x" * 5000]})
        net._send_once()
        self.assertEqual(net.outbox.jobs[msg["id"]].state, "failed")
        self.assertFalse(room.messages)


if __name__ == "__main__":
    unittest.main()
