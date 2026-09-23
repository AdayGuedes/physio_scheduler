#!/usr/bin/env bash

#Command for this script:
#./scripts/format.sh to check and modify all the format errors
#./scripts/format.sh --check if you want to just check what is wrong, no modify


set -euo pipefail

if [[ "${1:-}" == "--check" ]]; then 
    black --check .
else 
    black .
fi