"""Build the small tables of hubs that the multimodal pipelines read.

The tables are snapshots kept with the code, in `scgraph/pipelines/data/`, so that a
build reads the same hubs on every machine. This script makes them again from their
sources. Its output is a new snapshot, to be reviewed like any change of code:

- `ports.csv`: the ports of the World Port Index, with their number, position, harbour
  type and whether a railway serves them;
- `airports.csv` and `flights.csv`: the large and medium airports of OurAirports that
  have regular flights in the OpenSky flight list of 2021, and these flights;
- `rail_terminals.csv`: the freight terminals of Wikidata that are still open.

`data/README.md` gives the sources, their licences and the counts of the last run.

Usage:
    python utils/build_hub_tables.py --opensky-dir DIR [--wpi FILE]

DIR holds the 12 monthly files of 2021 of the OpenSky flight list (Zenodo record
5815448, 2.3 GB); the script downloads the missing ones and checks every md5. FILE is a
copy of the World Port Index CSV (gzipped or not), for when NGA's server is down.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

import requests

OUT = Path(__file__).parent.parent / "scgraph" / "pipelines" / "data"
AGENT = {"User-Agent": "scgraph-hub-tables"}

WPI_URL = (
    "https://msi.nga.mil/api/publications/download"
    "?type=view&key=16920959/SFH00000/UpdatedPub150.csv"
)
OURAIRPORTS_COMMIT = "1cdbf9cbed1e47bed8f115ec173b91aeb999e44f"
OURAIRPORTS_URL = (
    "https://raw.githubusercontent.com/davidmegginson/ourairports-data/"
    f"{OURAIRPORTS_COMMIT}/airports.csv"
)
OPENSKY_RECORD = "https://zenodo.org/api/records/5815448"
OPENSKY_YEAR = "2021"
# Flights in the year, both directions together: about one a week each way
REGULAR_FLIGHTS = 104
AIRPORT_TYPES = {"large_airport", "medium_airport"}
WIKIDATA_URL = "https://query.wikidata.org/sparql"
# Classes of freight terminals; an item counts if it is an instance of one of them,
# has a position, and has no date of closure or demolition
TERMINAL_CLASSES = {
    "Q55493": "goods station",
    "Q492425": "container terminal",
    "Q57268313": "railway freight depot",
    "Q122972327": "rail terminal",
    "Q2297310": "dry port",
    "Q3984423": "freight terminal",
    "Q5501387": "freight terminal",
}


def download(url: str) -> bytes:
    response = requests.get(url, headers=AGENT, timeout=300)
    response.raise_for_status()
    return response.content


def build_ports(wpi: bytes) -> list[dict]:
    """The ports of the World Port Index with a position. A port is served by rail when
    its `Railway` field gives a size (small, medium, large)."""
    ports = []
    for row in csv.DictReader(io.StringIO(wpi.decode("utf-8-sig"))):
        if row["Latitude"] and row["Longitude"]:
            ports.append(
                {
                    "id": int(float(row["World Port Index Number"])),
                    "name": row["Main Port Name"],
                    "latitude": round(float(row["Latitude"]), 6),
                    "longitude": round(float(row["Longitude"]), 6),
                    "harbor_type": row["Harbor Type"],
                    "rail": int(row["Railway"] in ("Small", "Medium", "Large")),
                }
            )
    return ports


def fetch_flight_files(folder: Path) -> list[Path]:
    """The monthly OpenSky files of OPENSKY_YEAR in `folder`, downloaded when missing,
    each checked against the md5 that Zenodo gives."""
    folder.mkdir(parents=True, exist_ok=True)
    record = json.loads(download(OPENSKY_RECORD))
    paths = []
    for file in record["files"]:
        if not file["key"].startswith(f"flightlist_{OPENSKY_YEAR}"):
            continue
        path = folder / file["key"]
        if not path.exists():
            path.write_bytes(download(file["links"]["self"]))
        md5 = hashlib.md5(path.read_bytes()).hexdigest()
        if f"md5:{md5}" != file["checksum"]:
            raise ValueError(f"{path}: md5 {md5} differs from Zenodo's")
        paths.append(path)
    return sorted(paths)


def count_flights(paths: list[Path]) -> Counter:
    """Flights per (origin, destination) of airport codes; a flight without both ends,
    or with the same airport at both ends, is not counted."""
    flights = Counter()
    for path in paths:
        with gzip.open(path, "rt", newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                pair = row["origin"].strip(), row["destination"].strip()
                if all(pair) and pair[0] != pair[1]:
                    flights[pair] += 1
    return flights


def build_air(ourairports: bytes, flights: Counter) -> tuple[list, list]:
    """The airports and flights tables: the pairs of large or medium airports with
    regular flights (both directions together), and these airports, keyed by the
    OurAirports id."""
    by_code = {}
    for row in csv.DictReader(io.StringIO(ourairports.decode("utf-8"))):
        if row["type"] in AIRPORT_TYPES:
            for key in ("ident", "icao_code", "gps_code"):
                by_code.setdefault(row[key], row)
    by_code.pop("", None)
    pairs, airport = Counter(), {}
    for (origin, destination), n in flights.items():
        a, b = by_code.get(origin), by_code.get(destination)
        if a and b and a is not b:
            airport[a["id"]], airport[b["id"]] = a, b
            pairs[tuple(sorted((int(a["id"]), int(b["id"]))))] += n
    rows, used = [], {}
    for (a, b), n in sorted(pairs.items()):
        if n >= REGULAR_FLIGHTS:
            rows.append({"airport_a": a, "airport_b": b, "flights": n})
            used[a], used[b] = airport[str(a)], airport[str(b)]
    airports = [
        {
            "id": int(row["id"]),
            "code": row["ident"],
            "name": row["name"],
            "type": row["type"],
            "latitude": round(float(row["latitude_deg"]), 6),
            "longitude": round(float(row["longitude_deg"]), 6),
            "country": row["iso_country"],
        }
        for _, row in sorted(used.items())
    ]
    return airports, rows


def query_terminals() -> list[dict]:
    """The open freight terminals of Wikidata with a position (TERMINAL_CLASSES)."""
    classes = " ".join(f"wd:{q}" for q in TERMINAL_CLASSES)
    query = f"""
        SELECT DISTINCT ?item ?class ?label ?point WHERE {{
          VALUES ?class {{ {classes} }}
          ?item wdt:P31 ?class ; wdt:P625 ?point .
          FILTER NOT EXISTS {{ ?item wdt:P576 ?closed }}
          FILTER NOT EXISTS {{ ?item wdt:P3999 ?ended }}
          OPTIONAL {{ ?item rdfs:label ?label . FILTER(LANG(?label) = "en") }}
        }}"""
    response = requests.get(
        WIKIDATA_URL,
        params={"query": query, "format": "json"},
        headers=AGENT,
        timeout=300,
    )
    response.raise_for_status()
    terminals = {}
    for row in response.json()["results"]["bindings"]:
        point = row["point"]["value"]  # "Point(longitude latitude)"
        if not point.startswith("Point("):
            continue  # a position on another body than the Earth
        longitude, latitude = map(float, point[6:-1].split())
        q = int(row["item"]["value"].rsplit("/Q", 1)[1])
        terminals.setdefault(
            q,
            {
                "id": q,
                "name": row.get("label", {}).get("value", ""),
                "kind": TERMINAL_CLASSES[
                    row["class"]["value"].rsplit("/", 1)[1]
                ],
                "latitude": round(latitude, 6),
                "longitude": round(longitude, 6),
            },
        )
    return [terminals[q] for q in sorted(terminals)]


def write(name: str, rows: list[dict]) -> None:
    with open(OUT / name, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--opensky-dir", type=Path, required=True)
    parser.add_argument("--wpi", type=Path)
    arguments = parser.parse_args()
    if arguments.wpi:
        wpi = arguments.wpi.read_bytes()
        wpi = gzip.decompress(wpi) if wpi[:2] == b"\x1f\x8b" else wpi
    else:
        wpi = download(WPI_URL)
    print(f"World Port Index: sha256 {hashlib.sha256(wpi).hexdigest()}")
    write("ports.csv", build_ports(wpi))
    flights = count_flights(fetch_flight_files(arguments.opensky_dir))
    airports, rows = build_air(download(OURAIRPORTS_URL), flights)
    write("airports.csv", airports)
    write("flights.csv", rows)
    write("rail_terminals.csv", query_terminals())


if __name__ == "__main__":
    main()
