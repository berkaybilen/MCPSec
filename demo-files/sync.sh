#!/usr/bin/env bash
# Copy demo files into /tmp so the filesystem MCP backend can read them.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cp "$SCRIPT_DIR/notes.txt"      /tmp/notes.txt
cp "$SCRIPT_DIR/malicious.txt"  /tmp/malicious.txt
cp "$SCRIPT_DIR/secrets.txt"    /tmp/secrets.txt
cp "$SCRIPT_DIR/safe.txt"       /tmp/safe.txt

echo "Demo files copied to /tmp:"
ls -la /tmp/notes.txt /tmp/malicious.txt /tmp/secrets.txt /tmp/safe.txt
