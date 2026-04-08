"""Minimaler Worker (Beispiel)."""

import os
import time

import alpha_lib

if __name__ == "__main__":
    print("worker started", alpha_lib.greet("alpha-lib"), flush=True)
    while True:
        time.sleep(float(os.environ.get("WORKER_INTERVAL", "5")))
