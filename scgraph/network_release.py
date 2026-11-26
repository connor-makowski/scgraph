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
TAG = "networks-2026.11.25-dev.1"
# The `content_sha256` of each network file of this release. A key is the name of a
# network. It ends with `.no_shapes` for the file without the shapes of the edges.
# `load_geograph` checks each file that it downloads from this release against its
# value here.
CONTENT_SHA256 = {
    "africa.no_shapes": "c74d12c50edb92ae8c6d2611c2f2cbb5ca55f6438064e96c31e74c44936e7253",
    "africa": "3fd0ee4ab70b178333a64436e3ee414cbd8a6fd0138c8856a2e8c5c41e6be698",
    "east_southeast_asia.no_shapes": "1fb1eb46333e44c27ddc310b21cafcf0192f59b7ccbed49e956dc23efe8ba140",
    "east_southeast_asia": "800e09312c25e932adaec316e5dabf2b48d725afe72553d7e1fd213c4482b96e",
    "europe.no_shapes": "d789192af8412aa292875db019e0542aad01922550ea8fa841dc6411be1477fe",
    "europe": "50f5ba2da9d0b2be89d18130be034556ce3ba9c4cf2956e1b57803c888d72416",
    "north_america.no_shapes": "7d1974ade9a7990d41d37f43fb4b26cab651db3484877b79361a740a09278cad",
    "north_america": "3201e19448f59a063c66afe0bba22ff24ef1d3734a6f4c8b5b158e426d977373",
    "north_asia.no_shapes": "9f3d420592515da4b9310f05c01a31a9b037fdbaa08a022b33e7abeb11c48283",
    "north_asia": "86bdacb4947b120768529b869724db0cdf7b9144f81ea98b3d16f7136e4e4ded",
    "oceania.no_shapes": "6d8d1200756f5c43df7acc749dc05a1f6c8778d66b493894ade35a7dc1e4be95",
    "oceania": "99548f67b15b883c7f2569af7e2deaa1eb4e47d4bc22af95688ee21010c21fb1",
    "south_america.no_shapes": "628a5ceecf05ed6077d5529300f30c6580ecf7767efa3719a40c33fac6caf0c0",
    "south_america": "6745eb8aab3b332b10cf165da3e527dcfea68db41a2d0e1ed12d568746abe402",
    "west_south_asia.no_shapes": "360bb9570f5649ec35104438c0259dbf1e9e7fc21b43a803dbdb609f5965d31c",
    "west_south_asia": "ade30ff138f9cf4bf4e3baab04f38cf0a693b2c6427411df4d2046e17bd8876a",
    "world_multimodal.no_shapes": "9ef4ec32dcbcd8e2239228e6a735c47ad4097900bfcb180102a4c202aac1b2ec",
    "world_multimodal": "e684a761d4d963698f65b008e389eac5dd663886aa387c28ea72c62b9c9cdc06",
    "world_rail.no_shapes": "5d6eec52ad73bb14043db79248b7f47e21a0ea30bc7b21de0bbafe2096c522a5",
    "world_rail": "cc6a5629565c7c3e14c51b591bb549c925670e3fcaed69ba779612a7e73103c2",
    "world_sea.no_shapes": "a8b004fa79ff6abc75aa01d99766d30994a5b7c7a3636d7afd7c2a7fde1c951e",
    "world_sea": "637323b42501e61c0428f17afc43cb6abcff3858732778228a408290b82c4722",
}
# What `GeoGraph.list_geographs` says of each network of this release: its numbers of
# nodes and of edges, the size in MB of its download with and without the shapes of the
# edges, the time of its newest source data (None when no source gives a time), and its
# description.
NETWORKS = {
    "africa": {
        "nodes": 407115,
        "edges": 803768,
        "download_mb": 20.6,
        "download_mb_without_shapes": 10.3,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -35 and 38 and longitudes -18 and 52, with every sea lane, port and airport of the world",
    },
    "east_southeast_asia": {
        "nodes": 903156,
        "edges": 1732293,
        "download_mb": 57.1,
        "download_mb_without_shapes": 23.4,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -11 and 55 and longitudes 92 and 150, with every sea lane, port and airport of the world",
    },
    "europe": {
        "nodes": 1470292,
        "edges": 2679590,
        "download_mb": 64.1,
        "download_mb_without_shapes": 33.7,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 34 and 72 and longitudes -25 and 45, with every sea lane, port and airport of the world",
    },
    "north_america": {
        "nodes": 878406,
        "edges": 1640913,
        "download_mb": 42.8,
        "download_mb_without_shapes": 21.1,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 7 and 84 and longitudes -170 and -50, with every sea lane, port and airport of the world",
    },
    "north_asia": {
        "nodes": 210112,
        "edges": 502591,
        "download_mb": 13.3,
        "download_mb_without_shapes": 5.4,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 40 and 78 and longitudes 45 and 180, with every sea lane, port and airport of the world",
    },
    "oceania": {
        "nodes": 147794,
        "edges": 367546,
        "download_mb": 9.4,
        "download_mb_without_shapes": 3.8,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -50 and 0 and longitudes 110 and 180, with every sea lane, port and airport of the world",
    },
    "south_america": {
        "nodes": 364990,
        "edges": 712123,
        "download_mb": 17.4,
        "download_mb_without_shapes": 8.5,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -57 and 13 and longitudes -82 and -34, with every sea lane, port and airport of the world",
    },
    "west_south_asia": {
        "nodes": 584416,
        "edges": 1144709,
        "download_mb": 30.7,
        "download_mb_without_shapes": 15.0,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 5 and 45 and longitudes 25 and 98, with every sea lane, port and airport of the world",
    },
    "world_multimodal": {
        "nodes": 4143454,
        "edges": 7403938,
        "download_mb": 204.2,
        "download_mb_without_shapes": 99.2,
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
