#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-OS - Certificate authority of this installation for MQTT over TLS
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
# Makes the certificates that let the broker (HYDRA-UMC-MQTT-BROKER) listen over TLS and, if wanted, demand a client certificate (mutual TLS) from every bridge, with a
# certificate authority that belongs to THIS installation: no Internet authority is involved. It only writes files under one directory; it does not edit the broker's or a
# service's configuration and it restarts nothing. `env` prints the lines to put there.
#
#   hydra_mqtt_tls.sh plan   [--name HOST]... [--ip ADDRESS]...             what would be made; changes nothing
#   hydra_mqtt_tls.sh init   [--name HOST]... [--ip ADDRESS]... [--force]   the authority (once), the certificate of the broker, 0700 directory
#   hydra_mqtt_tls.sh client NAME                                            a certificate for one bridge or service (mutual TLS); NAME is its MQTT client-id prefix
#   hydra_mqtt_tls.sh env    [--client NAME]                                 the environment lines of the broker and, with --client, of that bridge
#   hydra_mqtt_tls.sh export-ca [--out FILE]                                 the certificate of the authority (public) to copy to the machines that connect
#   hydra_mqtt_tls.sh verify                                                 every certificate is signed by the authority, not expired and not near expiry
#   hydra_mqtt_tls.sh renew                                                  a new certificate of the broker with the same authority (when the address changed or it expires)
#
# The directory is $HYDRA_TLS_DIR (default /etc/hydra-umc/tls). The key of the authority is there, mode 0600 in a 0700 directory, and is never needed by the broker or a bridge:
# copy ca.pem to them, and server.pem/server.key to the broker only, client-NAME.pem/.key to that bridge only. The certificate of the broker lasts two years, the one of a bridge
# one year, the authority ten. The key of the authority is never printed and never written anywhere else; `renew` and `client` use it from this directory.
# Names the certificate of the broker vouches for: localhost, 127.0.0.1, this machine's host name (and name.local) plus every --name and --ip.
# Nothing here has been run on a CM5.
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
# an OPENSSL_CONF that names a file which is not there makes every openssl call fail: use the default configuration instead
[[ -z "${OPENSSL_CONF:-}" || -f "${OPENSSL_CONF:-}" ]] || unset OPENSSL_CONF

DIR="${HYDRA_TLS_DIR:-/etc/hydra-umc/tls}"
CA_DAYS=3650; SERVER_DAYS=730; CLIENT_DAYS=365; WARN_DAYS=30
NAMES=(); IPS=(); FORCE=0; OUT=""; CLIENT_FOR=""

fail() { echo "hydra_mqtt_tls: $*" >&2; exit 2; }
say() { echo "[hydra-mqtt-tls] $*"; }

valid_name() { [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$ ]]; }
valid_client() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$ ]]; }
valid_ipv4() {
  local octet
  [[ "$1" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
  for octet in "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}"; do (( 10#$octet <= 255 )) || return 1; done
}
valid_ipv6() { [[ "$1" =~ ^[0-9A-Fa-f:]{2,39}$ && "$1" == *:* ]]; }

COMMAND="${1:-}"
[[ -n "$COMMAND" ]] || fail "usage: hydra_mqtt_tls.sh plan|init|client|env|export-ca|verify|renew [options]  (see the header of the script)"
shift
if [[ "$COMMAND" == client ]]; then
  CLIENT_FOR="${1:-}"; valid_client "$CLIENT_FOR" || fail "client wants a name of letters, digits, '.', '_' or '-' (the MQTT client-id prefix of the bridge), not '$CLIENT_FOR'"; shift
fi
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) valid_name "${2:-}" || fail "--name wants a host name"; NAMES+=("$2"); shift 2 ;;
    --ip) { valid_ipv4 "${2:-}" || valid_ipv6 "${2:-}"; } || fail "--ip wants an IP address"; IPS+=("$2"); shift 2 ;;
    --force) FORCE=1; shift ;;
    --out) OUT="${2:-}"; [[ -n "$OUT" ]] || fail "--out wants a file name"; shift 2 ;;
    --client) valid_client "${2:-}" || fail "--client wants a client name"; CLIENT_FOR="$2"; shift 2 ;;
    -h|--help) sed -n '5,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

