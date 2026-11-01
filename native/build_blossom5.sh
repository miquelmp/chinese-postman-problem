#!/usr/bin/env bash
# Downloads Kolmogorov's Blossom V and builds libblossom5.so next to this script.
# Blossom V licence: evaluation and non-commercial research only; commercial use needs a
# licence from UCL Business. Read LICENSE.TXT in the downloaded source before using it.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$HERE/blossom5-src}"
if [ ! -f "$SRC/PerfectMatching.h" ]; then
    git clone --depth 1 https://github.com/dasdkslkd/blossom5 "$SRC"
fi
OBJ="$(mktemp -d)"
for f in "$SRC"/*.cpp "$SRC"/MinCost/*.cpp; do
    case "$(basename "$f")" in example.cpp) continue ;; esac
    c++ -O3 -D_NDEBUG -fPIC -w -c "$f" -o "$OBJ/$(basename "$f" .cpp).o"
done
c++ -O3 -D_NDEBUG -fPIC -w -I"$SRC" -c "$HERE/pm_shim.cpp" -o "$OBJ/pm_shim.o"
c++ -shared -o "$HERE/libblossom5.so" "$OBJ"/*.o
rm -rf "$OBJ"
echo "Built $HERE/libblossom5.so"
