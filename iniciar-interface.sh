#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
make -s
exec python3 interface/servidor.py "$@"
