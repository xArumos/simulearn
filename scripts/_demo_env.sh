# Shared helpers for scripts/tunnel.sh, scripts/demo_up.sh, scripts/serve_product.sh and scripts/product_up.sh.
# Sourced, not run. Reads only local files.

# env_value NAME ENV_FILE
#   Prints the value of NAME: a shell variable wins over the .env file, even when empty (same rule as
#   backend/app/env.py). Fails when NAME is set nowhere. Callers must never print a secret read with it.
env_value() {
  local name="$1" env_file="$2"
  if [ "${!name+set}" = set ]; then
    printf '%s' "${!name}"
    return 0
  fi
  [ -f "$env_file" ] || return 1
  local line value
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${name}[[:space:]]*=" "$env_file" | tail -n 1)" || return 1
  value="${line#*=}"
  value="$(printf '%s' "$value" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  if [ "${#value}" -ge 2 ] && { [ "${value:0:1}" = '"' ] || [ "${value:0:1}" = "'" ]; } \
     && [ "${value:0:1}" = "${value: -1}" ]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

# demo_password_set ENV_FILE: succeeds when DEMO_PASSWORD is non-empty (shell first, then .env). Never prints it.
demo_password_set() {
  local value
  value="$(env_value DEMO_PASSWORD "$1")" || return 1
  [ -n "$value" ]
}

# env_flag_off NAME ENV_FILE: succeeds when NAME is 0 / false / no / off (shell first, then .env), the values
# src/product/server.py reads as "off".
env_flag_off() {
  local value
  value="$(env_value "$1" "$2")" || return 1
  case "${value,,}" in 0|false|no|off) return 0 ;; *) return 1 ;; esac
}

# demo_listening PORT: succeeds when something accepts TCP connections on 127.0.0.1:PORT.
demo_listening() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# ingress_routes CONFIG
#   Prints "HOSTNAME PORT" for each ingress rule of a cloudflared config whose service is a local
#   http://127.0.0.1:PORT or http://localhost:PORT. A rule without a hostname prints "*". Catch-all rules such as
#   http_status:404 print nothing. Pure bash, so it needs no extra tools.
ingress_routes() {
  local line key value host=""
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    if [[ "$line" =~ ^[[:space:]]*-[[:space:]]* ]]; then host="*"; fi
    [[ "$line" =~ ^[[:space:]]*(-[[:space:]]*)?(hostname|service):[[:space:]]*(.*)$ ]] || continue
    key="${BASH_REMATCH[2]}"
    value="${BASH_REMATCH[3]}"
    value="${value//[\"\' 	]/}"
    if [ "$key" = hostname ]; then
      host="$value"
    else
      if [[ "$value" =~ ^https?://(127\.0\.0\.1|localhost):([0-9]+)(/.*)?$ ]]; then
        echo "${host:-*} ${BASH_REMATCH[2]}"
      fi
      host=""
    fi
  done < "$1"
}
