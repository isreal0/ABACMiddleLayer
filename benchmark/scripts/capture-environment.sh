#!/usr/bin/env bash
# Captures hardware/software version info for the current VM into
# /opt/abac-research/versions/environment.<hostname>.txt
#
# Safe to re-run; overwrites only this VM's own environment file.
set -euo pipefail

OUT_DIR="/opt/abac-research/versions"
HOST="$(hostname)"
OUT_FILE="${OUT_DIR}/environment.${HOST}.txt"

mkdir -p "$OUT_DIR"

{
  echo "captured_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "=== hostname ==="; hostname
  echo "=== whoami ==="; whoami
  echo "=== lsb_release ==="; lsb_release -a 2>&1 || true
  echo "=== uname ==="; uname -a
  echo "=== nproc ==="; nproc
  echo "=== free ==="; free -h
  echo "=== df ==="; df -h /
  echo "=== load average ==="; cat /proc/loadavg
  echo "=== git ==="; git --version || true
  echo "=== java (if present) ==="; java -version 2>&1 || echo "not installed"
  echo "=== javac (if present) ==="; javac -version 2>&1 || echo "not installed"
  echo "=== mvn (if present) ==="; mvn -version 2>&1 || echo "not installed"
  echo "=== gcc/g++ (if present) ==="; gcc --version 2>&1 | head -1 || echo "not installed"
  echo "=== cmake (if present) ==="; cmake --version 2>&1 | head -1 || echo "not installed"
  echo "=== psql (if present) ==="; psql --version 2>&1 || echo "not installed"
} > "$OUT_FILE"

echo "Wrote $OUT_FILE"
