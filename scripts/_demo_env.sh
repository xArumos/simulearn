# Shared helpers for scripts/tunnel.sh and scripts/demo_up.sh. Sourced, not run. Reads only local files.

# demo_password_set ENV_FILE
#   Succeeds when DEMO_PASSWORD is non-empty. A shell variable wins over the .env file, even when empty (same rule
#   as backend/app/env.py). Never prints the value.
demo_password_set() {
  local env_file="$1"
  if [ "${DEMO_PASSWORD+set}" = set ]; then
    [ -n "$DEMO_PASSWORD" ]
    return
  fi
  [ -f "$env_file" ] || return 1
  local line value
  line="$(grep -E '^[[:space:]]*(export[[:space:]]+)?DEMO_PASSWORD[[:space:]]*=' "$env_file" | tail -n 1)" || return 1
  value="${line#*=}"
  value="$(printf '%s' "$value" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  if [ "${#value}" -ge 2 ] && { [ "${value:0:1}" = '"' ] || [ "${value:0:1}" = "'" ]; } \
     && [ "${value:0:1}" = "${value: -1}" ]; then
    value="${value:1:${#value}-2}"
  fi
  [ -n "$value" ]
}

# demo_listening PORT: succeeds when something accepts TCP connections on 127.0.0.1:PORT.
demo_listening() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
