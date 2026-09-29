"""Create or verify the persistent SDK engine installation (git-ignored, machine-local).

    install  create the installation once from the verified SDK archive; refuses an existing path
    verify   read-only check of package integrity and state continuity, with a ledger summary

There is deliberately no reinstall, repair or reset command. The engine keeps first-use
authentication state inside its installed package; see docs/ENGINE_INSTALL.md.

Exit status: 0 success; 1 verification found a problem; 3 a guardrail refused the operation.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install, sdk_data  # noqa: E402
from miaosuan_agent import sdk_provenance as prov  # noqa: E402

DEFAULT_ROOT = REPO_ROOT / "local" / "engines" / f"sdk-{prov.ENGINE_VERSION}"


def cmd_install(args: argparse.Namespace) -> int:
    dest: Path = args.dest.resolve()
    if dest.exists():
        raise engine_install.InstallRefused(f"{dest} already exists; the installation is created only once")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".wheel-") as scratch:
        wheel = sdk_data.extract_engine_wheel(args.sdk_archive, Path(scratch))
        manifest = engine_install.create_install(
            dest, wheel,
            wheel_sha256=prov.NESTED_ARCHIVES[prov.ENGINE_WHEEL_MEMBER],
            engine_version=prov.ENGINE_VERSION,
            provenance={"sdk_archive": prov.SDK_ARCHIVE_NAME, "sdk_archive_sha256": prov.SDK_ARCHIVE_SHA256,
                        "wheel_member": prov.ENGINE_WHEEL_MEMBER},
        )
    tree = manifest["tree_before_first_import"]
    print(json.dumps({"installed": str(dest), "engine_version": manifest["engine"]["version"],
                      "wheel_sha256": manifest["source"]["wheel_sha256"], "python": manifest["python"]["version"],
                      "file_count": tree["file_count"], "tree_digest_before_first_import": tree["digest"],
                      "installed_at": manifest["installed_at"]}, indent=1))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    report = engine_install.verify(engine_install.EngineInstall(args.install.resolve()))
    print(json.dumps(report, indent=1))
    return 0 if report["integrity"]["ok"] and report["state_continuous"] and not report["unclosed_session"] else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install", help="create the persistent installation (once)")
    install.add_argument("--sdk-archive", type=Path, required=True)
    install.add_argument("--dest", type=Path, default=DEFAULT_ROOT)
    install.set_defaults(func=cmd_install)
    verify = sub.add_parser("verify", help="read-only integrity and continuity check")
    verify.add_argument("--install", type=Path, default=DEFAULT_ROOT)
    verify.set_defaults(func=cmd_verify)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except engine_install.InstallRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    except (engine_install.InstallError, sdk_data.SdkDataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
