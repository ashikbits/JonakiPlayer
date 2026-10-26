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

        client = IPCClient(socket_path=sock_path)
        self.assertTrue(client.is_server_running())

        res = client.send_command({"action": "open", "file": "test.mkv"})
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("ack"), "open")
        self.assertEqual(len(received_command), 1)

        server.stop()
        self.assertFalse(client.is_server_running())


if __name__ == "__main__":
    unittest.main()
