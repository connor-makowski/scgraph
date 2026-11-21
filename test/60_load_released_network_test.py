"""`GeoGraph.load_geograph` with the name of a released network.

A network release is a set of network files published under one tag. Each file is
compressed with gzip. The tests replace the download: the fixture `releases`
holds the files of fake network releases. Two tests download a real file of the
pinned network release: the release that `scgraph.network_release` names.
"""

import gzip
import io
import types

import pytest
import requests

from scgraph import GeoGraph, network_release

# A tag that is not the pinned network release
OTHER_TAG = "networks-2000.01.01"
EUROPE_FILE = f"{OTHER_TAG}/europe.scgraph.gz"
EUROPE_FILE_WITHOUT_SHAPES = f"{OTHER_TAG}/europe.no_shapes.scgraph.gz"
RELEASES_URL = "https://github.com/connor-makowski/scgraph/releases/download/"


def _small_network():
    # Two road nodes, and one sea node joined to the second road node. The
    # edge between the road nodes has a shape with one point.
    return GeoGraph(
        graph=[{1: 2.0}, {0: 2.0, 2: 3.0}, {1: 3.0}],
        nodes=[[0, 0], [0, 1], [1, 1]],
        intermediate_nodes=[{1: [[0.5, 0.5]]}, {}, {}],
        node_modes=[0, 0, 1],
        modes=[{"name": "road"}, {"name": "sea"}],
    )


def _compress_small_network(folder, shapes=True):
    """The small network as a file of a network release: a network file, compressed
    with gzip."""
    file = folder / "small.scgraph"
    _small_network().save_as_scgraph(str(file), save_intermediate_nodes=shapes)
    return gzip.compress(file.read_bytes())


def _road_route(network):
    return network.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 1},
    )["coordinate_path"]


