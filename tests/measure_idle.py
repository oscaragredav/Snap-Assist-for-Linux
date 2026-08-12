"""Mide CPU y RSS de un proceso Linux durante un intervalo reproducible."""

import argparse
import os
import time
from pathlib import Path


def process_ticks(pid: int) -> int:
    fields = (Path("/proc") / str(pid) / "stat").read_text().split()
    return int(fields[13]) + int(fields[14])


def process_rss_mb(pid: int) -> float:
    status = (Path("/proc") / str(pid) / "status").read_text().splitlines()
    rss_line = next(line for line in status if line.startswith("VmRSS:"))
    return int(rss_line.split()[1]) / 1024


def measure(pid: int, seconds: float) -> tuple[float, float]:
    ticks_per_second = os.sysconf("SC_CLK_TCK")
    start_ticks = process_ticks(pid)
    start = time.monotonic()
    time.sleep(seconds)
    elapsed = time.monotonic() - start
    used_seconds = (process_ticks(pid) - start_ticks) / ticks_per_second
    return used_seconds / elapsed * 100, process_rss_mb(pid)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--max-cpu", type=float, default=0.1)
    parser.add_argument("--max-rss", type=float, default=50)
    args = parser.parse_args()
    cpu, rss = measure(args.pid, args.seconds)
    print(f"CPU={cpu:.3f}% RSS={rss:.2f}MB intervalo={args.seconds:.1f}s")
    if cpu >= args.max_cpu or rss >= args.max_rss:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
