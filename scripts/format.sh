#!/usr/bin/env bash

set -euo pipefail

if [[ "${1:-}" == "--check" ]]; then 
    black --check .
else 
    black .
fi