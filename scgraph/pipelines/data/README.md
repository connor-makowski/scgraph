# Hub tables

Small tables that the multimodal pipelines read (`step2_hub_connectors.HUB_TABLES`). They are snapshots kept
with the code, so that a build reads the same hubs on every machine.
`utils/build_hub_tables.py` makes them again from their sources; a new snapshot is reviewed
like any change of code. The change that brings a new snapshot also updates the `version`
of the table in `step2_hub_connectors.HUB_TABLES` and the counts below. It raises the `PIPELINE_VERSION` of
the pipelines that read the table, so that a cached network is built again.

To build a table again, run `python utils/build_hub_tables.py --opensky-dir DIR [--wpi FILE]`
(the docstring of the script explains `DIR` and `FILE`). The `version` of a table is a text.
The header of a network file records it as the version of the source, so it names the snapshot.
A build copies each table into its work folder. `read_ports`, `read_airports`,
`read_rail_terminals` and `read_flights` of `step2_hub_connectors` turn the rows into hubs, and
`join_networks_at_hubs` joins the networks at them. To add a hub, give a pipeline its own copy
of the table in its `SOURCES`, with a `url` that starts with http. The script would erase a row
that you add by hand.

| Table | Rows | Columns | Source | Licence |
|---|---|---|---|---|
| `ports.csv` | 3,807 | World Port Index number, name, position, harbour type, `rail` (1 when the `Railway` field gives a size) | NGA World Port Index (Pub. 150), file `UpdatedPub150.csv`, SHA-256 `315644f1e7796629…` | a work of the US government (`LicenseRef-US-Government-Work`) |
| `airports.csv` | 1,746 | OurAirports id, ICAO code, name, type, position, country | OurAirports `airports.csv` at commit `1cdbf9cb` of `davidmegginson/ourairports-data` | public domain |
| `flights.csv` | 14,483 | the two airport ids of a pair, flights between them in 2021 (both directions), the source of that count | OpenSky Network flight list, Zenodo record 5815448 (v21.12), the 12 months of 2021; US Bureau of Transportation Statistics, T-100 Segment (All Carriers), 2021; Eurostat tables `avia_par_*` and `avia_gor_*`, 2021; the last two read on 2026-11-17 | OpenSky: CC BY 4.0, cite Strohmeier et al., *Earth Syst. Sci. Data* 13, 357–366 (2021); T-100: a work of the US government; Eurostat: CC BY 4.0 |
| `rail_terminals.csv` | 898 | Wikidata number, English label, kind, position | Wikidata, items of seven classes of freight terminals, without a date of closure, query of 2026-11-16 | CC0 |

How each table is made:

- **Airports and flights.** Three sources count the flights of 2021 between two airports,
  both directions together:
  - the OpenSky list, all regions: a flight is one row with an origin and a destination;
  - BTS T-100, the flights that touch the United States: the departures performed, by
    every carrier;
  - Eurostat, the flights that touch Europe: the passenger and all-cargo flights that the
    European airports report. Each airport of a pair reports the flights between them;
    the larger report counts.

  Only the large and medium airports of OurAirports count, matched by their ICAO code
  (IATA code for T-100). A pair keeps the largest count among the sources. A pair with at
  least 104 flights (about one a week each way) has regular flights; the network joins it
  both ways. An airport is kept when it has regular flights.
- **Rail terminals.** Classes: goods station, container terminal, railway freight depot,
  rail terminal, dry port, freight terminal (two items). An item counts when it is an
  instance of one of them and has a position.

Known gaps, measured on 2026-11-16:

- No open source counts the flights inside mainland China, or between China and the rest
  of Asia: the OpenSky list has almost no receivers there. The Chinese airports have only
  their flights to the United States and Europe (Shanghai Pudong 17 regular routes, Beijing
  Capital 9, Chengdu Shuangliu 1). OpenFlights lists more routes, but stopped in June 2014
  and gives no counts.
- 2021 is a year of the COVID pandemic. Compared with the OpenSky list of 2022, the regular
  routes of the OpenSky list of 2021 miss 29 % of the regular routes between large and
  medium airports, which carry 8 % of the flights (measured on 2026-11-16).
- The rail flag of the World Port Index is unknown for many ports; Antwerpen, for example,
  has no rail flag.
- Wikidata lists few terminals in Germany and Italy (no Duisburg, no Verona among them).
