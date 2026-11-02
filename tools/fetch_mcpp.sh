#!/bin/sh
# Download the mixed Chinese postman instances of Corberan et al. (2012, sets MA and MB), as
# distributed with OAR Lib (Lum, Golden and Wasil, 2019), into data/mcpp. Not stored here.
set -e
COMMIT=db407dfa776977fd0ecede430c9d8f57efdf78cf
TMP=$(mktemp -d)
git clone -q https://github.com/Olibear/ArcRoutingLibrary "$TMP/oar"
git -C "$TMP/oar" checkout -q "$COMMIT"
mkdir -p data/mcpp
cp "$TMP"/oar/test_instances/MCPP_Instances_Corberan/* data/mcpp/
rm -rf "$TMP"
echo "$(ls data/mcpp | wc -l) instances in data/mcpp"
