#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prevent system sleep/hibernate while the LRAB matrix runs.

Uses SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) — a
process-scoped, non-persistent keep-awake: exit the process and Windows
resumes its normal idle policy. No system settings are modified.

Usage:  python keep_awake.py            # run until killed
        (matrix runner starts this alongside; killed in cleanup)
"""
import ctypes
import sys
import time

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def main():
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
    print("[keep-awake] system sleep suppressed (process-scoped)", flush=True)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        print("[keep-awake] released", flush=True)


if __name__ == "__main__":
    sys.exit(main())
