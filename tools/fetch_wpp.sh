#!/bin/sh
# Download the windy postman instances of Corberan et al. (2012) into data/wpp. Not stored here.
set -e
TMP=$(mktemp -d)
curl -sSL -o "$TMP/WPP.zip" https://www.uv.es/corberan/data/WPP.zip
mkdir -p data/wpp
unzip -q -o "$TMP/WPP.zip" -d data/wpp
rm -rf "$TMP"
echo "$(ls data/wpp | wc -l) instances in data/wpp"