def _list_files(folder):
    return {
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def releases(monkeypatch):
    """The fake network releases. `releases.files` maps the end of a URL,
    `TAG/FILE`, to the bytes of the file, or to the HTTP status of a refusal.
    A request for another URL gets the status 404. `releases.requested` lists
    the end of each requested URL."""
    releases = types.SimpleNamespace(files={}, requested=[])

    def get(url, **kwargs):
        end = url.removeprefix(RELEASES_URL)
        releases.requested.append(end)
        answer = releases.files.get(end, 404)
        response = requests.Response()
        response.status_code = answer if isinstance(answer, int) else 200
        response.raw = io.BytesIO(b"" if isinstance(answer, int) else answer)
        return response

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.delenv("SCGRAPH_OFFLINE", raising=False)
    return releases


@pytest.fixture(scope="module")
def world_sea():
    # A real download of 1.2 MB from the pinned network release.
    return GeoGraph.load_geograph("world_sea", load_intermediate_nodes=False)


def test_first_load_downloads_the_network_file_of_the_network_release(
    releases, cache, tmp_path
):
    releases.files[EUROPE_FILE] = _compress_small_network(tmp_path)

    europe = GeoGraph.load_geograph(
        "europe", str(cache), network_release=OTHER_TAG
    )

    assert sorted(europe.nodes) == [[0, 0], [0, 1], [1, 1]]


def test_later_loads_read_the_cache_without_a_request(
    releases, cache, tmp_path
):
    releases.files[EUROPE_FILE] = _compress_small_network(tmp_path)
    GeoGraph.load_geograph("europe", str(cache), network_release=OTHER_TAG)

    GeoGraph.load_geograph("europe", str(cache), network_release=OTHER_TAG)

    assert releases.requested == [EUROPE_FILE]


def test_a_cached_file_of_one_network_release_does_not_serve_another(
    releases, cache, tmp_path
):
    releases.files[EUROPE_FILE] = _compress_small_network(tmp_path)
    GeoGraph.load_geograph("europe", str(cache), network_release=OTHER_TAG)

    with pytest.raises(FileNotFoundError):
        GeoGraph.load_geograph(
            "europe", str(cache), network_release="networks-2000.01.02"
        )


def test_the_default_network_release_is_the_pinned_one(world_sea):
    # Shanghai to Savannah
    route = world_sea.get_shortest_path(
        origin_node={"latitude": 31.23, "longitude": 121.47},
        destination_node={"latitude": 32.08, "longitude": -81.09},
    )

    assert round(route["length"], 3) == 19264.189


def test_list_geographs_lists_the_networks_of_the_pinned_network_release(
    world_sea,
):
    listed = GeoGraph.list_geographs()

    cached = {network["name"]: network["cached"] for network in listed}
    assert cached["world_sea"] and "africa" in cached


# `list_geographs` makes no request. It says enough of each network for a user
# to choose one: what the network holds, and the size of its download.
def test_list_geographs_describes_each_released_network(cache):
    released = [
        network
        for network in GeoGraph.list_geographs(cache)
        if network["kind"] == "released"
    ]

    assert all(network["description"] for network in released)
    assert all(
        network["download_mb"] > network["download_mb_without_shapes"] > 0
        for network in released
    )


# The description of a part of the world gives its rectangle. The rectangle is
# the bbox that derives the network from the world file.
def test_the_description_of_a_part_of_the_world_gives_its_bbox(cache):
    from scgraph.pipelines.derived_networks import DERIVED_NETWORKS

    listed = {
        network["name"]: network for network in GeoGraph.list_geographs(cache)
    }

    for name, selection in DERIVED_NETWORKS.items():
        if "bbox" in selection:
            south, west, north, east = selection["bbox"]
            assert (
                f"latitudes {south} and {north} and longitudes {west} and {east}"
                in listed[name]["description"]
            )


def test_each_network_of_3_6_0_names_the_released_network_that_supersedes_it(
    cache,
):
    listed = {
        network["name"]: network for network in GeoGraph.list_geographs(cache)
    }
    built_in = [n for n in listed.values() if n["kind"] == "built-in"]

    assert len(built_in) == 7
    assert all(
        listed[network["superseded_by"]]["kind"] == "released"
        for network in built_in
    )


# Three tests below load the network lazily: the file is fetched at the first
# use of the network, with the same arguments.
def test_a_load_without_intermediate_nodes_has_no_edge_shapes(
    releases, cache, tmp_path
):
    releases.files[EUROPE_FILE_WITHOUT_SHAPES] = _compress_small_network(
        tmp_path, shapes=False
    )

    europe = GeoGraph.load_geograph(
        "europe",
        str(cache),
        network_release=OTHER_TAG,
        load_intermediate_nodes=False,
        lazy=True,
    )

    # The file with shapes would add the point (0.5, 0.5).
    assert _road_route(europe) == [[0, 0], [0, 0], [0, 1], [0, 1]]


def test_the_cache_keeps_the_file_with_shapes_and_the_file_without(
    releases, cache, tmp_path
):
    releases.files[EUROPE_FILE_WITHOUT_SHAPES] = _compress_small_network(
        tmp_path, shapes=False
    )
    releases.files[EUROPE_FILE] = _compress_small_network(tmp_path)
    GeoGraph.load_geograph(
        "europe",
        str(cache),
        network_release=OTHER_TAG,
        load_intermediate_nodes=False,
    )

    europe = GeoGraph.load_geograph(
        "europe", str(cache), network_release=OTHER_TAG
    )

    assert [0.5, 0.5] in _road_route(europe)


def test_modes_loads_the_nodes_of_these_modes_only(releases, cache, tmp_path):
    releases.files[EUROPE_FILE] = _compress_small_network(tmp_path)

    roads = GeoGraph.load_geograph(
        "europe",
        str(cache),
        network_release=OTHER_TAG,
        modes=["road"],
        lazy=True,
    )

    assert sorted(roads.nodes) == [[0, 0], [0, 1]]


def test_a_network_is_loaded_again_by_the_digest_of_its_file(
    releases, cache, tmp_path
):
    releases.files[EUROPE_FILE] = _compress_small_network(tmp_path)
    europe = GeoGraph.load_geograph(
        "europe", str(cache), network_release=OTHER_TAG
    )
    info = GeoGraph.get_scgraph_info(europe.scgraph_file)

    again = GeoGraph.load_geograph(
        "europe",
        str(cache),
        network_release=OTHER_TAG,
        content_sha256=info["content_sha256"],
    )

    assert sorted(again.nodes) == [[0, 0], [0, 1], [1, 1]]


def test_content_sha256_refuses_a_file_with_another_digest(
    releases, cache, tmp_path
):
    releases.files[EUROPE_FILE] = _compress_small_network(tmp_path)
    europe = GeoGraph.load_geograph(
        "europe",
        str(cache),
        network_release=OTHER_TAG,
        content_sha256="0" * 64,
        lazy=True,
    )

    with pytest.raises(ValueError, match="content_sha256"):
        europe.load()


def test_the_pinned_network_release_refuses_a_file_that_scgraph_does_not_record(
    releases, cache, tmp_path
):
    # `scgraph.network_release` records the digest of each file of the pinned
    # network release. The small network is not one of these files.
    default_file = f"{network_release.TAG}/europe.scgraph.gz"
    releases.files[default_file] = _compress_small_network(tmp_path)

    with pytest.raises(ValueError, match="content_sha256"):
        GeoGraph.load_geograph("europe", str(cache))

    assert _list_files(cache) == set()


def _cut_short(compressed):
    return compressed[:-20]


def _change_one_byte(compressed):
    content = bytearray(gzip.decompress(compressed))
    content[-1] ^= 1
    return gzip.compress(content)


def _replace_by_a_web_page(compressed):
    return b"<html>Not found</html>"


@pytest.mark.parametrize(
    "damage", [_cut_short, _change_one_byte, _replace_by_a_web_page]
)
def test_a_damaged_download_is_refused_and_leaves_no_file_in_the_cache(
    releases, cache, tmp_path, damage
):
    releases.files[EUROPE_FILE] = damage(_compress_small_network(tmp_path))

    with pytest.raises(ValueError):
        GeoGraph.load_geograph("europe", str(cache), network_release=OTHER_TAG)

    assert _list_files(cache) == set()


def test_local_files_only_refuses_a_network_that_is_not_in_the_cache(
    releases, cache, tmp_path
):
    releases.files[EUROPE_FILE] = _compress_small_network(tmp_path)

    with pytest.raises(FileNotFoundError):
        GeoGraph.load_geograph(
            "europe",
            str(cache),
            network_release=OTHER_TAG,
            local_files_only=True,
        )

    assert releases.requested == []


@pytest.mark.parametrize(
    "status, error", [(404, FileNotFoundError), (503, ConnectionError)]
)
def test_a_refused_download_raises_the_error_of_its_status(
    releases, cache, status, error
):
    releases.files[EUROPE_FILE] = status

    with pytest.raises(error):
        GeoGraph.load_geograph("europe", str(cache), network_release=OTHER_TAG)


@pytest.mark.parametrize("tag", ["../..", "networks/1", ""])
def test_a_network_release_that_is_not_a_tag_is_refused_before_any_request(
    releases, cache, tag
):
    with pytest.raises(ValueError, match="network_release"):
        GeoGraph.load_geograph("europe", str(cache), network_release=tag)

    assert releases.requested == []


def test_the_arguments_of_a_network_release_are_refused_for_a_network_of_3_6_0(
    releases, cache
):
    with pytest.raises(ValueError, match="network release"):
        GeoGraph.load_geograph(
            "marnet", str(cache), load_intermediate_nodes=False
        )

    assert releases.requested == []


def test_a_network_of_release_3_6_0_names_the_released_network_to_use(marnet):
    with pytest.warns(DeprecationWarning, match="Use 'world_sea'"):
        GeoGraph.load_geograph("marnet")


def test_another_geograph_url_is_deprecated():
    # A lazy load makes no request before the first use of the network.
    with pytest.warns(DeprecationWarning, match="geograph_url"):
        GeoGraph.load_geograph(
            "marnet", geograph_url="https://example.invalid", lazy=True
        )