need_openssl() { command -v openssl >/dev/null 2>&1 || fail "OpenSSL is not installed"; }

host_names() {
  local host
  host="$(hostname 2>/dev/null || true)"
  printf '%s\n' "DNS:localhost" "IP:127.0.0.1"
  if [[ -n "$host" ]] && valid_name "$host"; then printf '%s\n' "DNS:$host" "DNS:$host.local"; fi
  local item
  for item in "${NAMES[@]+"${NAMES[@]}"}"; do printf '%s\n' "DNS:$item"; done
  for item in "${IPS[@]+"${IPS[@]}"}"; do printf '%s\n' "IP:$item"; done
}

san_list() { host_names | awk '!seen[$0]++' | paste -sd, -; }

# Everything below runs inside the directory, so the file names given to openssl are plain relative names.
enter_dir() { [[ -d "$DIR" ]] || fail "$DIR does not exist: run init first"; cd "$DIR"; }

make_ca() {
  umask 077
  openssl ecparam -name prime256v1 -genkey -noout -out ca.key 2>/dev/null
  openssl req -x509 -new -key ca.key -sha256 -days "$CA_DAYS" -subj "/O=HYDRA-UMC/CN=HYDRA-UMC installation CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign" -out ca.pem 2>/dev/null
}

# issue NAME DAYS USAGE CN [SAN]: key + certificate signed by the authority
issue() {
  local name="$1" days="$2" usage="$3" common="$4" san="${5:-}" extensions
  umask 077
  openssl ecparam -name prime256v1 -genkey -noout -out "$name.key" 2>/dev/null
  openssl req -new -key "$name.key" -subj "/O=HYDRA-UMC/CN=$common" -out "$name.csr" 2>/dev/null
  extensions="$(mktemp "$PWD/.ext.XXXXXX")"
  {
    echo "basicConstraints=critical,CA:FALSE"
    echo "keyUsage=critical,digitalSignature"
    echo "extendedKeyUsage=$usage"
    [[ -z "$san" ]] || echo "subjectAltName=$san"
  } >"$extensions"
  openssl x509 -req -in "$name.csr" -CA ca.pem -CAkey ca.key -CAcreateserial -sha256 -days "$days" -extfile "$(basename "$extensions")" -out "$name.pem" 2>/dev/null
  rm -f "$name.csr" "$extensions"
  chmod 0600 "$name.key"; chmod 0644 "$name.pem"
}

days_left() {
  # whole days until the certificate expires (negative when it has)
  local end now
  end="$(openssl x509 -in "$1" -noout -enddate | cut -d= -f2)"
  end="$(date -u -d "$end" +%s 2>/dev/null || true)"
  [[ -n "$end" ]] || { echo 0; return; }
  now="$(date -u +%s)"
  echo $(( (end - now) / 86400 ))
}

