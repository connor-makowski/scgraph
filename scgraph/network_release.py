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
TAG = "networks-2026.11.23-dev.1"
# The `content_sha256` of each network file of this release. A key is the name of a
# network. It ends with `.no_shapes` for the file without the shapes of the edges.
# `load_geograph` checks each file that it downloads from this release against its
# value here.
CONTENT_SHA256 = {
    "africa.no_shapes": "ad3be952f4a42f498413f682cb5697ced98548c3a126bdb13a2506f1472410c6",
    "africa": "c7a56a7e99e080df0671951204657f224d9001efd437b7285458cb0b65ad66e0",
    "east_southeast_asia.no_shapes": "0c44da538a43dcb7f7dcf8cbbdf9a62f38b4a28cd5e36992606b7b02fd45727f",
    "east_southeast_asia": "09009d9fee31cef898b66c6d38ee6891ca9067bcd8d29e39bbb4f851f186b010",
    "europe.no_shapes": "391456ef011c1cd4d28b71b7cd747f625099692f4e97e1d1c1a33c33401c1cfb",
    "europe": "b3671590aa87050b4a5314692af876abef88fda5d951dcaa6b5902c1fc6f1ff0",
    "north_america.no_shapes": "b99a3613a7077367e697b0b8e4ac2a484f64034127914e135ddd65ab156ff7a5",
    "north_america": "95973f50fed91b5b292423e9dc71c58162ef62cd62319ff4984d4b0559a20111",
    "north_asia.no_shapes": "da9b77be96e2af6ef2afff4d9d6c32f112bb4cd01f5424d6a07d0f92dc495111",
    "north_asia": "ec2abd8d0d7da6f20fc2a2b1704e4761bc0111916bdf7ee0f194df2e74322c74",
    "oceania.no_shapes": "ed87c44c6a90a4a9360042c0cc14c6a1b9b326ecd6c01def9546cd51f7193cf1",
    "oceania": "e280164dda7f80d6424db0281bccff70a9e513e03e467b39b6e67dcc8cd9950a",
    "south_america.no_shapes": "5e738b5e90c7921b9a432a9f8e527db958bd0165f1579f20d12f72f482bf5567",
    "south_america": "d5cb6aa39e2bc90cee8352c3f2d54e4ad847abc6067fa5161f7201d54d57650e",
    "west_south_asia.no_shapes": "36e767dc8989061717663d493dfdd8c591efa14ea1ccf37afcf0016a7b08558b",
    "west_south_asia": "b490e9cc526ee6e52786b3beaa6a4a8c980fb5558f0e73c5edc1a6f05d648fdd",
    "world_multimodal.no_shapes": "b9f645fe154bffdb0f57b7d6b5c9e14228785dd8bf14eaaf112b908e1f962cb5",
    "world_multimodal": "cf6a3bac915315c5d5b0cc2af0a7cba9f35253fea704c34b1c6f70fe0918de71",
    "world_rail.no_shapes": "b48f49587d11e2873131d02c51cdd13f15b2906ca1337e7cf79ae7d130bcd2d1",
    "world_rail": "1c9b6e1bc5c9bc86bd356e322968d645eff611fdc87a6eeae8fc5671e15d1c3d",
    "world_sea.no_shapes": "96f237ac41bded06e65f8966000646dbd80d80e3319c9b87ff88ad73fdf45287",
    "world_sea": "081ac0c9fb9fa93b4a54a0dc2ef02664cb99a0b214e6b91a801b15d1b6af9c02",
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
