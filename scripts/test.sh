#!/usr/bin/env bash

#Command for this script: 
# ./scripts/test.sh to run all the tests that are in the tests directory
# ./scripts/test.sh name_of_test.py to run an specific test


set -euo pipefail

python -m pytest tests/