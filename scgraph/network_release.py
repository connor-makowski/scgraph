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
TAG = "networks-2026.11.27-dev.1"
# The `content_sha256` of each network file of this release. A key is the name of a
# network. It ends with `.no_shapes` for the file without the shapes of the edges.
# `load_geograph` checks each file that it downloads from this release against its
# value here.
CONTENT_SHA256 = {
    "africa.no_shapes": "245564b68486cd82767d9e2a8c88e6caa336e05b7bfae93e313cd660b76d0d61",
    "africa": "d974e326655f51af6cfd6647e45d406ab3df8b5fa499a64341538d7f3aaf2117",
    "east_southeast_asia.no_shapes": "4a1ca68f9e315bbdf2886f56e9158ac3bce16653952fc13364f5a0ebb33dc4bd",
    "east_southeast_asia": "3294d905d80d02865ccfd98ab704c4b0674f86b9576c92936a3947477fb58cc7",
    "europe.no_shapes": "32b90ad8a61cbcf936c6cd815c5d90380ef5aaebbdb89208c3b4f2faa3625888",
    "europe": "9868e7ce61823afcf73161934109746054b749f714e60de00d6e17a91a8e5fe3",
    "north_america.no_shapes": "b1e4b9b1f6a5dcd2a8e372b3410a3be08f00ee1a0ba3bdec819df6d01ec956e3",
    "north_america": "7fc7c839ff3ecc6a03de53a3a7b8b5edd4c068585d989fcbc784553d97944196",
    "north_asia.no_shapes": "90973cda357869961957b8abd85dc4a8305da580cba29d28fb67f59b925ceea6",
    "north_asia": "dc41f4186078607e48020740391072492efaed8d572134a9a3971f799b676836",
    "oceania.no_shapes": "f6e53397e020be6808453e96775d35216b3803c0d08970c5998dc8d904ab26eb",
    "oceania": "df05d75fc2cec7b0bc1c8c82e9312af120c07b9e9d9dc261665d769230c37384",
    "south_america.no_shapes": "75431ed860b1e3516a4d05edace3a3b22945121aa4d4a58f66838d5e7cca62eb",
    "south_america": "a4b6c40b02209d15daaff884c5065bb26b8181c832c2c8a6ddb1a89fe9c40d5a",
    "west_south_asia.no_shapes": "bccf0f06ab28269ef9b10016fdd1b15749d3823c22b5b586a71368d0160506ef",
    "west_south_asia": "bfe9064799c35d35cf32a7b7fc1b188ccc3d69c58bac5ca424d64a0e9b8ed1a9",
    "world_multimodal.no_shapes": "204ae7f85921ce40e6947452bf445302c8fcd48e66fdc7b0d94c189b710ab576",
    "world_multimodal": "188e0d0a3a459f28f45374d83fb2aa74f6a69548336a8a92ccf05109af2c4ec0",
    "world_rail.no_shapes": "c5b2f459eb31dca4e73e1b8f415379b45e8082e4cca0ae8aee180b11eaf54efd",
    "world_rail": "bcc0d0b597eeefd0c2673564f7dec52769463fe1d59406aca0fc6f10025f5c0f",
    "world_sea.no_shapes": "acdb3f6b57bc50ec752cd31581e31d218163dfacb07b5fafc13d511a6675061b",
    "world_sea": "95ed29c18b623a25638d928867674600c45878fecbce9be3b14e1cba926669f6",
}
# What `GeoGraph.list_geographs` says of each network of this release: its numbers of
# nodes and of edges, the size in MB of its download with and without the shapes of the
# edges, the time of its newest source data (None when no source gives a time), and its
# description.
NETWORKS = {
    "africa": {
        "nodes": 407116,
        "edges": 803770,
        "download_mb": 18.1,
        "download_mb_without_intermediate_nodes": 10.3,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -35 and 38 and longitudes -18 and 52, with every sea lane, port and airport of the world",
    },
    "east_southeast_asia": {
        "nodes": 903157,
        "edges": 1732295,
        "download_mb": 50.9,
        "download_mb_without_intermediate_nodes": 23.4,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -11 and 55 and longitudes 92 and 150, with every sea lane, port and airport of the world",
    },
    "europe": {
        "nodes": 1470293,
        "edges": 2679592,
        "download_mb": 58.1,
        "download_mb_without_intermediate_nodes": 33.7,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 34 and 72 and longitudes -25 and 45, with every sea lane, port and airport of the world",
    },
    "north_america": {
        "nodes": 878407,
        "edges": 1640915,
        "download_mb": 38.9,
        "download_mb_without_intermediate_nodes": 21.1,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 7 and 84 and longitudes -170 and -50, with every sea lane, port and airport of the world",
    },
    "north_asia": {
        "nodes": 210113,
        "edges": 502593,
        "download_mb": 11.2,
        "download_mb_without_intermediate_nodes": 5.4,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 40 and 78 and longitudes 45 and 180, with every sea lane, port and airport of the world",
    },
    "oceania": {
        "nodes": 147795,
        "edges": 367548,
        "download_mb": 7.6,
        "download_mb_without_intermediate_nodes": 3.8,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -50 and 0 and longitudes 110 and 180, with every sea lane, port and airport of the world",
    },
    "south_america": {
        "nodes": 364991,
        "edges": 712125,
        "download_mb": 15.1,
        "download_mb_without_intermediate_nodes": 8.5,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes -57 and 13 and longitudes -82 and -34, with every sea lane, port and airport of the world",
    },
    "west_south_asia": {
        "nodes": 584417,
        "edges": 1144711,
        "download_mb": 27.3,
        "download_mb_without_intermediate_nodes": 15.0,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "The part of world_multimodal between latitudes 5 and 45 and longitudes 25 and 98, with every sea lane, port and airport of the world",
    },
    "world_multimodal": {
        "nodes": 4143455,
        "edges": 7403940,
        "download_mb": 186.6,
        "download_mb_without_intermediate_nodes": 99.2,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "Roads, railways, sea lanes and flights of the world, joined at ports, airports and rail terminals: `osm_region_multimodal` for the OpenStreetMap planet.",
    },
    "world_rail": {
        "nodes": 378045,
        "edges": 996352,
        "download_mb": 24.6,
        "download_mb_without_intermediate_nodes": 10.7,
        "data_up_to": "2026-11-02T00:59:53Z",
        "description": "Railways and rail terminals of the world",
    },
    "world_sea": {
        "nodes": 43234,
        "edges": 159176,
        "download_mb": 2.4,
        "download_mb_without_intermediate_nodes": 1.2,
        "data_up_to": None,
        "description": "Sea lanes and ports of the world",
    },
}
