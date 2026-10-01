"""Parsers and the sample reduction of the /proc resource measurement, on synthetic text."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from miaosuan_agent.evaluation import procstat as ps

STAT = """cpu  100 5 50 800 20 3 2 0 0 0
cpu0 50 2 25 400 10 1 1 0 0 0
ctxt 123456
procs_running 3
procs_blocked 0
"""
PID_STAT = ("4242 (python3 (game) x) S 4200 4242 4242 0 -1 4194560 1000 0 0 0 "
            "750 125 0 0 20 0 7 0 12345 1000000 25600 18446744073709551615")
STATUS = """Name:\tpython3
VmHWM:\t  204800 kB
VmRSS:\t  102400 kB
Threads:\t7
voluntary_ctxt_switches:\t150
nonvoluntary_ctxt_switches:\t12
"""
TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000:2328 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 55555 1 0
"""
UNIX = """Num       RefCount Protocol Flags    Type St Inode Path
0000000000000000: 00000002 00000000 00010000 0001 01 777 /run/example.sock
"""
MAPS = """7f00-7f01 r-xp 00000000 08:01 1 /usr/lib/x86_64-linux-gnu/libc.so.6
7f02-7f03 r-xp 00000000 08:01 2 /env/lib/libopenblas64_p-r0.3.23.so
7f04-7f05 rw-p 00000000 00:00 0 [heap]
"""


class ParserTest(unittest.TestCase):
    def test_proc_stat(self) -> None:
        parsed = ps.parse_proc_stat(STAT)
        self.assertEqual(parsed["busy"], 100 + 5 + 50 + 3 + 2 + 0)
        self.assertEqual(parsed["total"], parsed["busy"] + 800 + 20)
        self.assertEqual((parsed["ctxt"], parsed["procs_running"]), (123456, 3))

    def test_pid_stat_survives_parentheses_in_the_name(self) -> None:
        parsed = ps.parse_pid_stat(PID_STAT)
        self.assertEqual(parsed["comm"], "python3 (game) x")
        self.assertEqual((parsed["utime"], parsed["stime"], parsed["threads"], parsed["rss_pages"]), (750, 125, 7, 25600))
        self.assertEqual((parsed["ppid"], parsed["pgrp"]), (4200, 4242))

    def test_status_and_io(self) -> None:
        self.assertEqual(ps.parse_status(STATUS), {"vm_hwm_kib": 204800, "vm_rss_kib": 102400, "threads": 7,
                                                   "voluntary_switches": 150, "involuntary_switches": 12})
        self.assertEqual(ps.parse_io("rchar: 10\nwchar: 20\nwrite_bytes: 4096\n"),
                         {"rchar": 10, "wchar": 20, "write_bytes": 4096})

    def test_access_mode(self) -> None:
        self.assertEqual(ps.access_mode("pos:\t0\nflags:\t0100000\n"), "r")
        self.assertEqual(ps.access_mode("pos:\t0\nflags:\t02102001\n"), "w")
        self.assertEqual(ps.access_mode("flags:\t02\n"), "rw")

    def test_sockets(self) -> None:
        self.assertEqual(ps.parse_inet_sockets(TCP, "tcp")[55555],
                         {"protocol": "tcp", "local": "0.0.0.0:9000", "remote": "0.0.0.0:0", "state": "0A"})
        self.assertEqual(ps.parse_unix_sockets(UNIX)[777], {"protocol": "unix", "path": "/run/example.sock"})

    def test_libraries(self) -> None:
        names = ps.libraries(MAPS)
        self.assertEqual(names, ["libc.so.6", "libopenblas64_p-r0.3.23.so"])
        self.assertEqual(ps.library_flags(names), {"gpu": False, "openmp": False, "openblas": True})
        self.assertTrue(ps.library_flags(["libcuda.so.1"])["gpu"])


SCHED = """python (333791, #threads: 64)
-------------------------------------------------------------------
se.exec_start                                :    5009954965.571913
se.sum_exec_runtime                          :            92.649286
se.nr_migrations                             :                    3
nr_switches                                  :                    6
nr_voluntary_switches                        :                    5
nr_involuntary_switches                      :                    1
se.load.weight                               :              1048576
"""


