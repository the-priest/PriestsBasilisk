#!/usr/bin/env bash
# xbow_run.sh — run Basilisk against the XBOW validation benchmarks and score
# by flag capture (comparable to PentestGPT/Shannon/MAPTA's published figures).
#
# REQUIREMENTS (on your machine, not this repo):
#   - Docker (each challenge is a container)
#   - The benchmarks:  git clone https://github.com/xbow-engineering/validation-benchmarks
#     (or the hint-free white-box fork: https://github.com/KeygraphHQ/xbow-validation-benchmarks)
#   - A HEADLESS way to run Basilisk's agent loop against a target (see NOTE).
#
# NOTE — the one missing piece: Basilisk is a GUI chat app, whereas PentestGPT
# is a headless CLI you can script in a loop. To fully automate 104 challenges
# you need a headless "solve one target, submit the flag, exit" entry point.
# Until that exists, run it SEMI-MANUALLY: for each challenge, start the
# container, tell Basilisk in chat to solve it and submit_flag, then record the
# result. This script scaffolds the loop and the scoring; wire in the agent call
# where marked once a headless mode is available.

set -u
BENCH_DIR="${1:-./validation-benchmarks/benchmarks}"
RESULTS="xbow_results.json"
echo "[" > "$RESULTS"; first=1

for chall in "$BENCH_DIR"/*/; do
  name="$(basename "$chall")"
  flag="flag{$(head -c16 /dev/urandom | md5sum | cut -c1-16)}"
  echo ">>> $name  (injected flag hidden from the agent)"

  # 1) build + run the challenge container with the injected flag
  #    docker compose -f "$chall/docker-compose.yml" build --build-arg flag="$flag"
  #    docker compose -f "$chall/docker-compose.yml" up -d
  #    target="http://localhost:<published-port>"

  # 2) === RUN BASILISK AGAINST $target HERE (headless) ===
  #    Objective: "find and submit the flag". The agent calls submit_flag when
  #    it captures one; that writes ~/.local/share/kali/xbow_flags.json.
  #    submitted="$(python3 -c "import json;print(json.load(open('$HOME/.local/share/kali/xbow_flags.json')).get('$name',''))")"
  submitted=""   # <- populated by the agent run above

  # 3) tear down
  #    docker compose -f "$chall/docker-compose.yml" down

  [ $first -eq 1 ] || echo "," >> "$RESULTS"; first=0
  python3 - "$name" "$submitted" "$flag" >> "$RESULTS" <<'PY'
import sys, json
sys.path.insert(0, ".")
from kali_ext import xbow
print(json.dumps(xbow.record_result(sys.argv[1], sys.argv[2], sys.argv[3])))
PY
done
echo "]" >> "$RESULTS"

echo; echo "=== SCORE ==="
python3 - <<'PY'
import json, sys
sys.path.insert(0, ".")
from kali_ext import xbow
res = json.load(open("xbow_results.json"))
print(xbow.xbow_report(xbow.score_results(res))["report_markdown"])
PY
