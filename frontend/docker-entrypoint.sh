#!/bin/sh
set -eu

template_path="${IMPRINT_TEMPLATE_PATH:?IMPRINT_TEMPLATE_PATH is required}"
output_path="${IMPRINT_OUTPUT_PATH:?IMPRINT_OUTPUT_PATH is required}"

for variable in IMPRINT_NAME IMPRINT_STREET IMPRINT_CITY_ZIP IMPRINT_PHONE; do
  eval "value=\${$variable-}"
  if [ -z "$value" ]; then
    echo "Required Impressum variable is missing: $variable" >&2
    exit 1
  fi
done

if [ ! -f "$template_path" ]; then
  echo "Impressum template not found: $template_path" >&2
  exit 1
fi

output_dir=$(dirname "$output_path")
mkdir -p "$output_dir"
tmp_file=$(mktemp "$output_dir/.impressum.html.XXXXXX")

trap 'rm -f "$tmp_file"' EXIT

envsubst '${IMPRINT_NAME} ${IMPRINT_STREET} ${IMPRINT_CITY_ZIP} ${IMPRINT_PHONE}' \
  < "$template_path" > "$tmp_file"

mv "$tmp_file" "$output_path"
trap - EXIT

exec "$@"