class SchedulingParserTest(unittest.TestCase):
    def test_sched(self) -> None:
        self.assertEqual(ps.parse_sched(SCHED), {"exec_ms": 92.649286, "migrations": 3.0, "switches": 6.0,
                                                 "voluntary": 5.0, "involuntary": 1.0})

    def test_process_start(self) -> None:
        stat = PID_STAT.replace(" 12345 ", " 50000 ")
        ticks = ps.clock_ticks()
        self.assertAlmostEqual(ps.process_start_seconds(stat, f"{50000 / ticks + 7.5:.2f} 999.0"), 7.5, places=1)


class SummaryTest(unittest.TestCase):
    def samples(self):
        meta = {"kind": "meta", "clock_ticks": 100, "page_size": 4096, "logical_cpus": 4}
        hosts = [{"kind": "host", "t": float(t), "busy": 200 * t, "total": 400 * t, "ctxt": 1000 * t, "load1": 1.0 + t,
                  "procs_running": 2, "mem_total_kib": 1000000, "mem_available_kib": 900000} for t in range(4)]
        processes = []
        for t in range(1, 4):
            for game in ("a", "b"):
                processes.append({"kind": "process", "t": float(t), "game": game, "utime": 80 * t, "stime": 20 * t,
                                  "threads": 3, "rss_pages": 256})
        descriptors = [{"kind": "descriptors", "t": 1.0, "game": "a", "readable": True,
                        "files": [{"path": "/work/games/a.json", "mode": "w"}, {"path": "/elsewhere/x", "mode": "rw"},
                                  {"path": "/lib/data", "mode": "r"}],
                        "sockets": [{"protocol": "unix", "path": ""}]}]
        libs = [{"kind": "libraries", "t": 1.0, "game": "a", "gpu": False, "openmp": False, "openblas": True}]
        gpu = [{"kind": "gpu", "t": 1.0, "gpus": [{"index": 0, "utilization": 35.0, "memory_mib": 10.0}],
                "ours_on_gpu": False}]
        return [meta] + hosts + processes + descriptors + libs + gpu

    def test_cpu_split_between_ours_and_others(self) -> None:
        summary = ps.summarize_samples(self.samples(), lambda p: p.startswith("/work/"))
        self.assertAlmostEqual(summary["host_busy_cpus_mean"], 2.0)
        self.assertAlmostEqual(summary["our_cpus_sampled_mean"], 2.0)
        self.assertAlmostEqual(summary["others_cpus_mean"], 0.0)
        self.assertEqual(summary["peak_total_rss_kib"], 2 * 256 * 4096 / 1024)
        self.assertEqual(summary["concurrent_processes_max"], 2)
        self.assertEqual(summary["total_threads_max"], 6)
        self.assertEqual(summary["unexpected_writable_files"], ["/elsewhere/x"])
        self.assertEqual((summary["inet_socket_observations"], summary["unix_socket_observations"]), (0, 1))
        self.assertEqual(summary["gpu_peak_utilization"], {"0": 35.0})
        self.assertFalse(summary["ours_on_gpu"])
        self.assertTrue(summary["libraries"]["openblas"])

    def test_others_are_host_minus_ours(self) -> None:
        samples = [s for s in self.samples() if not (s.get("kind") == "process" and s["game"] == "b")]
        summary = ps.summarize_samples(samples, lambda p: True)
        self.assertAlmostEqual(summary["others_cpus_mean"], 1.0)


@unittest.skipUnless(sys.platform.startswith("linux"), "reads the Linux /proc filesystem")
class LiveProcTest(unittest.TestCase):
    def test_sampler_and_self_report_on_a_real_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2.5)"])
            path = Path(tmp) / "samples.jsonl"
            sampler = ps.Sampler(path, lambda: {"child": child.pid}, interval=0.5, descriptor_every=2, gpu_every=1000)
            sampler.start()
            child.wait()
            sampler.stop()
            samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        kinds = {s["kind"] for s in samples}
        self.assertTrue({"meta", "host", "process", "descriptors", "libraries"} <= kinds, kinds)
        summary = ps.summarize_samples(samples, lambda p: False)
        self.assertEqual(summary["concurrent_processes_max"], 1)
        self.assertGreater(summary["peak_total_rss_kib"], 0)
        self.assertFalse(summary["libraries"]["gpu"])
        report = ps.self_report()
        self.assertGreaterEqual(len(report["threads"]), 1)
        self.assertEqual(len(report["gc"]), 3)
        self.assertTrue(report["descriptors"]["readable"])


if __name__ == "__main__":
    unittest.main()
