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
TAG = "networks-2026.11.22-dev.2"
# The `content_sha256` of each network file of this release. A key is the name of a
# network. It ends with `.no_shapes` for the file without the shapes of the edges.
# `load_geograph` checks each file that it downloads from this release against its
# value here.
CONTENT_SHA256 = {
    "africa.no_shapes": "025c54703624ddad82da6e694d3bf89fcdd58c972de3fb00c8ca5aab9c8ce01c",
    "africa": "eb0dd0c9e2cdd40f826ccbe78f60b30676a6325cd6d24ba5b00fe05d1f389e72",
    "east_southeast_asia.no_shapes": "f05c35b9d6d5575d7ecdc95f3456e71ee6d8eaf25e6d32df49f9132d72c85a72",
    "east_southeast_asia": "fa536826618b15626a38611fac1b84454a5a4f091120ca5117983a395b364fc6",
    "europe.no_shapes": "4bcf146379080743f3001d68087c28ff032122f02e7ee1da5a97ef5744aa667b",
    "europe": "63ea4f4f4d125c7da7c416a5511f9f71d632830468fae5355555f31eca777e3c",
    "north_america.no_shapes": "7abc3064f814852ed9935421364bdddaf3ec57552bf2181165faad883a31c606",
    "north_america": "7e0784ea0084b068ce36aecbd134d9297cc62ceda9e5600f33a37870d8d0d8b2",
    "north_asia.no_shapes": "43cd2955e3fb3038c3dbbdd3783cc3b3b9c5e45362bf690c05f8e3e325914811",
    "north_asia": "e6110b2f33e8dd5ea5b329c97db09a9aba21d4c96581c2cfacd98b089649f5f9",
    "oceania.no_shapes": "b231713417f1488ae80a1c363491f54fb48880739bcbb137f2daaf812adcc38d",
    "oceania": "923032b52337e6f2bf619bc255ec7652b9626a899fe951a81d321afafe48e9f1",
    "south_america.no_shapes": "c0ce25928a2ee7a7cc849b9796400aeb528090af36f336cf34b183a5dc91f1bd",
    "south_america": "998804ce68d8a88f335afe3e3c851415884dee676a8ead5229edc297e72760e9",
    "west_south_asia.no_shapes": "611bad4a7a313ffe37fc9217b31f6a7e5f507cd1d8181ec9b15c139de35c14ae",
    "west_south_asia": "07c21abe84ed6afd144f048f59a19673d1da39ab100ce64d1088c374499190d3",
    "world_multimodal.no_shapes": "b8d207ab360cca9a22fcbe4beafe47b4a6b4f7f5d480ad9821c1f98b2129a945",
    "world_multimodal": "80df50763e02ff7175f383ef9516126f9c785fb64ea246e523471b0c739ef996",
    "world_rail.no_shapes": "8b865d3bace11a506f75b94684d00edb5b41fa62d9b4b1fd7d96635487480cea",
    "world_rail": "c9a38239e6b6321c3636ca264a4650003229df02f5475e7e0d6e0bbf85d9b4c0",
    "world_sea.no_shapes": "55348635ee75949884c6fcb3347a37831d58a79c2809d6ace095704487c4f74d",
    "world_sea": "768d9b7fe01a48fc880fab550c38eff6b288bd69eb078b892c3f1ca8bfcfb4c2",
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
        "description": "Roads, railways, sea lanes and flights of the world, joined at ports, airports and rail terminals: `geofabrik_multimodal` for the OpenStreetMap planet.",
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
