#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Encrypted backup of the settings and state
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Encrypted backup of the settings and state of this installation (the server data directory: users, settings, audit log), made with a passphrase of the owner.
#
# The archive is encrypted with AES-256 (PBKDF2) using a passphrase read from a file, and a keyed hash (HMAC-SHA-256, with a key derived from the passphrase) is written next to it:
# restoring refuses an archive that was changed, BEFORE anything is decrypted, which a plain checksum cannot do (whoever can change the archive can change the checksum).
# The archive is verified by decrypting it again before the script reports success. The passphrase is never printed, never put on a command line and never stored anywhere.
# It never includes the environment file (server.env) or a TLS private key: keep those somewhere else.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: backup_settings.sh --data-dir DIR --out-dir DIR --passphrase-file FILE

  --data-dir         the directory to save (for example /opt/hydra-umc/server/data)
  --out-dir          where the .tar.gz.enc archive, its .sha256 and its .hmac are written
  --passphrase-file  a file whose first line is the passphrase (at least 12 characters, mode 600)
USAGE
}

DATA_DIR="" OUT_DIR="" PASS_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir) DATA_DIR="${2:-}"; shift 2 ;;
    --out-dir) OUT_DIR="${2:-}"; shift 2 ;;
    --passphrase-file) PASS_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ -d "$DATA_DIR" && -n "$OUT_DIR" && -f "$PASS_FILE" ]] || { usage >&2; exit 2; }
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }
# an OPENSSL_CONF that names a file which is not there makes every openssl call fail: use the default configuration instead
[[ -z "${OPENSSL_CONF:-}" || -f "${OPENSSL_CONF:-}" ]] || unset OPENSSL_CONF
# A native Windows openssl (Git Bash) does not translate the path inside "file:"; give it a Windows path.
PASS_PATH="$PASS_FILE"; if command -v cygpath >/dev/null 2>&1; then PASS_PATH="$(cygpath -m "$PASS_FILE")"; fi
[[ -s "$PASS_FILE" ]] || { echo "the passphrase file is empty" >&2; exit 1; }
if [[ "$(head -n1 "$PASS_FILE" | tr -d '\r\n' | wc -c)" -lt 12 ]]; then echo "the passphrase must be at least 12 characters" >&2; exit 1; fi

# the key of the keyed hash: derived from the passphrase, so the passphrase itself is never on a command line
mac_key() { { printf 'hydra-backup-mac:'; cat "$PASS_FILE"; } | openssl dgst -sha256 -r | cut -d' ' -f1; }
mac_of() { openssl dgst -sha256 -mac HMAC -macopt "hexkey:$(mac_key)" -r "$1" | cut -d' ' -f1; }

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$OUT_DIR/hydra-umc-data-$STAMP.tar.gz.enc"
[[ ! -e "$TARGET" ]] || { echo "refusing to overwrite $TARGET" >&2; exit 1; }
PARENT="$(cd "$DATA_DIR/.." && pwd)"
BASE="$(basename "$(cd "$DATA_DIR" && pwd)")"

umask 077
tar -C "$PARENT" -czf - --exclude="$BASE/*.tmp" "$BASE" | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$PASS_PATH" -out "$TARGET"

# Verify: it must decrypt and list at least the directory itself.
COUNT="$(openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$PASS_PATH" -in "$TARGET" | tar -tzf - | wc -l)"
if [[ "$COUNT" -lt 1 ]]; then rm -f -- "$TARGET"; echo "verification failed: the archive is empty" >&2; exit 1; fi
( cd "$OUT_DIR" && sha256sum "$(basename "$TARGET")" >"$(basename "$TARGET").sha256" )
printf '%s  %s\n' "$(mac_of "$TARGET")" "$(basename "$TARGET")" >"$TARGET.hmac"
echo "HYDRA_BACKUP=PASS file=$TARGET entries=$COUNT"
