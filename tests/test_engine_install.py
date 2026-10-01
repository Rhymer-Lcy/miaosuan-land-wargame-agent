"""Guardrails of the persistent engine installation, exercised on a synthetic package.

No real wheel is installed and no real engine state file is involved: a fake installer writes a
small package whose state file has a synthetic name.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from miaosuan_agent import engine_install as ei

STATE = "pkg/state/.synthetic_state"


def fake_installer(wheel: Path, target: Path) -> dict:
    (target / "pkg" / "state").mkdir(parents=True)
    (target / "pkg" / "module.so").write_bytes(b"synthetic module")
    (target / STATE).write_bytes(b"")
    return {"command": ["fake-installer", str(wheel)], "pip_version": "none"}


class InstallTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.wheel = self.tmp / "engine-0.0.0-py3-none-any.whl"
        self.wheel.write_bytes(b"synthetic wheel")
        self.sha = hashlib.sha256(b"synthetic wheel").hexdigest()
        self.install = ei.EngineInstall(self.tmp / "engines" / "sdk-0.0.0")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def create(self) -> dict:
        return ei.create_install(self.install.root, self.wheel, wheel_sha256=self.sha, engine_version="0.0.0",
                                 state_files=(STATE,), installer=fake_installer)

    def engine_writes_state(self, data: bytes) -> None:
        (self.install.site / STATE).write_bytes(data)


class CreateInstallTest(InstallTestCase):
    def test_manifest_records_provenance_and_the_pre_import_tree(self) -> None:
        manifest = self.create()
        self.assertEqual(manifest["source"]["wheel_sha256"], self.sha)
        self.assertEqual(manifest["state_at_install"], {STATE: hashlib.sha256(b"").hexdigest()})
        self.assertEqual(manifest["tree_before_first_import"]["file_count"], 2)
        self.assertTrue(self.install.home.is_dir())
        self.assertFalse(os.access(self.install.manifest_path, os.W_OK))
        self.assertEqual(ei.load_manifest(self.install)["schema"], ei.SCHEMA)

    def test_existing_destination_is_refused(self) -> None:
        self.create()
        with self.assertRaises(ei.InstallRefused):
            self.create()
        self.install.root.parent.joinpath("other").mkdir()
        with self.assertRaises(ei.InstallRefused):
            ei.create_install(self.install.root.parent / "other", self.wheel, wheel_sha256=self.sha,
                              engine_version="0.0.0", state_files=(STATE,), installer=fake_installer)

    def test_wrong_wheel_digest_creates_nothing(self) -> None:
        with self.assertRaises(ei.InstallError):
            ei.create_install(self.install.root, self.wheel, wheel_sha256="0" * 64, engine_version="0.0.0",
                              state_files=(STATE,), installer=fake_installer)
        self.assertFalse(self.install.root.exists())


class SessionLedgerTest(InstallTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.create()

    def test_first_use_then_reuse_with_state_continuity(self) -> None:
        first = ei.open_session(self.install, "smoke", {"commit": "abc"})
        self.assertEqual((first["session"], first["kind"]), ("0001", "first-use"))
        self.engine_writes_state(b"written by the engine")
        closed = ei.close_session(self.install, first, {"status": "PASS"})
        self.assertTrue(closed["state_changed"])
        second = ei.open_session(self.install, "capture", {"commit": "abc"})
        self.assertEqual((second["session"], second["kind"]), ("0002", "reuse"))
        ei.close_session(self.install, second, {"status": "PASS"})
        events = [record["event"] for record in ei.read_ledger(self.install)]
        self.assertEqual(events, ["session-open", "session-close", "session-open", "session-close"])

    def test_state_change_outside_a_session_is_refused(self) -> None:
        opened = ei.open_session(self.install, "smoke", {})
        ei.close_session(self.install, opened, {"status": "PASS"})
        self.engine_writes_state(b"changed between sessions")
        before = ei.read_ledger(self.install)
        with self.assertRaises(ei.InstallRefused):
            ei.open_session(self.install, "smoke", {})
        self.assertEqual(ei.read_ledger(self.install), before)

    def test_state_change_before_first_use_is_refused(self) -> None:
        self.engine_writes_state(b"not the installed state")
        with self.assertRaises(ei.InstallRefused):
            ei.open_session(self.install, "smoke", {})

    def test_changed_or_missing_package_files_are_refused(self) -> None:
        (self.install.site / "pkg" / "module.so").write_bytes(b"tampered")
        with self.assertRaises(ei.InstallRefused):
            ei.open_session(self.install, "smoke", {})
        (self.install.site / "pkg" / "module.so").unlink()
        with self.assertRaises(ei.InstallRefused):
            ei.open_session(self.install, "smoke", {})

    def test_added_files_are_reported_not_refused(self) -> None:
        (self.install.site / "pkg" / "cache.bin").write_bytes(b"new")
        opened = ei.open_session(self.install, "smoke", {})
        self.assertEqual(opened["integrity"]["added"], ["pkg/cache.bin"])

    def test_unclosed_session_is_recovered_with_state_as_found(self) -> None:
        ei.open_session(self.install, "smoke", {})
        self.engine_writes_state(b"written before the process was killed")
        reopened = ei.open_session(self.install, "smoke", {})
        events = [record["event"] for record in ei.read_ledger(self.install)]
        self.assertEqual(events, ["session-open", "session-recovered", "session-open"])
        self.assertEqual(reopened["kind"], "reuse")

    def test_verify_is_read_only(self) -> None:
        opened = ei.open_session(self.install, "smoke", {})
        report = ei.verify(self.install)
        self.assertTrue(report["unclosed_session"])
        ei.close_session(self.install, opened, {"status": "PASS"})
        ledger = ei.read_ledger(self.install)
        report = ei.verify(self.install)
        self.assertEqual(ei.read_ledger(self.install), ledger)
        self.assertTrue(report["integrity"]["ok"] and report["state_continuous"])
        self.assertEqual((report["sessions_opened"], report["first_use_session"]), (1, "0001"))
        self.engine_writes_state(b"outside")
        self.assertFalse(ei.verify(self.install)["state_continuous"])


@unittest.skipUnless(importlib.util.find_spec("fcntl"), "sessions use POSIX file locking (fcntl)")
class SessionContextTest(InstallTestCase):
    def test_context_manager_closes_and_records_the_outcome(self) -> None:
        self.create()
        with ei.session(self.install, "smoke", {}) as handle:
            handle.outcome = {"status": "PASS"}
        self.assertEqual(handle.closed["outcome"], {"status": "PASS"})

    def test_exception_is_recorded_and_reraised(self) -> None:
        self.create()
        with self.assertRaises(RuntimeError):
            with ei.session(self.install, "smoke", {}):
                raise RuntimeError("engine crashed")
        close = ei.read_ledger(self.install)[-1]
        self.assertEqual(close["outcome"]["status"], "INTERRUPTED")
        self.assertIn("engine crashed", close["outcome"]["exception"])


def _shared_worker(root: str, worker: int, count: int) -> None:
    install = ei.EngineInstall(Path(root))
    for k in range(count):
        with ei.shared_session(install, "diagnostic", {"game_id": f"w{worker}.g{k}"}, str(worker)) as handle:
            handle.outcome = {"status": "COMPLETED", "game_id": f"w{worker}.g{k}"}


@unittest.skipUnless(importlib.util.find_spec("fcntl"), "sessions use POSIX file locking (fcntl)")
class SharedSessionTest(InstallTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.create()
        with ei.session(self.install, "smoke", {}) as handle:
            handle.outcome = {"status": "PASS"}

    def test_shared_sessions_overlap_and_number_consecutively(self) -> None:
        with ei.shared_session(self.install, "diagnostic", {"game_id": "a"}, "0") as a:
            with ei.shared_session(self.install, "diagnostic", {"game_id": "b"}, "1") as b:
                self.assertEqual((a.opened["session"], b.opened["session"]), ("0002", "0003"))
                self.assertEqual(ei.verify(self.install)["unclosed_sessions"], ["0002", "0003"])
        events = [(r["event"], r["session"]) for r in ei.read_ledger(self.install)[2:]]
        self.assertEqual(events, [("session-open", "0002"), ("session-open", "0003"),
                                  ("session-close", "0003"), ("session-close", "0002")])
        report = ei.verify(self.install)
        self.assertEqual((report["unclosed_sessions"], report["unclosed_session"], report["shared_sessions"]),
                         ([], False, 2))
        self.assertEqual(a.closed["concurrency"], {"mode": "shared", "worker": "0"})

    def test_exclusive_and_shared_exclude_each_other(self) -> None:
        with ei.shared_session(self.install, "diagnostic", {}, "0"):
            with self.assertRaises(ei.InstallRefused):
                with ei.session(self.install, "smoke", {}):
                    pass
            with self.assertRaises(ei.InstallRefused):
                with ei.exclusive_window(self.install):
                    pass
        with ei.session(self.install, "smoke", {}):
            with self.assertRaises(ei.InstallRefused):
                with ei.shared_session(self.install, "diagnostic", {}, "0"):
                    pass
        self.assertEqual(ei.unclosed_sessions(ei.read_ledger(self.install)), [])

    def test_first_use_is_never_shared(self) -> None:
        other = ei.EngineInstall(self.tmp / "engines" / "other")
        ei.create_install(other.root, self.wheel, wheel_sha256=self.sha, engine_version="0.0.0", state_files=(STATE,),
                          installer=fake_installer)
        with self.assertRaises(ei.InstallRefused):
            with ei.shared_session(other, "diagnostic", {}, "0"):
                pass
        self.assertEqual(ei.read_ledger(other), [])

    def test_state_change_outside_a_session_refuses_a_shared_session(self) -> None:
        self.engine_writes_state(b"outside any session")
        with self.assertRaises(ei.InstallRefused):
            with ei.shared_session(self.install, "diagnostic", {}, "0"):
                pass

    def test_concurrent_processes_get_unique_consecutive_numbers(self) -> None:
        import multiprocessing
        context = multiprocessing.get_context("fork")
        workers = [context.Process(target=_shared_worker, args=(str(self.install.root), w, 6)) for w in range(8)]
        for process in workers:
            process.start()
        for process in workers:
            process.join(60)
            self.assertEqual(process.exitcode, 0)
        ledger = ei.read_ledger(self.install)
        opens = [r["session"] for r in ledger if r["event"] == "session-open"]
        closes = sorted(r["session"] for r in ledger if r["event"] == "session-close")
        self.assertEqual(sorted(opens), [f"{n:04d}" for n in range(1, 50)])
        self.assertEqual(closes, sorted(opens))
        self.assertEqual(ei.unclosed_sessions(ledger), [])
        games = sorted(r["harness"]["game_id"] for r in ledger if r["event"] == "session-open" and "game_id" in r["harness"])
        self.assertEqual(len(games), 48)
        self.assertEqual(len(set(games)), 48)

    def test_killed_shared_sessions_are_recovered_only_exclusively(self) -> None:
        lost = ei.open_shared_session(self.install, "diagnostic", {}, "0")
        with ei.shared_session(self.install, "diagnostic", {}, "1") as live:
            with self.assertRaises(ei.InstallRefused):
                ei.recover_unclosed(self.install)
        self.assertEqual(ei.unclosed_sessions(ei.read_ledger(self.install)), [lost["session"]])
        recovered = ei.recover_unclosed(self.install)
        self.assertEqual([r["session"] for r in recovered], [lost["session"]])
        self.assertEqual(ei.unclosed_sessions(ei.read_ledger(self.install)), [])
        self.assertNotEqual(live.opened["session"], lost["session"])

    def test_exclusive_open_recovers_every_unclosed_session(self) -> None:
        first = ei.open_shared_session(self.install, "diagnostic", {}, "0")
        second = ei.open_shared_session(self.install, "diagnostic", {}, "1")
        opened = ei.open_session(self.install, "smoke", {})
        events = [(r["event"], r["session"]) for r in ei.read_ledger(self.install)[-3:]]
        self.assertEqual(events, [("session-recovered", first["session"]), ("session-recovered", second["session"]),
                                  ("session-open", opened["session"])])


class UnclosedSessionsTest(unittest.TestCase):
    def test_pairs_opens_with_closes_and_recoveries(self) -> None:
        ledger = [{"event": "session-open", "session": "0001"}, {"event": "session-open", "session": "0002"},
                  {"event": "session-close", "session": "0001"}, {"event": "session-open", "session": "0003"},
                  {"event": "session-recovered", "session": "0003"}]
        self.assertEqual(ei.unclosed_sessions(ledger), ["0002"])
        self.assertEqual(ei.unclosed_sessions(ledger[:1]), ["0001"])
        self.assertEqual(ei.unclosed_sessions([]), [])


if __name__ == "__main__":
    unittest.main()
