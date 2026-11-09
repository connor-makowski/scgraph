"""Endpoint coordinates of the rail corridors (test_rail_corridors), from OSM Nominatim.
Run by hand.

    python -I rail_corridors_geocode.py > rail_corridors_nominatim.jsonl

One JSON line per query with Nominatim's raw answer; the first result of each query was copied
into cases/rail_corridors.csv, except Chicago Union Station (the train_station result,
~100 m from the first) (Maasvlakte: the admin area's centroid; City Deep: a place of
that name). Generic User-Agent, one request per 1.2 s (Nominatim usage policy).
"""

import json
import time
import urllib.parse
import urllib.request

QUERIES = {
    "rotterdam_duisburg": ["Maasvlakte, Rotterdam", "Duisburg Hauptbahnhof"],
    "hamburg_munich": ["Hamburg-Harburg Bahnhof", "München Hauptbahnhof"],
    "paris_marseille": [
        "Paris Gare de Lyon railway station",
        "Gare de Marseille-Saint-Charles",
    ],
    "chicago_los_angeles": [
        "Chicago Union Station",
        "Los Angeles Union Station",
    ],
    "chicago_new_york": [
        "Chicago Union Station",
        "Pennsylvania Station New York",
    ],
    "moscow_vladivostok": [
        "Yaroslavsky railway station Moscow",
        "Vladivostok railway station",
    ],
    "beijing_shanghai": ["Beijing railway station", "Shanghai railway station"],
    "chongqing_duisburg": [
        "Tuanjiecun railway station Chongqing",
        "Duisburg Hauptbahnhof",
    ],
    "mumbai_delhi": [
        "Mumbai Central railway station",
        "New Delhi railway station",
    ],
    "durban_johannesburg": [
        "Durban railway station",
        "City Deep, Johannesburg",
    ],
    "santos_jundiai": ["Estação Valongo Santos", "Estação Jundiaí"],
    "sydney_perth": ["Sydney Central station", "East Perth Terminal"],
    "toronto_vancouver": [
        "Toronto Union Station",
        "Pacific Central Station Vancouver",
    ],
    "tehran_mashhad": ["Tehran railway station", "Mashhad railway station"],
    "kolkata_delhi": [
        "Howrah Junction railway station",
        "New Delhi railway station",
    ],
}

for case, queries in QUERIES.items():
    for q in queries:
        url = (
            "https://nominatim.openstreetmap.org/search?"
            + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 3})
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
        )
        with urllib.request.urlopen(req) as r:
            answer = json.load(r)
        print(
            json.dumps(
                {
                    "case": case,
                    "query": q,
                    "date": time.strftime("%Y-%m-%d"),
                    "answer": answer,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        time.sleep(1.2)
