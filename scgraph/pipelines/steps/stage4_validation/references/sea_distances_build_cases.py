"""Write ../cases/sea_distances.csv: 20 port pairs, their WPI positions and their reference
sea distances (run by hand; the CSV is the frozen, committed output, never overwritten).

References:
- CERDI-seadistance V1.1 (Bertoli, Goujon & Santoni 2016, Zenodo record 240493, CC-BY-4.0):
  distances between the main port of each country, read from an extract
  (CERDI_PAIRS.json: {"ports": {code: [lat, lon]}, "pairs": [[code, code, km]]}, made from
  CERDI-seadistance_V1.1.xlsx, SHA-256 61942cbbb8f4..., and used_ports.shp,
  75aff6af3b3c...). The extract has no pair for the CERDI ports USAE, USAW and CANW.
- NGA Pub. 151 Distances Between Ports, 11th edition 2001 (US Government: "no copyright
  claimed under Title 17 U.S.C."), copy https://everyspec.com/MISC/download.php?spec=NGIA_PUB-151_2001.049282.pdf
  read 2026-11-06, SHA-256 f52240cfe0be406b. Nautical miles (1 nm = 1.852 km). A pair not
  listed directly is the sum of the legs through the book's junction points, as its preface
  prescribes; the legs are written in the CSV.

Reference of a case: CERDI when CERDI's port of both countries is the case's port (within
SAME_PORT_KM of the WPI position), otherwise Pub. 151 (its positions are the ports').

Usage: python -I sea_distances_build_cases.py WPI_DEC.csv CERDI_PAIRS.json
"""

import csv
import json
import os
import sys
from pathlib import Path

from scgraph.utils import haversine as haversine_km

OUT = Path(__file__).resolve().parents[1] / "cases" / "sea_distances.csv"

NM_KM = 1.852
SAME_PORT_KM = 25.0
WPI_SOURCE = (
    "NGA World Port Index (Pub. 150, UpdatedPub150.csv SHA-256 315644f1)"
)
CERDI_SOURCE = (
    "CERDI-seadistance V1.1 (Bertoli, Goujon & Santoni 2016; Zenodo 240493; "
    "CC-BY-4.0), via S10 cerdi_pairs.json"
)
PUB151_SOURCE = (
    "NGA Pub. 151 Distances Between Ports, 11th ed. 2001 (US Gov., no copyright), "
    "https://everyspec.com/MISC/download.php?spec=NGIA_PUB-151_2001.049282.pdf "
    "read 2026-11-06 (SHA-256 f52240cf)"
)

# port: (WPI number, CERDI country code or None)
PORTS = {
    "Shanghai": (59970, "CHN"),
    "Rotterdam": (31140, "NLD"),
    "Singapore": (50000, "SGP"),
    "Santos": (12970, "BRA"),
    "New York": (7640, None),
    "Los Angeles": (16080, None),
    "Durban": (46850, "ZAF"),
    "Felixstowe": (31560, "GBR"),
    "Busan": (60390, "KOR"),
    "Hong Kong": (57840, "HKG"),
    "Jiddah": (48140, "SAU"),
    "Mumbai": (48840, "IND"),
    "Algeciras": (38310, "ESP"),
    "Istanbul": (43420, "TUR"),
    "Yokohama": (61390, "JPN"),
    "Vancouver": (18150, None),
    "Melbourne": (54030, "AUS"),
    "Auckland": (55060, "NZL"),
    "Valparaiso": (14500, "CHL"),
    "Lagos": (46130, "NGA"),
    "Manama": (48310, "BHR"),
    "Nagoya": (61480, "JPN"),
    "Karachi": (48600, "PAK"),
}
# (origin, destination, expected route, Pub. 151 legs [(table, entry, nm)] or None)
PAIRS = [
    (
        "Shanghai",
        "Rotterdam",
        "Malacca, Suez, Gibraltar",
        [
            ("Shanghai", "Singapore", 2207),
            ("Singapore", "Port Said", 5035),
            ("Port Said", "Strait of Gibraltar", 1943),
            ("Strait of Gibraltar", "Ile d'Ouessant", 918),
            ("Rotterdam", "Ile d'Ouessant", 444),
        ],
    ),
    (
        "Singapore",
        "Rotterdam",
        "Suez, Gibraltar",
        [
            ("Singapore", "Port Said", 5035),
            ("Port Said", "Strait of Gibraltar", 1943),
            ("Strait of Gibraltar", "Ile d'Ouessant", 918),
            ("Rotterdam", "Ile d'Ouessant", 444),
        ],
    ),
    (
        "Santos",
        "Rotterdam",
        "Atlantic",
        [
            ("Santos", "Ile d'Ouessant", 5002),
            ("Rotterdam", "Ile d'Ouessant", 444),
        ],
    ),
    (
        "New York",
        "Rotterdam",
        "North Atlantic",
        [("New York", "Bishop Rock", 2937), ("Rotterdam", "Bishop Rock", 454)],
    ),
    (
        "Shanghai",
        "Los Angeles",
        "North Pacific, crosses 180 deg",
        [("Shanghai", "Los Angeles (via Tsugaru-Kaikyo)", 5699)],
    ),
    (
        "New York",
        "Shanghai",
        "Panama",
        [
            ("New York", "Panama (via Windward Passage)", 2016),
            ("Shanghai", "Panama (via Tsugaru-Kaikyo)", 8566),
        ],
    ),
    ("Durban", "Singapore", "Indian Ocean", [("Durban", "Singapore", 4872)]),
    (
        "Rotterdam",
        "Felixstowe",
        "short sea, North Sea",
        [("Felixstowe", "Rotterdam", 121)],
    ),
    (
        "Busan",
        "Shanghai",
        "short sea, East China Sea",
        [("Busan", "Shanghai (north of Cheju Do, via South Channel)", 491)],
    ),
    (
        "Hong Kong",
        "Singapore",
        "South China Sea",
        [("Hong Kong", "Singapore", 1454)],
    ),
    (
        "Jiddah",
        "Mumbai",
        "Bab-el-Mandeb, Arabian Sea",
        [("Jiddah", "Aden", 707), ("Aden", "Bombay", 1657)],
    ),
    (
        "Algeciras",
        "Istanbul",
        "Mediterranean, Dardanelles",
        [
            (
                "Istanbul",
                "Gibraltar (port, 8 km across the bay from Algeciras)",
                1804,
            )
        ],
    ),
    (
        "Yokohama",
        "Vancouver",
        "North Pacific, crosses 180 deg",
        [("Vancouver", "Yokohama", 4262)],
    ),
    ("Melbourne", "Auckland", "Tasman Sea", [("Melbourne", "Auckland", 1649)]),
    (
        "Santos",
        "Shanghai",
        "Cape of Good Hope, ~20,000 km",
        [
            ("Cape Town", "Santos", 3409),
            ("Cape Town", "Cape of Good Hope", 35),
            ("Cape of Good Hope", "Singapore", 5579),
            ("Shanghai", "Singapore", 2207),
        ],
    ),
    (
        "Valparaiso",
        "Rotterdam",
        "Panama",
        [
            ("Valparaiso", "Panama", 2616),
            ("Panama", "Ile d'Ouessant (via Mona Passage)", 4374),
            ("Rotterdam", "Ile d'Ouessant", 444),
        ],
    ),
    (
        "Lagos",
        "Rotterdam",
        "West Africa, Atlantic",
        [
            ("Lagos", "Ile d'Ouessant", 3746),
            ("Rotterdam", "Ile d'Ouessant", 444),
        ],
    ),
    (
        "Manama",
        "Singapore",
        "Hormuz, Indian Ocean",
        [("Singapore", "Al Manamah", 3652)],
    ),
    ("Nagoya", "Melbourne", "Western Pacific", None),
    (
        "Karachi",
        "Durban",
        "Western Indian Ocean (Durban table: 3,915 nm)",
        [("Karachi", "Durban", 3887)],
    ),
]


