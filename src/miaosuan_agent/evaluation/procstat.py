"""Non-invasive resource measurement from ``/proc`` (Linux), standard library only.

Host figures come from ``/proc/stat``, ``/proc/loadavg`` and ``/proc/meminfo``. Per-process figures are
read only for processes this tooling started (by PID): CPU time, threads, resident set, context switches,
I/O counters, open file descriptors (with their access mode, and sockets resolved to protocol and
addresses) and the shared libraries mapped. Nothing here reads the memory, environment or command line
of any other process; other activity on the host is visible only as the difference between host CPU
time and the CPU time of our own processes. The parsers are pure functions over text, so they are tested
on any platform.
"""

from __future__ import annotations

import gc
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

GPU_LIBRARY_MARKERS = ("libcuda", "libcudart", "libnvidia", "libcublas", "libcudnn", "libnvrtc")


def clock_ticks() -> int:
    return os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def page_size() -> int:
    return os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def parse_cpu_line(line: str) -> Dict[str, int]:
    """The aggregate ``cpu`` line of ``/proc/stat`` as busy and total clock ticks."""
    fields = [int(x) for x in line.split()[1:]]
    fields += [0] * (10 - len(fields))
    user, nice, system, idle, iowait, irq, softirq, steal = fields[:8]
    busy = user + nice + system + irq + softirq + steal
    return {"busy": busy, "total": busy + idle + iowait, "iowait": iowait}


def parse_proc_stat(text: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for line in text.splitlines():
        if line.startswith("cpu "):
            result.update(parse_cpu_line(line))
        elif line.startswith(("ctxt ", "procs_running ", "procs_blocked ")):
            key, value = line.split()[:2]
            result[key] = int(value)
    return result


def parse_meminfo(text: str) -> Dict[str, int]:
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].rstrip(":") in ("MemTotal", "MemAvailable"):
            values[parts[0].rstrip(":")] = int(parts[1])
    return {"mem_total_kib": values.get("MemTotal", 0), "mem_available_kib": values.get("MemAvailable", 0)}


def parse_pid_stat(text: str) -> Dict[str, Any]:
    """``/proc/<pid>/stat``: the command name may contain spaces or parentheses, so split at the last ')'."""
    head, _, rest = text.rpartition(")")
    fields = rest.split()
    return {"comm": head.partition("(")[2], "state": fields[0], "ppid": int(fields[1]), "pgrp": int(fields[2]),
            "utime": int(fields[11]), "stime": int(fields[12]), "threads": int(fields[17]), "rss_pages": int(fields[21])}


def parse_status(text: str) -> Dict[str, int]:
    keys = {"VmHWM": "vm_hwm_kib", "VmRSS": "vm_rss_kib", "Threads": "threads",
            "voluntary_ctxt_switches": "voluntary_switches", "nonvoluntary_ctxt_switches": "involuntary_switches"}
    result = {}
    for line in text.splitlines():
        name, _, value = line.partition(":")
        if name in keys:
            result[keys[name]] = int(value.split()[0])
    return result


def parse_io(text: str) -> Dict[str, int]:
    result = {}
    for line in text.splitlines():
        name, _, value = line.partition(":")
        if value.strip():
            result[name.strip()] = int(value)
    return result


def access_mode(fdinfo: str) -> str:
    """``r``, ``w`` or ``rw`` from the octal ``flags`` line of ``/proc/<pid>/fdinfo/<fd>``."""
    for line in fdinfo.splitlines():
        if line.startswith("flags:"):
            return {0: "r", 1: "w", 2: "rw"}.get(int(line.split()[1], 8) & 3, "?")
    return "?"


def _hex_address(text: str) -> str:
    address, _, port = text.partition(":")
    port_number = int(port, 16)
    if len(address) == 8:
        octets = [str(int(address[i:i + 2], 16)) for i in range(6, -1, -2)]
        return f"{'.'.join(octets)}:{port_number}"
    return f"[ipv6]:{port_number}"


