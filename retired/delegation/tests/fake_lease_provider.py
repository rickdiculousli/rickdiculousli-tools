"""A stand-in lease provider for tests, following the contract in reference/overlay.md.

    acquire <slot> --ttl N   -> prints the lease key, exit 0; exit 3 when every slot is taken
    renew <key> --ttl N      -> exit 0 while the lease exists, else exit 1
    release <key>            -> removes the lease, exit 0

Leases are files under $FAKE_LEASE_DIR named <slot>.<n>; $FAKE_LEASE_SLOTS slots per
name (default 1). Every call is appended to $FAKE_LEASE_LOG, followed by the holder
variables check.py passes. $FAKE_LEASE_MODE can be `fail` (acquire exits 7), `nokey`
(acquire exits 0 without printing anything) or `norelease` (release exits 9).
"""

import os
from pathlib import Path
import sys
import time


def main(argv):
    store = Path(os.environ["FAKE_LEASE_DIR"])
    store.mkdir(parents=True, exist_ok=True)
    log = os.environ.get("FAKE_LEASE_LOG")
    if log:
        holder = " ".join(f"{key}={os.environ.get(key, '')}" for key in
                          ("DELEGATION_LEASE_DELEGATION", "DELEGATION_LEASE_COMMAND"))
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(" ".join(argv) + " | " + holder + "\n")
    command, args = argv[0], argv[1:]
    mode = os.environ.get("FAKE_LEASE_MODE", "")
    if command == "acquire":
        slot, ttl = args[0], args[args.index("--ttl") + 1]
        if mode == "fail":
            print("lease store unreachable", file=sys.stderr)
            return 7
        if mode == "nokey":
            return 0
        for index in range(int(os.environ.get("FAKE_LEASE_SLOTS", "1"))):
            key = f"{slot}.{index}"
            try:
                with open(store / key, "x", encoding="utf-8") as handle:
                    handle.write(f"{os.getpid()} ttl={ttl} at={time.time()}\n")
            except FileExistsError:
                continue
            print(key)
            return 0
        print(f"all slots of {slot} are leased", file=sys.stderr)
        return 3
    if command == "renew":
        key, ttl = args[0], args[args.index("--ttl") + 1]
        path = store / key
        if not path.exists():
            print(f"no such lease {key}", file=sys.stderr)
            return 1
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"renewed ttl={ttl} at={time.time()}\n")
        return 0
    if command == "release":
        path = store / args[0]
        if path.exists():
            path.unlink()
        if mode == "norelease":
            print("release refused", file=sys.stderr)
            return 9
        return 0
    print(f"unknown command {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
