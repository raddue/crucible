#!/usr/bin/env python3
"""Tests for orchestrator_fleet.py — fleet-file CRUD and identity tracking."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import orchestrator_fleet as of  # noqa: E402

class FleetTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "fleet.json")

    def tearDown(self):
        self._tmp.cleanup()

    def _load(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def pane(self, pane_id="w9:p1", terminal_id="term-1", session=None):
        return {
            "pane_id": pane_id, "terminal_id": terminal_id, "workspace_id": "w9",
            "tab_id": "w9:t1", "revision": 7, "agent_session": session,
        }

    def agent(self, session_value="session-1", name="w1", pane_id="w9:p1", session=None):
        return {
            "name": name, "pane_id": pane_id, "workspace_id": "w9", "tab_id": "w9:t1",
            "agent_session": session or {
                "agent": "pi", "kind": "id", "source": "herdr:pi", "value": session_value,
            }, "agent_status": "idle", "cwd": "/tmp/wt",
        }

    def receipt(self, request_id, result):
        path = os.path.join(self._tmp.name, "receipt.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"id": request_id, "result": result}, f)
        return path

    def creation_receipt(self, pane=None, command="cli:pane:split"):
        return self.receipt(command, {"type": "pane_info", "pane": pane or self.pane()})

    def register(self, name="w1", pane=None, status="dispatched", **fields):
        pane = pane or self.pane()
        receipt = self.creation_receipt(pane)
        with patch.object(of, "live_pane", return_value=pane):
            args = ["register", name, "--receipt-file", receipt, "--status", status, "-p", self.path]
            for key, value in fields.items():
                args.extend(["--" + key.replace("_", "-"), str(value)])
            return of.main(args)

    def test_init_creates_skeleton_and_refuses_existing(self):
        self.assertEqual(of.main(["init", "-p", self.path]), 0)
        doc = self._load()
        self.assertEqual(doc["workers"], [])
        self.assertEqual(doc["orchestrator"]["name"], "orchestrator")
        self.assertEqual(of.main(["init", "-p", self.path]), 1)

    def test_register_takes_identity_from_creation_receipt(self):
        of.main(["init", "-p", self.path])
        pane = self.pane()
        receipt = self.creation_receipt(pane)
        with patch.object(of, "live_pane", return_value=pane):
            self.assertEqual(of.main(["register", "w1", "--receipt-file", receipt, "--worktree", "/tmp/wt", "-p", self.path]), 0)
        worker = self._load()["workers"][0]
        self.assertEqual(worker["pane_identity"]["terminal_id"], "term-1")
        self.assertEqual(worker["pane_identity"]["created_revision"], 7)
        self.assertEqual(worker["pane_id"], "w9:p1")

    def test_register_refuses_live_pane_mismatch_and_old_open_worktree(self):
        of.main(["init", "-p", self.path])
        receipt = self.creation_receipt(self.pane(terminal_id="old"))
        with patch.object(of, "live_pane", return_value=self.pane(terminal_id="replacement")):
            self.assertEqual(of.main(["register", "w1", "--receipt-file", receipt, "-p", self.path]), 1)
        opened = self.receipt("cli:worktree:open", {
            "type": "worktree_opened", "already_open": True, "root_pane": self.pane(),
        })
        self.assertEqual(of.main(["register", "w1", "--receipt-file", opened, "-p", self.path]), 1)
        self.assertEqual(self._load()["workers"], [])

    def test_registration_rotation_preserves_old_identity(self):
        of.main(["init", "-p", self.path])
        self.register(status="done")
        self.register(pane=self.pane("w9:p2", "term-2"))
        worker = self._load()["workers"][0]
        self.assertEqual(worker["pane_history"][0]["terminal_id"], "term-1")
        self.assertEqual(worker["pane_history"][0]["cleanup"], "pending")
        self.assertEqual(worker["pane_identity"]["terminal_id"], "term-2")

    def test_bind_records_agent_session_only_after_receipts_and_live_match(self):
        of.main(["init", "-p", self.path])
        self.register()
        agent = self.agent()
        start = self.receipt("cli:agent:start", {"type": "agent_started", "agent": agent, "argv": []})
        with patch.object(of, "live_pane", return_value=self.pane(session=agent["agent_session"])), \
             patch.object(of, "live_agents", return_value=[agent]):
            self.assertEqual(of.main(["bind", "w1", "--receipt-file", start, "-p", self.path]), 0)
        identity = self._load()["workers"][0]["pane_identity"]
        self.assertEqual(identity["agent_name"], "w1")
        self.assertEqual(identity["agent_session"], agent["agent_session"])

    def test_bind_refuses_replaced_agent_or_terminal(self):
        of.main(["init", "-p", self.path])
        self.register()
        agent = self.agent(session_value="replacement")
        start = self.receipt("cli:agent:start", {"type": "agent_started", "agent": agent, "argv": []})
        with patch.object(of, "live_pane", return_value=self.pane("w9:p1", "different-terminal", agent["agent_session"])), \
             patch.object(of, "live_agents", return_value=[agent]):
            self.assertEqual(of.main(["bind", "w1", "--receipt-file", start, "-p", self.path]), 1)
        identity = self._load()["workers"][0]["pane_identity"]
        self.assertNotIn("agent_session", identity)

    def test_reconcile_requires_exact_pane_and_agent_session(self):
        of.main(["init", "-p", self.path])
        self.register()
        agent = self.agent()
        start = self.receipt("cli:agent:start", {"type": "agent_started", "agent": agent, "argv": []})
        with patch.object(of, "live_pane", return_value=self.pane(session=agent["agent_session"])), \
             patch.object(of, "live_agents", return_value=[agent]):
            self.assertEqual(of.main(["bind", "w1", "--receipt-file", start, "-p", self.path]), 0)
        worker = self._load()["workers"][0]
        matched, stale = of.reconcile({"workers": [worker]}, [agent], lambda _pane_id: self.pane(session=agent["agent_session"]))
        self.assertEqual([row[0] for row in matched], ["w1"])
        self.assertEqual(stale, [])

        replaced = dict(agent, agent_session=dict(agent["agent_session"], value="other-session"))
        matched, stale = of.reconcile({"workers": [worker]}, [replaced], lambda _pane_id: self.pane(session=replaced["agent_session"]))
        self.assertEqual(matched, [])
        self.assertEqual(stale[0]["_identity_error"], "no matching recorded pane/agent identity")

    def test_remove_archives_identity_and_refuses_active_worker(self):
        of.main(["init", "-p", self.path])
        self.register(status="working")
        self.assertEqual(of.main(["remove", "w1", "-p", self.path]), 1)
        of.main(["status", "w1", "--status", "done", "-p", self.path])
        self.assertEqual(of.main(["remove", "w1", "-p", self.path]), 0)
        doc = self._load()
        self.assertEqual(doc["workers"], [])
        self.assertEqual(doc["archived_workers"][0]["pane_identity"]["terminal_id"], "term-1")

    def test_bad_targets_and_dependency_graph(self):
        of.main(["init", "-p", self.path])
        self.assertEqual(of.main(["status", "ghost", "--status", "x", "-p", self.path]), 1)
        self.register("a", self.pane("p1", "term-a"), status="done")
        self.register("b", self.pane("p2", "term-b"), status="idle", depends_on="a")
        doc = self._load()
        self.assertEqual(doc["workers"][1]["depends_on"], ["a"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(of.main(["ready", "-p", self.path]), 0)
        self.assertIn("b", buf.getvalue().splitlines()[0])

    def test_queue_next_requires_creation_receipt_and_only_pops_after_register(self):
        of.main(["init", "-p", self.path])
        of.main(["queue", "push", "--issue", "563", "--task", "fix auth", "-p", self.path])
        receipt = self.creation_receipt(self.pane("w9:p2", "term-2"))
        with patch.object(of, "live_pane", return_value=self.pane("w9:p2", "term-2")):
            self.assertEqual(of.main(["queue", "next", "w1", "--receipt-file", receipt, "-p", self.path]), 0)
        doc = self._load()
        self.assertEqual(doc["backlog"], [])
        self.assertEqual(doc["workers"][0]["pane_identity"]["terminal_id"], "term-2")
        self.assertEqual(doc["workers"][0]["issue"], 563)

    def test_meta_and_log_roundtrip(self):
        of.main(["init", "-p", self.path])
        of.main(["meta", "arc", "closed", "-p", self.path])
        of.main(["meta", "orchestrator.me", "w3:p1", "-p", self.path])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(of.main(["log", "--event", "dispatch", "--next", "await result", "-p", self.path]), 0)
        doc = self._load()
        self.assertEqual(doc["arc"], "closed")
        self.assertEqual(doc["orchestrator"]["me"], "w3:p1")
        self.assertEqual(doc["pending"], "await result")

    def test_skill_is_not_shipped(self):
        self.assertFalse(os.path.exists(os.path.join(REPO_ROOT, "skills", "orchestrator")))

if __name__ == "__main__":
    unittest.main()