def parse_inet_sockets(text: str, protocol: str) -> Dict[int, Dict[str, str]]:
    """Inode -> protocol, local and remote address, state, from ``/proc/<pid>/net/{tcp,udp}{,6}``."""
    result = {}
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 10:
            result[int(fields[9])] = {"protocol": protocol, "local": _hex_address(fields[1]),
                                      "remote": _hex_address(fields[2]), "state": fields[3]}
    return result


def parse_unix_sockets(text: str) -> Dict[int, Dict[str, str]]:
    result = {}
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 7:
            result[int(fields[6])] = {"protocol": "unix", "path": fields[7] if len(fields) > 7 else ""}
    return result


def libraries(maps: str) -> List[str]:
    names = set()
    for line in maps.splitlines():
        parts = line.split()
        if len(parts) >= 6 and "/" in parts[5]:
            names.add(parts[5].rsplit("/", 1)[1])
    return sorted(names)


def library_flags(names: Iterable[str]) -> Dict[str, bool]:
    names = list(names)
    return {"gpu": any(n.startswith(GPU_LIBRARY_MARKERS) for n in names),
            "openmp": any(n.startswith(("libgomp", "libiomp", "libomp")) for n in names),
            "openblas": any("openblas" in n for n in names)}


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_host() -> Dict[str, Any]:
    stat = parse_proc_stat(_read(Path("/proc/stat")) or "")
    load = (_read(Path("/proc/loadavg")) or "0 0 0").split()
    return {**stat, **parse_meminfo(_read(Path("/proc/meminfo")) or ""),
            "load1": float(load[0]), "load5": float(load[1]), "load15": float(load[2])}


def read_process(pid: int) -> Optional[Dict[str, Any]]:
    base = Path("/proc") / str(pid)
    stat = _read(base / "stat")
    if stat is None:
        return None
    result = parse_pid_stat(stat)
    result.update(parse_status(_read(base / "status") or ""))
    io = _read(base / "io")
    if io is not None:
        result["io"] = parse_io(io)
    return result


def thread_cpu(pid: int) -> List[Dict[str, Any]]:
    """CPU seconds of every thread of ``pid``."""
    ticks = clock_ticks()
    threads = []
    for task in sorted((Path("/proc") / str(pid) / "task").glob("*"), key=lambda p: int(p.name)):
        text = _read(task / "stat")
        if text:
            parsed = parse_pid_stat(text)
            threads.append({"tid": int(task.name), "comm": parsed["comm"],
                            "cpu_seconds": (parsed["utime"] + parsed["stime"]) / ticks})
    return threads


def descriptors(pid: int) -> Dict[str, Any]:
    """Open descriptors of ``pid``: files with access mode, sockets resolved, pipes and others counted."""
    base = Path("/proc") / str(pid)
    files, socket_inodes, counts = [], [], {"file": 0, "socket": 0, "pipe": 0, "other": 0}
    try:
        entries = sorted(os.listdir(base / "fd"), key=int)
    except OSError:
        return {"readable": False}
    for fd in entries:
        try:
            target = os.readlink(base / "fd" / fd)
        except OSError:
            continue
        if target.startswith("socket:["):
            counts["socket"] += 1
            socket_inodes.append(int(target[8:-1]))
        elif target.startswith("pipe:["):
            counts["pipe"] += 1
        elif target.startswith("/"):
            counts["file"] += 1
            files.append({"path": target, "mode": access_mode(_read(base / "fdinfo" / fd) or "")})
        else:
            counts["other"] += 1
    sockets = []
    if socket_inodes:
        table: Dict[int, Dict[str, str]] = {}
        for name in ("tcp", "tcp6", "udp", "udp6"):
            table.update(parse_inet_sockets(_read(base / "net" / name) or "", name))
        table.update(parse_unix_sockets(_read(base / "net" / "unix") or ""))
        sockets = [table.get(inode, {"protocol": "unresolved"}) for inode in socket_inodes]
    return {"readable": True, "counts": counts, "files": files, "sockets": sockets}


def mapped_libraries(pid: int) -> List[str]:
    return libraries(_read(Path("/proc") / str(pid) / "maps") or "")


