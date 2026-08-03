"""Retry installation while a newly published PyPI release propagates."""

import argparse
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--index-url", default="https://pypi.org/simple/")
    args = parser.parse_args()
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--only-binary=:all:",
        "--no-cache-dir",
        "--index-url",
        args.index_url,
        f"wimf=={args.version}",
    ]
    for attempt in range(1, 7):
        result = subprocess.run(command, check=False)
        if result.returncode == 0:
            return
        if attempt < 6:
            print(f"Published wheel is not visible yet; retrying ({attempt}/6)", file=sys.stderr)
            time.sleep(10)
    raise SystemExit("published wheel did not become installable within 60 seconds")


if __name__ == "__main__":
    main()
