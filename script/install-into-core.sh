#!/usr/bin/env bash
# Copy the integration into a Home Assistant core checkout and regenerate the
# files core derives from it.
#
#   script/install-into-core.sh ../core
#
# The generation steps run only when the checkout has a .venv.
set -euo pipefail

core=$(cd "${1:?usage: $0 <path to a home-assistant/core checkout>}" && pwd)
here=$(cd "$(dirname "$0")/.." && pwd)

rsync -a --delete --exclude translations --exclude __pycache__ \
  "$here/homeassistant/components/gtw08/" "$core/homeassistant/components/gtw08/"
rsync -a --delete --exclude __pycache__ \
  "$here/tests/components/gtw08/" "$core/tests/components/gtw08/"

# Opt the integration into strict typing, keeping the list sorted
python3 - "$core/.strict-typing" <<'EOF'
import sys

path, entry = sys.argv[1], "homeassistant.components.gtw08.*"
lines = open(path).read().splitlines()
if entry not in lines:
    for i, line in enumerate(lines):
        if line.startswith("homeassistant.components.") and line > entry:
            lines.insert(i, entry)
            break
    open(path, "w").write("\n".join(lines) + "\n")
EOF

python="$core/.venv/bin/python"
if [[ ! -x $python ]]; then
  echo "No .venv in $core: run script/setup there, then this script again."
  exit 0
fi

cd "$core"
"$python" -m script.translations develop --integration gtw08
# Run only the plugins that generate files. The quality_scale plugin fails
# until the brands entry exists, and any failure cancels generation.
PATH="$core/.venv/bin:$PATH" "$python" -m script.hassfest \
  -p codeowners,config_flow,mypy_config,translations
PATH="$core/.venv/bin:$PATH" "$python" -m script.gen_requirements_all
