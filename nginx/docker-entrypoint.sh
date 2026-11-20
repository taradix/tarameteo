#!/bin/sh

set -eu

python3 /bootstrap.py

exec "$@"
