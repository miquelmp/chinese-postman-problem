# OpenStreetMap extracts

Street networks used in section 9.4 of the report, exported from Overpass Turbo on 3 November 2026 as
raw OSM JSON. Each file keeps the timestamp of its data in `osm3s.timestamp_osm_base`.

The query is `overpass_query` in `chinese_postman/web.py`, with the bounding box of the area and a
timeout of 120 seconds. `web.from_osm` reads the files.

Data © OpenStreetMap contributors, available under the Open Database Licence (ODbL) 1.0:
https://www.openstreetmap.org/copyright