def gpu_query() -> Optional[Dict[str, Any]]:
    """Per-GPU utilisation and memory, and the PIDs of compute processes, from ``nvidia-smi`` if present."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        gpus = subprocess.run(["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used",
                               "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=20).stdout
        apps = subprocess.run(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in gpus.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 3 and parts[0].isdigit():
            rows.append({"index": int(parts[0]), "utilization": float(parts[1]), "memory_mib": float(parts[2])})
    pids = {int(p) for p in apps.split() if p.strip().isdigit()}
    return {"gpus": rows, "compute_pids": pids}


def self_report() -> Dict[str, Any]:
    """What a game process reports about itself at the end: threads, peak memory, I/O, GC counts, libraries."""
    pid = os.getpid()
    process = read_process(pid) or {}
    libs = mapped_libraries(pid)
    return {"threads": thread_cpu(pid), "vm_hwm_kib": process.get("vm_hwm_kib"), "io": process.get("io"),
            "gc": [dict(generation) for generation in gc.get_stats()], "libraries": library_flags(libs),
            "descriptors": descriptors(pid)}


def summarize_samples(samples: Sequence[Mapping[str, Any]], allowed_writable: Callable[[str], bool]) -> Dict[str, Any]:
    """Reduce a sampler's lines: host and our CPU, load, memory, threads, descriptors, libraries, GPU.

    Our CPU in an interval is the growth of our processes' CPU ticks between consecutive host samples; a game
    that exits inside an interval loses that interval's last ticks, so per-game CPU totals come from wait4.
    """
    meta = next((s for s in samples if s.get("kind") == "meta"), {"clock_ticks": 100, "page_size": 4096,
                                                                   "logical_cpus": 1})
    ticks, page, logical = meta["clock_ticks"], meta["page_size"], meta["logical_cpus"]
    hosts = [s for s in samples if s.get("kind") == "host"]
    processes = [s for s in samples if s.get("kind") == "process"]
    by_time: Dict[float, List[Mapping[str, Any]]] = {}
    for s in processes:
        by_time.setdefault(s["t"], []).append(s)
    last_ticks: Dict[str, int] = {}
    intervals = []
    for a, b in zip(hosts, hosts[1:]):
        span = b["total"] - a["total"]
        if span <= 0:
            continue
        busy = logical * (b["busy"] - a["busy"]) / span
        ours = 0
        for s in by_time.get(b["t"], []):
            now = s["utime"] + s["stime"]
            ours += now - last_ticks.get(s["game"], 0)
            last_ticks[s["game"]] = now
        seconds = b["t"] - a["t"]
        ours_cpus = ours / ticks / seconds if seconds > 0 else 0.0
        intervals.append({"busy": busy, "ours": ours_cpus, "others": max(0.0, busy - ours_cpus), "seconds": seconds,
                          "ctxt": b.get("ctxt", 0) - a.get("ctxt", 0)})
    total_seconds = sum(i["seconds"] for i in intervals) or 1.0

    def weighted(key: str) -> float:
        return sum(i[key] * i["seconds"] for i in intervals) / total_seconds

    rss_by_time = [sum(s["rss_pages"] for s in group) * page / 1024 for group in by_time.values()]
    unexpected_files, inet_sockets, unix_sockets = set(), 0, 0
    for s in (x for x in samples if x.get("kind") == "descriptors" and x.get("readable")):
        for f in s["files"]:
            if f["mode"] in ("w", "rw") and not allowed_writable(f["path"]):
                unexpected_files.add(f["path"])
        for sock in s["sockets"]:
            if sock.get("protocol", "").startswith(("tcp", "udp")):
                inet_sockets += 1
            elif sock.get("protocol") == "unix":
                unix_sockets += 1
    libs = [s for s in samples if s.get("kind") == "libraries"]
    gpus = [s for s in samples if s.get("kind") == "gpu"]
    gpu_peak: Dict[int, float] = {}
    for s in gpus:
        for g in s["gpus"]:
            gpu_peak[g["index"]] = max(gpu_peak.get(g["index"], 0.0), g["utilization"])
    return {
        "seconds": total_seconds,
        "host_busy_cpus_mean": weighted("busy") if intervals else None,
        "host_busy_fraction_mean": weighted("busy") / logical if intervals else None,
        "our_cpus_sampled_mean": weighted("ours") if intervals else None,
        "others_cpus_mean": weighted("others") if intervals else None,
        "others_cpus_max": max((i["others"] for i in intervals), default=None),
        "context_switches_per_second": (sum(i["ctxt"] for i in intervals) / total_seconds) if intervals else None,
        "load1_max": max((h["load1"] for h in hosts), default=None),
        "procs_running_mean": (sum(h.get("procs_running", 0) for h in hosts) / len(hosts)) if hosts else None,
        "procs_running_max": max((h.get("procs_running", 0) for h in hosts), default=None),
        "mem_available_kib_min": min((h["mem_available_kib"] for h in hosts), default=None),
        "mem_total_kib": hosts[0]["mem_total_kib"] if hosts else None,
        "peak_total_rss_kib": max(rss_by_time, default=0.0),
        "threads_per_process_max": max((s["threads"] for s in processes), default=None),
        "concurrent_processes_max": max((len(g) for g in by_time.values()), default=0),
        "unexpected_writable_files": sorted(unexpected_files),
        "inet_socket_observations": inet_sockets,
        "unix_socket_observations": unix_sockets,
        "descriptor_snapshots": sum(1 for x in samples if x.get("kind") == "descriptors"),
        "libraries": {key: any(s[key] for s in libs) for key in ("gpu", "openmp", "openblas")},
        "processes_with_libraries": len(libs),
        "gpu_samples": len(gpus),
        "gpu_peak_utilization": {str(k): v for k, v in sorted(gpu_peak.items())},
        "ours_on_gpu": any(s["ours_on_gpu"] for s in gpus),
    }


class Sampler(threading.Thread):
    """Append host and per-game samples to a JSON-lines file until :meth:`stop`.

    ``running`` returns the games to sample, as game id -> PID. Every ``interval`` seconds a host sample
    and one sample per running game are written; descriptors every ``descriptor_every`` samples (and once
    per new game), libraries once per game, and GPU figures every ``gpu_every`` samples, reduced to the
    utilisation per GPU and whether any of our PIDs is a GPU compute process.
    """

    def __init__(self, path: Path, running: Callable[[], Mapping[str, int]], interval: float = 1.0,
                 descriptor_every: int = 5, gpu_every: int = 10) -> None:
        super().__init__(daemon=True)
        self.path, self.running, self.interval = Path(path), running, interval
        self.descriptor_every, self.gpu_every = descriptor_every, gpu_every
        self._halt = threading.Event()
        self._seen: set = set()

    def stop(self) -> None:
        self._halt.set()
        self.join()

    def _write(self, handle: Any, payload: Mapping[str, Any]) -> None:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def run(self) -> None:
        t0 = time.monotonic()
        ticks = clock_ticks()
        with open(self.path, "x", encoding="utf-8") as handle:
            self._write(handle, {"kind": "meta", "clock_ticks": ticks, "page_size": page_size(),
                                 "logical_cpus": os.cpu_count()})
            count = 0
            while not self._halt.is_set():
                t = time.monotonic() - t0
                self._write(handle, {"kind": "host", "t": t, **read_host()})
                running = dict(self.running())
                for game, pid in running.items():
                    sample = read_process(pid)
                    if sample is None:
                        continue
                    self._write(handle, {"kind": "process", "t": t, "game": game, **sample})
                    if game not in self._seen or count % self.descriptor_every == 0:
                        self._write(handle, {"kind": "descriptors", "t": t, "game": game, **descriptors(pid)})
                    if game not in self._seen:
                        self._write(handle, {"kind": "libraries", "t": t, "game": game,
                                             **library_flags(mapped_libraries(pid))})
                        self._seen.add(game)
                if count % self.gpu_every == 0:
                    query = gpu_query()
                    if query is not None:
                        ours = set(running.values())
                        self._write(handle, {"kind": "gpu", "t": t, "gpus": query["gpus"],
                                             "ours_on_gpu": bool(ours & query["compute_pids"])})
                handle.flush()
                count += 1
                self._halt.wait(self.interval)
            self._write(handle, {"kind": "host", "t": time.monotonic() - t0, **read_host()})
