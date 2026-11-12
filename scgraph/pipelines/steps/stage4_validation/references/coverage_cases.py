"""References of test_coverage and test_crossings, from Natural Earth 1:10m v5.1.2.

City cases: every Natural Earth populated place with POP_MAX >= 500,000 (POP_MAX: the
largest population figure Natural Earth gives for the place, metropolitan where known).
Each city gets a landmass: the Natural Earth land polygon that contains it (else the nearest
one; its distance is recorded), with the Americas split at the Darien Gap (no road there):
cities of South American countries form their own landmass. The landmass's main city is its
most populous city (POP_MAX) in this list; the check tests that every city's nearest road
node lies in the strongly connected road component of the main city's nearest road node.

Island and strait cases (crossings): 12 fixed pairs whose road route needs a bridge,
tunnel or ferry. Coordinates from Natural Earth (NE_ID) except Ronne and Kadikoy (not in
Natural Earth), read from their Wikipedia pages (2026-11-06).

Writes ../cases/coverage.csv and ../cases/crossings.csv (refuses to overwrite them). A row
disabled later by hand (Mazatlan) says why in its `source`.

Usage: python -I coverage_cases.py NE_POPULATED_PLACES.geojson NE_LAND.geojson
"""

import csv
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from shapely import STRtree
from shapely.geometry import Point, shape

from scgraph.utils import haversine

CASES = Path(__file__).resolve().parents[1] / "cases"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/"
SOUTH_AMERICA = {
    "ARG",
    "BOL",
    "BRA",
    "CHL",
    "COL",
    "ECU",
    "GUF",
    "GUY",
    "PER",
    "PRY",
    "SUR",
    "URY",
    "VEN",
    "FLK",
}
# Natural Earth rows disabled (id starts with '#'), with the reason written in the row
DISABLED = {
    1159148743: "Natural Earth error: a small place named Natal in Amazonas carries the "
    "population of Natal (RN), which is row natal_bra",
    1159148899: "Natural Earth error: a small place named Vila Velha in Amapa carries the "
    "population of Vila Velha (ES), which is row vila_velha_bra_1159150223",
}
# id, name, A (NE_ID or (lat, lon, source)), B, expected crossing
ISLANDS = [
    (
        "london_paris",
        "London - Paris",
        1159151577,
        1159151613,
        "Channel Tunnel shuttle or ferry",
    ),
    (
        "dover_calais",
        "Dover - Calais",
        1159135701,
        1159142047,
        "ferry or Channel Tunnel shuttle",
    ),
    (
        "copenhagen_malmo",
        "Copenhagen - Malmo",
        1159151437,
        1159149739,
        "Oresund bridge",
    ),
    (
        "copenhagen_odense",
        "Copenhagen - Odense (Great Belt)",
        1159151437,
        1159143035,
        "Great Belt bridge",
    ),
    (
        "ronne_copenhagen",
        "Ronne (Bornholm) - Copenhagen",
        (55.09861, 14.70139, "https://en.wikipedia.org/wiki/R%C3%B8nne"),
        1159151437,
        "ferry (Ronne - Ystad or Koge)",
    ),
    (
        "messina_reggio_di_calabria",
        "Messina - Reggio di Calabria",
        1159139527,
        1159129715,
        "ferry (Strait of Messina)",
    ),
    (
        "kadikoy_istanbul",
        "Istanbul Asian side (Kadikoy) - Istanbul",
        (
            40.993389,
            29.037361,
            "https://en.wikipedia.org/wiki/Kad%C4%B1k%C3%B6y",
        ),
        1159151579,
        "Bosphorus bridge or tunnel",
    ),
    (
        "hobart_melbourne",
        "Hobart - Melbourne",
        1159151171,
        1159151565,
        "ferry (Bass Strait)",
    ),
    (
        "sapporo_tokyo",
        "Sapporo - Tokyo",
        1159151399,
        1159151609,
        "ferry (Tsugaru Strait; Seikan is rail only)",
    ),
    (
        "victoria_vancouver",
        "Victoria - Vancouver",
        1159151039,
        1159151555,
        "ferry (Strait of Georgia)",
    ),
    (
        "manama_dammam",
        "Manama - Dammam",
        1159150451,
        1159136389,
        "King Fahd Causeway",
    ),
    (
        "singapore_johor_bahru",
        "Singapore - Johor Bahru",
        1159151627,
        1159146479,
        "Johor-Singapore Causeway",
    ),
]


