"""The network release that this version of scgraph loads.

A network release is a set of network files that scgraph publishes together, as the
assets of one GitHub release. Its tag names it, for example `networks-2026.11.20`. A
published network release is never changed.

This module pins one network release. `GeoGraph.load_geograph("europe")` loads the
file `europe` of this release, unless the caller passes another `version`. The same
version of scgraph therefore loads the same networks on every machine and at any date.
The module also records the digest of each file, so that `load_geograph` refuses a
download that is not the published file.

`utils/pin_network_release.py TAG` writes this module. Do not edit it by hand.
"""

# The tag of the pinned network release
TAG = "networks-2026.11.20-dev.1"
# The `content_sha256` of each network file of this release. A key is the name of a
# network. It ends with `.no_shapes` for the file without the shapes of the arcs.
# `load_geograph` checks each file that it downloads from this release against its
# value here.
CONTENT_SHA256 = {
    "africa.no_shapes": "1610d4797343dc60b0821e191f6af7b870c938623392f2245e14dadd2708f3b1",
    "africa": "3aeec56c95610d2eeef20175e6d8fcd932a82466d6e55bce2116524e0a10e11d",
    "east_southeast_asia.no_shapes": "b1a7fe2b27fc52413f6c2193eacad21cc8d751d2f8f725fc4436b14930ed02b0",
    "east_southeast_asia": "0e4eaed1038b0be8c7948cdca799ef78635137abaa77dfd760cdb6554ea4c7fa",
    "europe.no_shapes": "c56ba1be4e2248dabad7822c2ff863ff6f5d7db299225c3c13a90c667324b83a",
    "europe": "4212a887e6fa18071a1eb886a6a6ca69831255f3e09ddb14b5b7bc8cfa1ca6ad",
    "north_america.no_shapes": "d687911891588e625ff716ab37de85e8e851072e46cba5374ec5039a39aef2aa",
    "north_america": "a93f679b55238180d7f79916a0ca7adc5d285efcfb0d3e335d65469df6d68fab",
    "north_asia.no_shapes": "8802f709c269adb09f37025e2a1443c520eab7c9dde0b0c8542528c25baf4ad3",
    "north_asia": "35dfcc14d4644242465952095c243ded9e0ca4b5605b56e64469e08243c906cf",
    "oceania.no_shapes": "6a6929a9e1e285c2af8c6e78a88ef4f4a8be2af140aeb62478fce3ef75beeba8",
    "oceania": "1780c12e4156b213b1e022d306f2bc4e79df4d7709e9b3c9cc626da7ae5508d8",
    "south_america.no_shapes": "6741ff087614ec11890305f0a98365d0601de5f3a94a0aed79b4e27e062369ff",
    "south_america": "b0202f1e440383624d3f1448bf24f8920e6e325bbf6792c6a63f6d71f0ee7fb2",
    "west_south_asia.no_shapes": "04f609430b69e7ef4546720f88b5a9ea5737d4f424f06a3771a6397d9ef8255d",
    "west_south_asia": "54fcd30b5f566b92b3335bfb1187340fbd1d8f8d01add24e768410b8b8b7ad6a",
    "world_multimodal.no_shapes": "d28faf90fcd62b5b58886f6d0001c64af17ac7e8a0e01f26dc316412f3b71d4f",
    "world_multimodal": "08069ed255f01ff7b9b1ec0195588fc7ad72596133932b1af6742b398ae5e49a",
    "world_rail.no_shapes": "601f39c359eaa28a5faa5bff3cb59b78724a3ec5693c792c3542a874e031873e",
    "world_rail": "63d4e3a6b79989a6aee31e93ab4ece83f46963f673ba766f468675d2b02f518e",
    "world_sea.no_shapes": "6ae9a66acc9e0e52e2e21f61f744705a4801ef79df3cf4cca94e85319acf5fc0",
    "world_sea": "00b17075c2109edf055cdd947a43aae3452dea91f1fee2b3e06f53b87222bf0b",
}
# What `GeoGraph.list_geographs` says of each network of this release: its numbers of
# nodes and of arcs, the size in MB of its download with and without the shapes of the
# arcs, and the time of its newest source data.
NETWORKS = {
    "africa": {
        "nodes": 374498,
        "arcs": 758171,
        "download_mb": 20.3,
        "download_mb_without_shapes": 9.9,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "east_southeast_asia": {
        "nodes": 844874,
        "arcs": 1651243,
        "download_mb": 56.5,
        "download_mb_without_shapes": 22.6,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "europe": {
        "nodes": 1048594,
        "arcs": 2071242,
        "download_mb": 60.4,
        "download_mb_without_shapes": 28.3,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "north_america": {
        "nodes": 706899,
        "arcs": 1389147,
        "download_mb": 41.3,
        "download_mb_without_shapes": 19.0,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "north_asia": {
        "nodes": 182059,
        "arcs": 461399,
        "download_mb": 13.0,
        "download_mb_without_shapes": 5.1,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "oceania": {
        "nodes": 125567,
        "arcs": 338274,
        "download_mb": 9.2,
        "download_mb_without_shapes": 3.5,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "south_america": {
        "nodes": 273351,
        "arcs": 583495,
        "download_mb": 16.6,
        "download_mb_without_shapes": 7.4,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "west_south_asia": {
        "nodes": 544330,
        "arcs": 1086945,
        "download_mb": 30.2,
        "download_mb_without_shapes": 14.5,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "world_multimodal": {
        "nodes": 3335926,
        "arcs": 6241423,
        "download_mb": 196.9,
        "download_mb_without_shapes": 88.9,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "world_rail": {
        "nodes": 371303,
        "arcs": 976474,
        "download_mb": 28.9,
        "download_mb_without_shapes": 10.5,
        "data_up_to": "2026-11-02T00:59:53Z",
    },
    "world_sea": {
        "nodes": 43233,
        "arcs": 159174,
        "download_mb": 3.7,
        "download_mb_without_shapes": 1.2,
        "data_up_to": "None",
    },
}
