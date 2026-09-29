"""Read-only checks of the persistent engine installation on this machine.

The installation lives under the git-ignored ``local/engines/`` tree and exists only on machines
that hold the SDK. Without it every test here is skipped. Nothing here imports the engine or
writes to the installation.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from miaosuan_agent import engine_install as ei
from miaosuan_agent import sdk_provenance as prov

REPO = Path(__file__).resolve().parents[1]
INSTALL = ei.EngineInstall(REPO / "local" / "engines" / f"sdk-{prov.ENGINE_VERSION}")


def setUpModule() -> None:
    if not INSTALL.manifest_path.is_file():
        raise unittest.SkipTest(f"no persistent engine installation at {INSTALL.root.relative_to(REPO).as_posix()} "
                                "(git-ignored; created once on a machine holding the SDK)")


class RealInstallTest(unittest.TestCase):
    def test_provenance(self) -> None:
        manifest = ei.load_manifest(INSTALL)
        self.assertEqual(manifest["engine"]["version"], prov.ENGINE_VERSION)
        self.assertEqual(manifest["source"]["wheel_sha256"], prov.NESTED_ARCHIVES[prov.ENGINE_WHEEL_MEMBER])
        self.assertEqual(manifest["source"]["sdk_archive_sha256"], prov.SDK_ARCHIVE_SHA256)
        self.assertEqual(manifest["state_files"], list(ei.DEFAULT_STATE_FILES))
        self.assertTrue(manifest["python"]["version"].startswith("3.10."))

    def test_integrity_and_continuity(self) -> None:
        report = ei.verify(INSTALL)
        self.assertTrue(report["integrity"]["ok"], report["integrity"])
        self.assertTrue(report["state_continuous"])
        self.assertFalse(report["unclosed_session"])

    def test_ledger_chain_was_never_reset(self) -> None:
        manifest = ei.load_manifest(INSTALL)
        ledger = ei.read_ledger(INSTALL)
        self.assertTrue(ledger, "the installation has never been used")
        expected = manifest["state_at_install"]
        opened = 0
        for record in ledger:
            if record["event"] == "session-open":
                opened += 1
                self.assertEqual(record["kind"], "first-use" if opened == 1 else "reuse")
                self.assertEqual(record["state"], expected, f"state changed before session {record['session']}")
            elif record["event"] in ("session-close", "session-recovered"):
                expected = record["state"]
            else:
                self.fail(f"unknown ledger event {record['event']!r}")
        self.assertEqual(sum(1 for r in ledger if r["event"] == "session-open"), opened)


if __name__ == "__main__":
    unittest.main()