def slug(text: str) -> str:
    text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def main(places_path: str | os.PathLike, land_path: str | os.PathLike) -> None:
    if (CASES / "coverage.csv").exists() or (CASES / "crossings.csv").exists():
        sys.exit(
            "the cases exist: they are changed only by a commit that gives the reason"
        )
    places = {
        f["properties"]["NE_ID"]: f["properties"]
        for f in json.load(open(places_path))["features"]
    }
    polygons = []
    for f in json.load(open(land_path))["features"]:
        g = shape(f["geometry"])
        polygons.extend(g.geoms if g.geom_type == "MultiPolygon" else [g])
    tree = STRtree(polygons)
    cities = sorted(
        (p for p in places.values() if (p["POP_MAX"] or 0) >= 500_000),
        key=lambda p: -p["POP_MAX"],
    )
    rows, crossings, main_city, ids = [], [], {}, set()
    for p in cities:
        pt = Point(p["LONGITUDE"], p["LATITUDE"])
        hit = [int(i) for i in tree.query(pt, predicate="within")]
        if hit:
            k, off_km = hit[0], 0.0
        else:  # coastal point just outside the 1:10m coastline
            k = int(tree.nearest(pt))
            q = polygons[k].exterior.interpolate(
                polygons[k].exterior.project(pt)
            )
            off_km = haversine([p["LATITUDE"], p["LONGITUDE"]], [q.y, q.x])
        landmass = f"land{k}" + (
            "-south-america" if p["ADM0_A3"] in SOUTH_AMERICA else ""
        )
        main_city.setdefault(landmass, p)  # cities are sorted by population
        m = main_city[landmass]
        cid = f"{slug(p['NAME'])}_{p['ADM0_A3'].lower()}"
        cid = cid if cid not in ids else f"{cid}_{p['NE_ID']}"
        ids.add(cid)
        note = (
            f"; DISABLED: {DISABLED[p['NE_ID']]}"
            if p["NE_ID"] in DISABLED
            else ""
        )
        cid = f"#{cid}" if note else cid
        rows.append(
            {
                "id": cid,
                "origin_lat": p["LATITUDE"],
                "origin_lon": p["LONGITUDE"],
                "destination_lat": m["LATITUDE"],
                "destination_lon": m["LONGITUDE"],
                "reference": "",
                "source": f"Natural Earth 10m populated places v5.1.2, POP_MAX >= 500000 "
                f"({NE}ne_10m_populated_places.geojson); landmass from "
                f"{NE}ne_10m_land.geojson{note}",
                "tolerance": "",
                "tolerance_reason": "",
                "origin_name": p["NAME"],
                "origin_country": p["ADM0_A3"],
                "origin_ne_id": p["NE_ID"],
                "pop_max": p["POP_MAX"],
                "landmass": landmass,
                "outside_land_km": round(off_km, 1),
                "destination_name": m["NAME"],
                "destination_ne_id": m["NE_ID"],
            }
        )
    for cid, name, a, b, crossing in ISLANDS:
        ends, sources = [], []
        for e in (a, b):
            if isinstance(e, tuple):
                ends.append(
                    (name.split(" - ")[0] if e is a else "", e[0], e[1], "")
                )
                sources.append(e[2])
            else:
                ends.append(
                    (
                        places[e]["NAME"],
                        places[e]["LATITUDE"],
                        places[e]["LONGITUDE"],
                        e,
                    )
                )
                sources.append(f"Natural Earth NE_ID {e}")
        crossings.append(
            {
                "id": cid,
                "origin_lat": ends[0][1],
                "origin_lon": ends[0][2],
                "destination_lat": ends[1][1],
                "destination_lon": ends[1][2],
                "reference": crossing,
                "source": "; ".join(sources),
                "tolerance": "",
                "tolerance_reason": "",
                "pair": name,
                "origin_ne_id": ends[0][3],
                "destination_name": ends[1][0],
                "destination_ne_id": ends[1][3],
            }
        )
    for name, table in (("coverage", rows), ("crossings", crossings)):
        with open(
            CASES / f"{name}.csv", "w", newline="", encoding="utf-8"
        ) as f:
            w = csv.DictWriter(
                f, fieldnames=list(table[0]), lineterminator="\n"
            )
            w.writeheader()
            w.writerows(table)
    print(
        len(rows),
        "cities,",
        len(main_city),
        "landmasses,",
        len(ISLANDS),
        "island cases",
    )
    for lm, m in main_city.items():
        print(lm, m["NAME"], sum(r["landmass"] == lm for r in rows))


if __name__ == "__main__":
    main(*sys.argv[1:])
