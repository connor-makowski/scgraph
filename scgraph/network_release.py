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
TAG = "networks-2026.11.20-dev.2"
# The `content_sha256` of each network file of this release. A key is the name of a
# network. It ends with `.no_shapes` for the file without the shapes of the arcs.
# `load_geograph` checks each file that it downloads from this release against its
# value here.
CONTENT_SHA256 = {
    "africa.no_shapes": "b400e432b673d4fae1d4b88776955a71818c8818e521f327666dafd07b5c8326",
    "africa": "df86660b0fa3bbeea525f72a017956f599cbe082ef96105b2f65eca7e50085cf",
    "east_southeast_asia.no_shapes": "6e7c9aabfa9de13e1c2cdd0169743304f06728054e53d3b429d1459a029b2ca0",
    "east_southeast_asia": "0f24370876c70e2fc451ccfed1d631e2fab4d285b9fcf7de8021aebe70cb4c93",
    "europe.no_shapes": "4be7a003971d728c54362de5ae0ed8c63b98a60259dd552c92e4030ae4f555d0",
    "europe": "5dafa1c37d57bb89aeab601c333c72feb8235c8cab24ac0b4cbf380aec26c899",
    "north_america.no_shapes": "b47f0e948350a5554315d6757c5e2f97895f304c2454ff1a2cbb71b1707c354a",
    "north_america": "40f7d27aeaa2cb930b33f15f3052966fd5c10322f72964347a6835b79df994fd",
    "north_asia.no_shapes": "daec313e716a6aec9994ab3ce18acdbab1f3de9477553b4bd2e2f3e490bfaef3",
    "north_asia": "ac487ab7a2c09d5a9fa50525566a974207228bffdec390460a9410c6b70a7bfb",
    "oceania.no_shapes": "9e9585d0e83b82dbdca891daf5f4b1d1499d6b0f0288fd674752937547a68090",
    "oceania": "0a73791596c51e0b3ba9225f07309ac7818577b33389b763757d09056d1f5399",
    "south_america.no_shapes": "d1400251f27186e3b1d29abf5d41c2cdf1691c663537e7e177a52ab1d51b172d",
    "south_america": "55f18018a6534f3d9920470edd6cf93a2505776989260ac2ede8c4c651e0ccb1",
    "west_south_asia.no_shapes": "9b853fb661bf7e17a868a2a7009e59e4dacd3dc7627e2ee418acae2da8c5f91e",
    "west_south_asia": "297d811567e80ea9cf897f660101085db6f4c2af58c72eb52a11e8ece5c0ae5b",
    "world_multimodal.no_shapes": "2804569c160b8bf64e858fa4a954d276956b60f5cb8635b7ba9c8e697840fb98",
    "world_multimodal": "2bb9b71be389c190f49a0f4b302ec285df4b554b30fd2ae1695ea05b1241f2a8",
    "world_rail.no_shapes": "8585069719899b528af232e256f7a9fcf4700a6cbd9559459d46d96b704d3818",
    "world_rail": "052cc2a8b056652d17f6b351ad8195307130691fc1a235560f4f40738555f74a",
    "world_sea.no_shapes": "d21f90d1b382aae07014ca3b50a601ff05883e0b3e4fda84c52c1e14214696b2",
    "world_sea": "de354dff84af649763116b2234f2e9f73d2125c12a4e8d17efd52850dbd486ff",
}
# What `GeoGraph.list_geographs` says of each network of this release: its numbers of
# nodes and of arcs, the size in MB of its download with and without the shapes of the
# arcs, and the time of its newest source data (None when no source gives a time).
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
        "data_up_to": None,
    },
}
