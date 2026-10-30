"""
Unit tests for IPC socket communication between player instances.
"""

import unittest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from core.ipc import IPCServer, IPCClient


class TestJonakiIPC(unittest.TestCase):
    def test_ipc_roundtrip(self):
        sock_path = f"/tmp/test_jonaki_ipc_{os.getpid()}.sock"

        received_command = []

        def handler(msg):
            received_command.append(msg)
            return {"status": "ok", "ack": msg.get("action")}

        server = IPCServer(handler, socket_path=sock_path)
        self.assertTrue(server.start())
        self.addCleanup(server.stop)

        client = IPCClient(socket_path=sock_path)
        self.assertTrue(client.is_server_running())

        res = client.send_command({"action": "open", "file": "test.mkv"})
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("ack"), "open")
        self.assertEqual(len(received_command), 1)

        server.stop()
        self.assertFalse(client.is_server_running())

    def test_ipc_large_payload(self):
        sock_path = f"/tmp/test_jonaki_ipc_large_{os.getpid()}.sock"
        large_list = [f"/path/to/media/item_{i:05d}_long_title_with_extra_metadata_description.mkv" for i in range(2000)]
        received_data = []

        def handler(msg):
            received_data.append(msg)
            return {"status": "ok", "count": len(msg.get("items", []))}

        server = IPCServer(handler, socket_path=sock_path)
        self.assertTrue(server.start())
        self.addCleanup(server.stop)

        client = IPCClient(socket_path=sock_path)
        res = client.send_command({"action": "add_all", "items": large_list})
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("count"), 2000)
        self.assertEqual(len(received_data), 1)
        self.assertEqual(len(received_data[0]["items"]), 2000)

    def test_ipc_malformed_json_handling(self):
        import socket
        import json
        from core.ipc import _send_msg, _recv_msg

        sock_path = f"/tmp/test_jonaki_ipc_malformed_{os.getpid()}.sock"
        server = IPCServer(lambda msg: {"status": "ok"}, socket_path=sock_path)
        self.assertTrue(server.start())
        self.addCleanup(server.stop)

        # Send invalid JSON with valid 4-byte length prefix
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(sock_path)
            _send_msg(s, b"{not_valid_json: true,")
            resp_data = _recv_msg(s)
            self.assertIsNotNone(resp_data)
            resp = json.loads(resp_data.decode("utf-8"))
            self.assertEqual(resp.get("status"), "error")

        # Verify server survives and handles subsequent valid commands
        client = IPCClient(socket_path=sock_path)
        res = client.send_command({"action": "ping"})
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")

    def test_ipc_open_command_with_add_mode_and_extended_options(self):
        sock_path = f"/tmp/test_jonaki_ipc_opts_{os.getpid()}.sock"
        received = []

        def handler(msg):
            received.append(msg)
            return {"status": "ok"}

        server = IPCServer(handler, socket_path=sock_path)
        self.assertTrue(server.start())
        self.addCleanup(server.stop)

        client = IPCClient(socket_path=sock_path)
        payload = {
            "command": "open",
            "items": ["/media/video2.mp4"],
            "seek": 120.0,
            "add": True,
            "sub": "/media/video2.srt",
            "aud": None,
            "volume": 85.0,
            "title": "Episode 2",
            "config": "Default"
        }
        res = client.send_command(payload)
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(len(received), 1)
        msg = received[0]
        self.assertEqual(msg.get("volume"), 85.0)
        self.assertEqual(msg.get("title"), "Episode 2")
        self.assertTrue(msg.get("add"))
        self.assertEqual(msg.get("seek"), 120.0)


if __name__ == "__main__":
    unittest.main()