case "$COMMAND" in
  plan)
    echo "directory:                $DIR"
    echo "authority:                ca.pem / ca.key (EC P-256, $CA_DAYS days), made once"
    echo "certificate of the broker: server.pem / server.key ($SERVER_DAYS days) for: $(san_list)"
    echo "certificate of a bridge:   client-NAME.pem / client-NAME.key ($CLIENT_DAYS days), made with: hydra_mqtt_tls.sh client NAME"
    echo "nothing was changed"
    ;;
  init)
    need_openssl
    mkdir -p "$DIR"; chmod 0700 "$DIR"
    cd "$DIR"
    if [[ -f ca.key && -f ca.pem ]]; then say "the authority already exists and is kept"; else make_ca; say "the authority was made"; fi
    if [[ -f server.pem && $FORCE -eq 0 ]]; then
      say "server.pem already exists (use renew, or init --force)"
    else
      issue server "$SERVER_DAYS" serverAuth "HYDRA-UMC broker" "$(san_list)"
      say "the certificate of the broker was made for: $(san_list)"
    fi
    say "copy ca.pem to every machine that connects; server.pem and server.key go to the broker only"
    ;;
  renew)
    need_openssl; enter_dir
    [[ -f ca.key && -f ca.pem ]] || fail "there is no authority in $DIR: run init first"
    issue server "$SERVER_DAYS" serverAuth "HYDRA-UMC broker" "$(san_list)"
    say "a new certificate of the broker was made with the same authority, for: $(san_list)"
    ;;
  client)
    need_openssl; enter_dir
    [[ -f ca.key && -f ca.pem ]] || fail "there is no authority in $DIR: run init first"
    [[ ! -f "client-$CLIENT_FOR.pem" || $FORCE -eq 1 ]] || fail "client-$CLIENT_FOR.pem already exists (use --force to make a new one)"
    issue "client-$CLIENT_FOR" "$CLIENT_DAYS" clientAuth "$CLIENT_FOR"
    say "client-$CLIENT_FOR.pem and client-$CLIENT_FOR.key were made: copy them, with ca.pem, to that bridge only"
    ;;
  export-ca)
    enter_dir
    [[ -f ca.pem ]] || fail "there is no authority in $DIR: run init first"
    if [[ -n "$OUT" ]]; then cp ca.pem "$OUT"; say "ca.pem copied to $OUT"; else cat ca.pem; fi
    ;;
  env)
    enter_dir
    [[ -f server.pem ]] || fail "there is no certificate of the broker in $DIR: run init first"
    echo "# the broker (HYDRA-UMC-MQTT-BROKER .env): TLS on 8883, a client certificate demanded"
    echo "MQTT_TLS_CERT=$DIR/server.pem"
    echo "MQTT_TLS_KEY=$DIR/server.key"
    echo "MQTT_TLS_CA=$DIR/ca.pem"
    echo "MQTT_TLS_REQUIRE_CLIENT_CERT=1"
    if [[ -n "$CLIENT_FOR" ]]; then
      [[ -f "client-$CLIENT_FOR.pem" ]] || fail "client-$CLIENT_FOR.pem does not exist: run client $CLIENT_FOR first"
      echo "# the bridge $CLIENT_FOR (its service environment; the files are copied to the paths below on that machine)"
      echo "HYDRA_MQTT_TLS_CA=/etc/hydra-umc/tls/ca.pem"
      echo "HYDRA_MQTT_TLS_CERT=/etc/hydra-umc/tls/client-$CLIENT_FOR.pem"
      echo "HYDRA_MQTT_TLS_KEY=/etc/hydra-umc/tls/client-$CLIENT_FOR.key"
    fi
    ;;
  verify)
    need_openssl; enter_dir
    [[ -f ca.pem ]] || fail "there is no authority in $DIR: run init first"
    status=0
    left="$(days_left ca.pem)"
    (( left > 0 )) && say "ca.pem: $left days left" || { echo "ca.pem: EXPIRED" >&2; status=1; }
    for pem in server.pem client-*.pem; do
      [[ -f "$pem" ]] || continue
      if ! openssl verify -CAfile ca.pem "$pem" >/dev/null 2>&1; then echo "$pem: NOT signed by this authority or expired" >&2; status=1; continue; fi
      left="$(days_left "$pem")"
      if (( left < WARN_DAYS )); then echo "$pem: only $left days left" >&2; status=1; else say "$pem: ok, $left days left"; fi
    done
    [[ $status -eq 0 ]] && echo "HYDRA_MQTT_TLS=PASS" || { echo "HYDRA_MQTT_TLS=FAIL" >&2; exit 1; }
    ;;
  *) fail "unknown command '$COMMAND' (plan, init, client, env, export-ca, verify, renew)" ;;
esac
