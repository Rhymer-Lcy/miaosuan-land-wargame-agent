# Shared evaluation server: CPU policy

**Standing operational policy (owner decision, 2026-10-09, Sprint 28). It governs every job this project starts on
the evaluation server: engine games, offline studies, test suites, mutation runs and ad-hoc analyses.**

The evaluation server is shared with one colleague. The policy divides capacity fairly and isolates the two
workloads; it is about capacity, not about keeping CPUs busy. Dates are business dates in UTC+8.

## 1. Verified host topology (2026-10-09)

Read with `lscpu`, `lscpu -e`, `/sys/devices/system/cpu/cpu*/topology/thread_siblings_list`, `taskset -cp`,
`/proc/self/status` and the cgroup files of the login session:

| Item | Value |
|---|---|
| Sockets, physical cores, threads | 2 sockets x 16 physical cores x 2 SMT threads = **32 physical cores, 64 logical CPUs** |
| SMT siblings | logical CPU `i` and `i + 32` are the two threads of one physical core (0 and 32, 1 and 33, ...) |
| NUMA node 0 | logical CPUs 0-15 and 32-47 (socket 0: 16 physical cores with both threads) |
| NUMA node 1 | logical CPUs 16-31 and 48-63 (socket 1: 16 physical cores with both threads) |
| Affinity and cpuset of a login session | 0-63; cgroup v2, and only the memory and pids controllers are enabled below the root, so no CPU quota applies and a job is isolated by its CPU affinity (`taskset`) only |
| Memory | about 487 GiB, of which almost all was page cache or free at the inspection |
| Accounts | both people work under the same Unix account, so a process's user does not tell whose job it is |

"64 cores" in the owner's brief are 64 logical CPUs on 32 physical cores. **A 32-CPU half is one NUMA node: 16
physical cores with both of their SMT threads.** The split 0-31 / 32-63 is wrong: it gives each person one thread
of every physical core, so the two workloads would compete for the same cores, caches and memory controllers.

## 2. The two modes

* **Shared mode** (the colleague is active): each person uses at most one NUMA node. At the inspection on 2026-10-09
  the colleague's running job was pinned to NUMA node 1, so this project's half is **NUMA node 0, logical CPUs 0-15
  and 32-47**. Pin the project's own child processes there with `taskset -c 0-15,32-47 <command>` (or `numactl
  --cpunodebind=0 --membind=0` where available). If the colleague's pinning is ever found on node 0, take node 1
  instead; never overlap.
* **Idle-peer mode** (no job of the colleague's is running): the project's jobs may use more than one node, up to all
  64 logical CPUs, when that is useful. Apparent idleness is re-assessed before each expensive launch; it is not a
  standing permission, and it never licenses interfering with any existing background job.

A task that cannot use 32 CPUs effectively does not take them. A single engine game, a serial test suite or a
lightweight analysis stays as small as it is. Engine worker counts are the ones a registered manifest records
(`docs/CONCURRENCY_QUALIFICATION.md`, `docs/RUNTIME_THREAD_QUALIFICATION.md`); they are never raised to fill idle
CPUs, and the registered courtesy check of those qualifications is unchanged (32 workers is also the largest count
ever qualified, inside one 32-CPU half). A serial or deterministic procedure is not parallelised unless a tested
parallel mode exists, and no parallel run may share mutable inputs or the engine ledger unsafely.

## 3. Before launching expensive server work

1. `lscpu` and `lscpu -e=CPU,CORE,SOCKET,NODE`: the topology above is unchanged.
2. Physical cores against logical CPUs: siblings from `thread_siblings_list`, never assumed.
3. Effective affinity and cpuset of the launching shell: `taskset -cp $$`, `grep Cpus_allowed_list /proc/self/status`,
   and the session cgroup's `cpuset.cpus.effective` and `cpu.max`.
4. Load and pressure: `uptime`, `/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io`, `free -g`.
5. Whether the colleague is active: `ps -eo pid,ppid,pcpu,etimes,args --sort=-pcpu`, then, read-only, the busy
   processes' working directory (`readlink /proc/PID/cwd`) and affinity (`taskset -cp PID`). Jobs outside this
   project's own server folders are the colleague's or another task's.
6. The task's real parallelism (serial, a fixed worker pool, or embarrassingly parallel shards).
7. The worker count and the CPU set, chosen from 1 to 6 and written into the job's launch log.

## 4. Process safety

* Never use `pkill`, `killall` or `pgrep -f` with a pattern: a pattern can match the SSH command or the shell that
  runs it (this project has killed its own sessions that way more than once).
* Terminate only a process this task launched, identified by its exact PID, its parent chain and its command line
  as recorded at launch, and only when termination is necessary. Use the PID, not a name.
* Never terminate, renice, re-pin or move into another cgroup any process of the colleague's, and do not change
  their affinity, priority or cgroups.
* Avoid memory and storage contention: large private outputs stay inside the project's own server folders, and long
  jobs write their progress as they go.

## 5. Recording

Each sprint that uses the server reports, in its document, the topology check, the mode it found (shared or
idle-peer), the CPU set and worker count it chose and why. Colleague-identifying details (names, folders,
environments, command lines) are not written into this repository.
