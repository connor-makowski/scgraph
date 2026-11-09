"""References of test_road_distances: OSRM road distances for 20 city pairs, both ways.

    python -I road_distances_osrm.py fetch NE_POPULATED_PLACES.geojson
    python -I road_distances_osrm.py cases NE_POPULATED_PLACES.geojson

`fetch` is run ONCE (the user approved these one-off queries, coordinates only): each
direction is queried once on the public OSRM demo server (driving profile, overview=false),
>= 1.5 s apart, with a generic User-Agent; the raw answers go to
road_distances_osrm_raw.jsonl, which it refuses to overwrite. Queried 2026-11-06.

`cases` writes ../cases/road_distances.csv from the raw answers (no query), and refuses to
overwrite it: a per-case `tolerance` and its `tolerance_reason` are set by hand afterwards,
in a commit that gives the reason. City-centre coordinates: Natural Earth 1:10m populated
places v5.1.2 (public domain), by NE_ID.
"""

import csv
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "road_distances_osrm_raw.jsonl"
CASES = HERE.parent / "cases" / "road_distances.csv"
URL = "https://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=false"
NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/"
    "ne_10m_populated_places.geojson"
)

# (continent, city A NE_ID, city B NE_ID); the raw answers number the pairs from 1 in order
PAIRS = [
    ("Europe", 1159151613, 1159151529),  # Paris - Berlin
    ("Europe", 1159151503, 1159151273),  # Madrid - Lisbon
    ("Europe", 1159151299, 1159151495),  # Warsaw - Kyiv
    ("Europe", 1159151585, 1159151291),  # Moscow - St. Petersburg
    ("North America", 1159151491, 1159151485),  # Chicago - Houston
    ("North America", 1159151557, 1159151575),  # Toronto - New York
    ("North America", 1159151587, 1159151293),  # Mexico City - Guadalajara
    ("South America", 1159151621, 1159151559),  # Sao Paulo - Buenos Aires
    ("South America", 1159151511, 1159151615),  # Lima - Santiago
    ("Africa", 1159151591, 1159151403),  # Lagos - Accra
    ("Africa", 1159151597, 1159150593),  # Nairobi - Kampala
    ("Africa", 1159151515, 1159151289),  # Johannesburg - Durban
    ("Africa", 1159151603, 1159151349),  # Cairo - Alexandria
    ("Asia", 1159151405, 1159151611),  # Delhi - Mumbai
    ("Asia", 1159151595, 1159151605),  # Beijing - Shanghai
    ("Asia", 1159151509, 1159151317),  # Bangkok - Kuala Lumpur
    ("Asia", 1159151551, 1159151579),  # Tehran - Istanbul
    ("Asia", 1159150969, 1159151501),  # Almaty - Tashkent
    ("Oceania", 1159151623, 1159151565),  # Sydney - Melbourne
    ("Oceania", 1159151475, 1159151165),  # Perth - Adelaide
]


def places(ne_path):
    return {
        f["properties"]["NE_ID"]: f["properties"]
        for f in json.load(open(ne_path))["features"]
    }


def slug(text):
    text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def fetch(ne_path):
    import requests

    if RAW.exists():
        sys.exit(f"{RAW.name} exists: the references are frozen")
    p = places(ne_path)
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    with open(RAW, "w") as out:
        for k, (_, ida, idb) in enumerate(PAIRS, 1):
            for tag, (o, d) in (
                ("ab", (p[ida], p[idb])),
                ("ba", (p[idb], p[ida])),
            ):
                url = URL.format(
                    o["LONGITUDE"], o["LATITUDE"], d["LONGITUDE"], d["LATITUDE"]
                )
                when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                answer = session.get(url, timeout=60).json()
                out.write(
                    json.dumps(
                        {
                            "pair": k,
                            "direction": tag,
                            "url": url,
                            "time": when,
                            "answer": answer,
                        }
                    )
                    + "\n"
                )
                time.sleep(1.5)


def cases(ne_path):
    if CASES.exists():
        sys.exit(f"{CASES.name} exists: the references are frozen")
    p = places(ne_path)
    raw = {(r["pair"], r["direction"]): r for r in map(json.loads, open(RAW))}
    rows = []
    for k, (continent, ida, idb) in enumerate(PAIRS, 1):
        a, b = p[ida], p[idb]
        answers = {tag: raw[(k, tag)] for tag in ("ab", "ba")}
        km = {
            tag: r["answer"]["routes"][0]["distance"] / 1000
            for tag, r in answers.items()
        }
        row = {
            "id": f"{slug(a['NAME'])}_{slug(b['NAME'])}",
            "origin_lat": a["LATITUDE"],
            "origin_lon": a["LONGITUDE"],
            "destination_lat": b["LATITUDE"],
            "destination_lon": b["LONGITUDE"],
            "reference": round(km["ab"], 3),
            "source": (
                f"coordinates: Natural Earth 10m populated places v5.1.2 ({NE_URL}); "
                "reference: OSRM demo server router.project-osrm.org, driving profile "
                "(no data version in the answer), queried once per direction on "
                "2026-11-06, raw answers in references/road_distances_osrm_raw.jsonl"
            ),
            "tolerance": "",
            "tolerance_reason": "",
            "continent": continent,
            "origin_name": a["NAME"],
            "origin_country": a["ADM0_A3"],
            "origin_ne_id": ida,
            "destination_name": b["NAME"],
            "destination_country": b["ADM0_A3"],
            "destination_ne_id": idb,
            "reference_back": round(km["ba"], 3),
        }
        for tag, r in answers.items():
            row[f"osrm_{tag}_snap_m"] = "+".join(
                str(round(w["distance"])) for w in r["answer"]["waypoints"]
            )
            row[f"osrm_{tag}_query"] = f"{r['url']} at {r['time']}"
        row["osrm_asymmetry_pct"] = round(
            100 * abs(km["ab"] - km["ba"]) / ((km["ab"] + km["ba"]) / 2), 2
        )
        rows.append(row)
    with open(CASES, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    {"fetch": fetch, "cases": cases}[sys.argv[1]](sys.argv[2])
