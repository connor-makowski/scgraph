"""Build the small tables of hubs that the multimodal pipelines read.

The tables are snapshots kept with the code, in `scgraph/pipelines/data/`, so that a
build reads the same hubs on every machine. This script makes them again from their
sources. Its output is a new snapshot, to be reviewed like any change of code:

- `ports.csv`: the ports of the World Port Index, with their number, position, harbour
  type and whether a railway serves them;
- `airports.csv` and `flights.csv`: the large and medium airports of OurAirports that
  have regular flights in 2021, and these flights. Three sources count the flights: the
  OpenSky flight list (all regions, but few receivers in China), BTS T-100 (every flight
  that touches the United States) and Eurostat (every flight that touches Europe);
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
import re
import zipfile
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
T100_URL = (
    "https://www.transtats.bts.gov/DL_SelectFields.aspx"
    "?gnoyr_VQ=FMG&QO_fu146_anzr=Nv4%20Pn44vr45"
)  # T-100 Segment (All Carriers)
EUROSTAT_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
)
# The countries whose airports report their routes to Eurostat; a country without a
# table for the year is skipped
EUROSTAT_COUNTRIES = (
    "at be bg ch cy cz de dk ee el es fi fr hr hu ie is it lt lu lv me mk mt nl no "
    "pl pt ro rs se si sk tr uk"
).split()
YEAR = "2021"
# Flights in the year, both directions together: about one a week each way
REGULAR_FLIGHTS = 104
AIRPORT_TYPES = {"large_airport", "medium_airport"}
# The OurAirports columns that match the airport codes of each source of flights
AIRPORT_CODES = {
    "opensky": ("ident", "icao_code", "gps_code"),
    "t100": ("iata_code",),
    "eurostat": ("ident", "icao_code", "gps_code"),
}
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
    """The monthly OpenSky files of YEAR in `folder`, downloaded when missing,
    each checked against the md5 that Zenodo gives."""
    folder.mkdir(parents=True, exist_ok=True)
    record = json.loads(download(OPENSKY_RECORD))
    paths = []
    for file in record["files"]:
        if not file["key"].startswith(f"flightlist_{YEAR}"):
            continue
        path = folder / file["key"]
        if not path.exists():
            path.write_bytes(download(file["links"]["self"]))
        md5 = hashlib.md5(path.read_bytes()).hexdigest()
        if f"md5:{md5}" != file["checksum"]:
            raise ValueError(f"{path}: md5 {md5} differs from Zenodo's")
        paths.append(path)
    return sorted(paths)


def count_opensky(paths: list[Path]) -> Counter:
    """Flights per (origin, destination) of ICAO codes in the OpenSky files; a flight
    without both ends, or with the same airport at both ends, is not counted."""
    flights = Counter()
    for path in paths:
        with gzip.open(path, "rt", newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                pair = row["origin"].strip(), row["destination"].strip()
                if all(pair) and pair[0] != pair[1]:
                    flights[pair] += 1
    return flights


def count_t100() -> Counter:
    """Departures performed in YEAR per (origin, destination) of IATA codes, by every
    carrier, on the flights that touch the United States (BTS T-100 Segment). The table
    is served by a form: the script reads the form, then asks for three columns.
    """
    session = requests.Session()
    session.headers.update(AGENT)
    page = session.get(T100_URL, timeout=300).text
    form = dict(
        re.findall(
            r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"',
            page,
        )
    )
    form |= {
        "cboGeography": "All",
        "cboYear": YEAR,
        "cboPeriod": "All",
        "btnDownload": "Download",
        "ORIGIN": "on",
        "DEST": "on",
        "DEPARTURES_PERFORMED": "on",
    }
    response = session.post(T100_URL, data=form, timeout=600)
    response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    flights = Counter()
    with archive.open(archive.namelist()[0]) as file:
        for row in csv.DictReader(io.TextIOWrapper(file, "utf-8-sig")):
            if row["ORIGIN"] != row["DEST"]:
                flights[row["ORIGIN"], row["DEST"]] += round(
                    float(row["DEPARTURES_PERFORMED"])
                )
    return flights


def count_eurostat() -> Counter:
    """Passenger and all-cargo flights in YEAR per pair of ICAO codes, both directions
    together, as the European airports report them (Eurostat tables `avia_par_xx` and
    `avia_gor_xx`). Two reporting countries count the same flights between them, so a
    pair keeps the larger of their counts."""
    flights = Counter()
    for country in EUROSTAT_COUNTRIES:
        reported = Counter()
        for table, measure in (
            ("avia_par", "CAF_PAS"),
            ("avia_gor", "CAF_FRM"),
        ):
            response = requests.get(
                f"{EUROSTAT_URL}{table}_{country}",
                params={
                    "freq": "A",
                    "unit": "FLIGHT",
                    "tra_meas": measure,
                    "time": YEAR,
                },
                headers=AGENT,
                timeout=300,
            )
            if response.status_code == 404:
                continue  # no such table for this country
            response.raise_for_status()
            data = response.json()
            # Every dimension but the pair has one category, so a value's index is the
            # position of its pair, for example "BE_EBLG_CN_ZGGG"
            pairs = {
                position: pair
                for pair, position in data["dimension"]["airp_pr"]["category"][
                    "index"
                ].items()
            }
            for position, n in data["value"].items():
                _, a, _, b = pairs[int(position)].split("_")
                if a != b:
                    reported[tuple(sorted((a, b)))] += n
        for pair, n in reported.items():
            flights[pair] = max(flights[pair], n)
    return flights


def build_air(
    ourairports: bytes, flights: dict[str, Counter]
) -> tuple[list, list]:
    """The airports and flights tables, keyed by the OurAirports id.

    `flights` holds, for each source of AIRPORT_CODES, the flights per pair of its
    codes. A pair of large or medium airports counts the flights of both directions
    together, and keeps the largest count among the sources. A pair has regular
    flights from REGULAR_FLIGHTS on; an airport is kept when it has regular flights.
    """
    rows = [
        row
        for row in csv.DictReader(io.StringIO(ourairports.decode("utf-8")))
        if row["type"] in AIRPORT_TYPES
    ]
    best = {}  # (id, id) -> (flights, source)
    for source, counts in flights.items():
        by_code = {}
        for row in rows:
            for key in AIRPORT_CODES[source]:
                by_code.setdefault(row[key], row)
        by_code.pop("", None)
        pairs = Counter()
        for (origin, destination), n in counts.items():
            a, b = by_code.get(origin), by_code.get(destination)
            if a and b and a is not b:
                pairs[tuple(sorted((int(a["id"]), int(b["id"]))))] += n
        for pair, n in pairs.items():
            if n > best.get(pair, (0, None))[0]:
                best[pair] = (n, source)
    regular = [
        {"airport_a": a, "airport_b": b, "flights": n, "source": source}
        for (a, b), (n, source) in sorted(best.items())
        if n >= REGULAR_FLIGHTS
    ]
    used = {a for row in regular for a in (row["airport_a"], row["airport_b"])}
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
        for row in sorted(rows, key=lambda row: int(row["id"]))
        if int(row["id"]) in used
    ]
    return airports, regular


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
    flights = {
        "opensky": count_opensky(fetch_flight_files(arguments.opensky_dir)),
        "t100": count_t100(),
        "eurostat": count_eurostat(),
    }
    airports, rows = build_air(download(OURAIRPORTS_URL), flights)
    write("airports.csv", airports)
    write("flights.csv", rows)
    write("rail_terminals.csv", query_terminals())


if __name__ == "__main__":
    main()
