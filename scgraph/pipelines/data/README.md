# Hub tables

Small tables that the multimodal pipelines read (`hubs.TABLES`). They are snapshots kept
with the code, so that a build reads the same hubs on every machine.
`utils/build_hub_tables.py` makes them again from their sources; a new snapshot is reviewed
like any change of code.

| Table | Rows | Columns | Source | Licence |
|---|---|---|---|---|
| `ports.csv` | 3,807 | World Port Index number, name, position, harbour type, `rail` (1 when the `Railway` field gives a size) | NGA World Port Index (Pub. 150), file `UpdatedPub150.csv`, SHA-256 `315644f1e7796629…` | not stated (`NOASSERTION`); a work of the US government |
| `airports.csv` | 1,191 | OurAirports id, ICAO code, name, type, position, country | OurAirports `airports.csv` at commit `1cdbf9cb` of `davidmegginson/ourairports-data` | public domain |
| `flights.csv` | 10,523 | the two airport ids of a pair, flights between them in 2021 (both directions) | OpenSky Network flight list, Zenodo record 5815448 (v21.12), the 12 months of 2021 | CC BY 4.0: cite Strohmeier et al., *Earth Syst. Sci. Data* 13, 357–366 (2021) |
| `rail_terminals.csv` | 898 | Wikidata number, English label, kind, position | Wikidata, items of seven classes of freight terminals, without a date of closure, query of 2026-11-16 | CC0 |

How each table is made:

- **Airports and flights.** A flight is one row of the OpenSky list with an origin and a
  destination. Only the large and medium airports of OurAirports count, matched by their
  ICAO code. A pair of airports with at least 104 flights in 2021, both directions together
  (about one a week each way), has regular flights; the network joins it both ways. An
  airport is kept when it has regular flights.
- **Rail terminals.** Classes: goods station, container terminal, railway freight depot,
  rail terminal, dry port, freight terminal (two items). An item counts when it is an
  instance of one of them and has a position.

Known gaps, measured on 2026-11-16:

- The OpenSky list of 2021 has no flight at the airports of mainland China (Shanghai Pudong,
  Beijing Capital, Chengdu, Hangzhou) and 9 at Memphis. The flights table therefore has no
  route there.
- Compared with 2022, the regular routes of 2021 miss 29 % of the regular routes between
  large and medium airports, which carry 8 % of the flights (lab experiment E69).
- The rail flag of the World Port Index is unknown for many ports; Antwerpen, for example,
  has no rail flag.
- Wikidata lists few terminals in Germany and Italy (no Duisburg, no Verona among them).