def main(wpi_path: str | os.PathLike, cerdi_path: str | os.PathLike) -> None:
    if OUT.exists():
        sys.exit(f"{OUT.name} exists: the references are frozen")
    wpi = {}
    with open(wpi_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            wpi[int(float(r["World Port Index Number"]))] = (
                float(r["Latitude"]),
                float(r["Longitude"]),
            )
    cerdi = json.loads(Path(cerdi_path).read_text())
    dist = {}
    for a, b, d in cerdi["pairs"]:
        dist[(a, b)] = dist[(b, a)] = d
    rows = []
    for o, d, via, legs in PAIRS:
        (wo, co), (wd, cd) = PORTS[o], PORTS[d]
        po, pd = wpi[wo], wpi[wd]
        row = {
            "id": f"{o}_{d}".lower().replace(" ", "_"),
            "origin_lat": po[0],
            "origin_lon": po[1],
            "destination_lat": pd[0],
            "destination_lon": pd[1],
            "reference": "",
            "source": "",
            "tolerance": "",
            "tolerance_reason": "",
            "origin_name": o,
            "origin_wpi": wo,
            "destination_name": d,
            "destination_wpi": wd,
            "route": via,
            "great_circle_km": round(haversine_km(po, pd), 1),
        }
        c = dist.get((co, cd)) if co and cd else None
        offset = (
            max(
                haversine_km(po, cerdi["ports"][co]),
                haversine_km(pd, cerdi["ports"][cd]),
            )
            if c is not None
            else None
        )
        row["cerdi_pair"] = f"{co}-{cd}" if c is not None else ""
        row["cerdi_km"] = round(c, 1) if c is not None else ""
        row["cerdi_port_offset_km"] = round(offset, 1) if c is not None else ""
        nm = sum(leg[2] for leg in legs) if legs else None
        row["pub151_nm"] = nm or ""
        row["pub151_km"] = round(nm * NM_KM, 1) if nm else ""
        row["pub151_legs"] = (
            " + ".join(f"{t} table: {e} {n:,}" for t, e, n in legs)
            if legs
            else ""
        )
        if c is not None and offset <= SAME_PORT_KM:
            row["reference_from"], row["reference"] = "cerdi", row["cerdi_km"]
        elif nm:
            row["reference_from"], row["reference"] = "pub151", row["pub151_km"]
        else:
            raise SystemExit(f"{row['id']}: no reference")
        row["source"] = "; ".join(
            [f"ports: {WPI_SOURCE}"]
            + (
                [f"CERDI {row['cerdi_pair']}: {CERDI_SOURCE}"]
                if c is not None
                else [
                    "CERDI: no pair (US/Canada ports absent from the extract)"
                ]
            )
            + (
                [f"Pub. 151: {PUB151_SOURCE}"]
                if nm
                else ["Pub. 151: pair not listed"]
            )
        )
        rows.append(row)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        both = r["cerdi_km"] != "" and r["pub151_km"] != ""
        print(
            f"{r['id']:24s} ref {r['reference_from']:6s} {r['reference']:>9} km  gc {r['great_circle_km']:>8}"
            + (
                f"  cerdi/pub151 {r['cerdi_km'] / r['pub151_km'] - 1:+.1%}"
                if both
                else ""
            )
        )


if __name__ == "__main__":
    main(*sys.argv[1:])
