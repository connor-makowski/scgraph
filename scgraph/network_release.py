"""The network release that this version of scgraph loads.

A network release is a set of network files that scgraph publishes together, as the
assets of one GitHub release. Its tag names it, for example `networks-2026.11.20`. A
published network release is never changed.

This module pins one network release. `GeoGraph.load_geograph("europe")` loads the
file `europe` of this release, unless the caller passes another `network_release`. The same
version of scgraph therefore loads the same networks on every machine and at any date.
The module also records the digest of each file, so that `load_geograph` refuses a
download that is not the published file.

`utils/pin_network_release.py TAG` writes this module. Do not edit it by hand.
"""

# The tag of the pinned network release
TAG = "networks-2026.11.23-dev.2"
# The `content_sha256` of each network file of this release. A key is the name of a
# network. It ends with `.no_shapes` for the file without the shapes of the edges.
# `load_geograph` checks each file that it downloads from this release against its
# value here.
CONTENT_SHA256 = {
    "africa.no_shapes": "a3cce3dfd6944bd679bb573e8843f65fb76798edbb63c8008312f8e8b5d95b74",
    "africa": "8ae2f3e01716ca1ae07ff10e1de051818a6de18bee96429ddab0c39222f70797",
    "east_southeast_asia.no_shapes": "a5b8aa6fa4b58e6752558922165628a4e03062c6df6d7b34e1f0d8946590521d",
    "east_southeast_asia": "c4a22888d03db799c1ea7a519cedc52da049aa008e659144eb9de786184ffa79",
    "europe.no_shapes": "6e97fdbc8e44cd5f3ce1f3b770c47ad14bfd25d8657da1496e59e1478a6d2a66",
    "europe": "20012cb4c37bad10a4ee08fab294308dc36edeede4f23bf783d09309bf22a058",
    "north_america.no_shapes": "c14ec6c959e151bf0236378ebd3b08eedbe2960021d5e86337b733ce7565c0d9",
    "north_america": "62d0cfa2125d7761bc460cd22bc58e39f821b005a69811dd4497fdc1987b33b8",
    "north_asia.no_shapes": "76c860a652a5407bf1b0ac4df0c1793945e3f0554de596fca92b7adec30546e6",
    "north_asia": "030e6aa35eb84a49a867c6aca108b1a66a29edfd621f99f1a862154c24536cfe",
    "oceania.no_shapes": "a4ea80ea871d7b2ae9237ef0e4fba5c62efe7b56853dc4511c310294a561b5c2",
    "oceania": "af24f32b6750f43bf185803a0507a7a4632c8aac4e495777f2f8d9ad78030737",
    "south_america.no_shapes": "ab303127bf00b4015e6948bf55c8f3501a7c25b73b61e5178ae2b7710e6ea128",
    "south_america": "efcf8fde8e7c1aa0d9d1272029421e08e10ad70238a37291c8594693a8796ad8",
    "west_south_asia.no_shapes": "94223ae376715444a2706b82c167266c72b709692237ff45c10b4a6195502042",
    "west_south_asia": "fbac100845060c4d878c253ac28c5f8833671a7133cdd65cede4c9b73ab5eee3",
    "world_multimodal.no_shapes": "e74b3f41170db616061d3e34eeea548ba1ba51c2188a8507ea7f57e027291567",
    "world_multimodal": "926a857a7998aa1c113f7457cb6a5714c0b4d686cdf9f8b425237deab20fc688",
    "world_rail.no_shapes": "2eb5299e81265a361f381e18b55904ee05cffb7dfed5808779782e4c90cbdb2a",
    "world_rail": "c9807a872111a6932600e1d3e3ea66f757f958c02d13d8c5f23a122efe5282f2",
    "world_sea.no_shapes": "be06d817d25bcec16023fa6a7d504b383a6e728444951a993bf9b5de337ad58f",
    "world_sea": "405c992443cfe53428e4e1df1a1d5054dd3be2af64ab54a7bd606fbde2e552e9",
}
# What `GeoGraph.list_geographs` says of each network of this release: its numbers of
# nodes and of edges, the size in MB of its download with and without the shapes of the
# edges, the time of its newest source data (None when no source gives a time), and its
# description.
NETWORKS = {
    "africa": {
        "nodes": 378282,
        "edges": 765059,
        "download_mb": 20.3,
        "download_mb_without_shapes": 10.0,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -35 and 38 and longitudes -18 and 52, with every sea lane, port and airport of the world",
    },
    "east_southeast_asia": {
        "nodes": 857664,
        "edges": 1672040,
        "download_mb": 56.7,
        "download_mb_without_shapes": 23.0,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -11 and 55 and longitudes 92 and 150, with every sea lane, port and airport of the world",
    },
    "europe": {
        "nodes": 1056450,
        "edges": 2085191,
        "download_mb": 60.5,
        "download_mb_without_shapes": 28.5,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 34 and 72 and longitudes -25 and 45, with every sea lane, port and airport of the world",
    },
    "north_america": {
        "nodes": 712076,
        "edges": 1398583,
        "download_mb": 41.4,
        "download_mb_without_shapes": 19.1,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 7 and 84 and longitudes -170 and -50, with every sea lane, port and airport of the world",
    },
    "north_asia": {
        "nodes": 184239,
        "edges": 466049,
        "download_mb": 13.1,
        "download_mb_without_shapes": 5.1,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 40 and 78 and longitudes 45 and 180, with every sea lane, port and airport of the world",
    },
    "oceania": {
        "nodes": 125904,
        "edges": 339010,
        "download_mb": 9.2,
        "download_mb_without_shapes": 3.5,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -50 and 0 and longitudes 110 and 180, with every sea lane, port and airport of the world",
    },
    "south_america": {
        "nodes": 278024,
        "edges": 591053,
        "download_mb": 16.7,
        "download_mb_without_shapes": 7.5,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -57 and 13 and longitudes -82 and -34, with every sea lane, port and airport of the world",
    },
    "west_south_asia": {
        "nodes": 554802,
        "edges": 1106261,
        "download_mb": 30.4,
        "download_mb_without_shapes": 14.7,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 5 and 45 and longitudes 25 and 98, with every sea lane, port and airport of the world",
    },
    "world_multimodal": {
        "nodes": 3376285,
        "edges": 6313226,
        "download_mb": 197.8,
        "download_mb_without_shapes": 90.0,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "Roads, railways, sea lanes and flights of the world, joined at ports, airports and rail terminals: `osm_region_multimodal` for the OpenStreetMap planet.",
    },
    "world_rail": {
        "nodes": 378045,
        "edges": 996352,
        "download_mb": 29.1,
        "download_mb_without_shapes": 10.7,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "Railways and rail terminals of the world",
    },
    "world_sea": {
        "nodes": 43233,
        "edges": 159174,
        "download_mb": 3.7,
        "download_mb_without_shapes": 1.2,
        "data_up_to": None,
        "description": "Sea lanes and ports of the world",
    },
}
