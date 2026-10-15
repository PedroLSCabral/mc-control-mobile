"""Pretends to be a Minecraft server, so the agent can be tested without Java.

Behaves like the real thing where it matters to the agent:
- prints log lines, then `Done (...)! For help, type "help"` when "ready";
- reads commands from stdin and exits cleanly on `stop`.

Flags let tests simulate bad behaviour (slow start, ignoring stop, crashing).
"""

import argparse
import sys
import time


def log(msg: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] [Server thread/INFO]: {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-delay", type=float, default=0.5, help="seconds before Done")
    parser.add_argument("--never-ready", action="store_true", help="never print Done")
    parser.add_argument("--ignore-stop", action="store_true", help="ignore the stop command")
    parser.add_argument("--crash-after", type=float, default=None, help="exit(1) after N seconds")
    args = parser.parse_args()

    log("Starting minecraft server version 1.21.1 (fake)")
    if args.crash_after is not None:
        time.sleep(args.crash_after)
        log("Encountered an unexpected exception (fake crash)")
        return 1

    time.sleep(args.start_delay)
    if not args.never_ready:
        log(f'Done ({args.start_delay:.3f}s)! For help, type "help"')

    for line in sys.stdin:
        command = line.strip()
        if command == "stop" and not args.ignore_stop:
            log("Stopping the server")
            log("Saving worlds")
            return 0
        if command:
            log(f"Received command: {command}")

    # stdin closed (agent died): a real server keeps running; we just wait to be killed.
    while True:
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
