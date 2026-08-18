#!/usr/bin/env python3
"""把子进程放到新会话，避免 Agent/终端退出时整组杀掉。"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--log", required=True)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("usage: _spawn.py --log FILE [--cwd DIR] -- cmd ...", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(args.log)) or ".", exist_ok=True)
    log = open(args.log, "a", buffering=1)
    proc = subprocess.Popen(
        cmd,
        cwd=args.cwd,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    print(proc.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
