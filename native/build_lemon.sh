#!/usr/bin/env bash
# Builds liblemon_match.so next to this script from the LEMON sources in native/lemon_src.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
"${CXX:-c++}" -std=c++11 -O3 -DNDEBUG -fPIC -shared -w -I"$HERE/lemon_src" \
    "$HERE/match_shim.cpp" "$HERE/lemon_src/lemon/base.cc" -o "$HERE/liblemon_match.so"
echo "Built $HERE/liblemon_match.so"
