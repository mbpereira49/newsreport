#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3 -m daily_digest.cli --config config/digest.example.json
