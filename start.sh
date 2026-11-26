#!/usr/bin/env bash
# Christmas tree: update, install missing libraries, start (a running tree is replaced).
# "./start.sh stop" only closes it.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
pkill -f "python3 $(pwd)/tree.py" > /dev/null 2>&1   # an old (GTK) version, it cannot be asked to quit
exec python3 launcher.py "$@"
