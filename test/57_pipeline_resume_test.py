import json
import os
import shutil
import tempfile
import types
from pathlib import Path

import pytest

from scgraph.geograph import GeoGraph
from scgraph.pipelines.build import build_file, main
from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage3_assembly import assembly


def test_piece_arrays_resume_mapping(tmp_path):
    folder = tmp_path / "stage1"
    # Create and write pieces
    pieces = assembly.PieceArrays(folder=str(folder))
    pieces.append(
        101, 102, 12.5, 0, [[48.8, 2.3], [48.9, 2.4]], [[48.85, 2.35]]
    )
    pieces.flush()
    assert len(pieces.km) == 1
    assert pieces.origins[0] == 101

    # Reload with truncate=False
    reloaded = assembly.PieceArrays(folder=str(folder), truncate=False)
    assert len(reloaded.km) == 1
    assert reloaded.origins[0] == 101
    assert reloaded.destinations[0] == 102
    assert reloaded.km[0] == 12.5
    graph = assembly.build_graph_from_pieces(reloaded)
    assert len(graph["offsets"]) == 3
    reloaded.close()


def test_build_way_pieces_checkpoint_resume(tmp_path, monkeypatch):
    folder = tmp_path / "stage1"
    folder.mkdir(parents=True)
    calls = []

    def mock_locate_ways(
        source, selects, tag_keys=(), node_store=None, folder=None
    ):
        calls.append("locate_ways")
        junctions = osm._Junctions([1, 2])
        ways = [("roads", 0, [(1, [0.0, 0.0]), (2, [0.1, 0.1])])]
        return junctions, iter(ways)

    monkeypatch.setattr(osm, "locate_ways", mock_locate_ways)

    # First run: writes checkpoint stage1.done
    pieces1, steps1 = osm.build_way_pieces(
        "dummy_source",
        {"roads": lambda tags: 0},
        (),
        max_km=10,
        folder=str(folder),
    )
    assert calls == ["locate_ways"]
    assert (folder / "stage1.done").is_file()
    assert len(pieces1.km) >= 1

    # Second run: should load directly from stage1.done without calling locate_ways
    pieces2, steps2 = osm.build_way_pieces(
        "dummy_source",
        {"roads": lambda tags: 0},
        (),
        max_km=10,
        folder=str(folder),
    )
    assert calls == ["locate_ways"]  # Still 1 call, locate_ways was skipped!
    assert len(pieces2.km) == len(pieces1.km)
    assert steps2 == steps1


def test_build_file_keep_work_and_clean(tmp_path, monkeypatch):
    module = types.ModuleType("dummy_pipeline")
    module.__doc__ = "A dummy test pipeline"
    module.PIPELINE_VERSION = 1
    module.SOURCES = {
        "roads": {
            "url": "http://localhost/dummy.txt",
            "credit": "Dummy",
            "license": "MIT",
            "license_url": "",
            "download": lambda url, target: Path(target).write_text("dummy"),
        }
    }

    build_calls = []

    def dummy_build(files, *, folder=None):
        build_calls.append(folder)
        return GeoGraph(
            graph=[{1: 10.0}, {}],
            nodes=[[0.0, 0.0], [1.0, 1.0]],
        )

    module.build = dummy_build

    # 1. Run with keep_work=True
    work_dir = tmp_path / "custom_work"
    out_file = build_file(
        module,
        cache_dir=str(tmp_path / "cache"),
        keep_work=True,
        work_dir=str(work_dir),
    )
    assert Path(out_file).is_file()
    assert work_dir.exists()
    assert work_dir.joinpath("sources", "roads.txt").is_file()
    assert work_dir.joinpath("sources", "roads.meta.json").is_file()
    assert len(build_calls) == 1

    # 2. Run again with resume=True (default): should reuse sources
    out_file2 = build_file(
        module,
        cache_dir=str(tmp_path / "cache"),
        keep_work=True,
        work_dir=str(work_dir),
        refresh=True,
    )
    assert Path(out_file2).is_file()
    assert len(build_calls) == 2

    # 3. Run with clean=True: should purge work_dir
    fake_artifact = work_dir / "stage1" / "stage1.done"
    fake_artifact.parent.mkdir(parents=True, exist_ok=True)
    fake_artifact.write_text("done")

    build_file(
        module,
        cache_dir=str(tmp_path / "cache"),
        clean=True,
        keep_work=True,
        work_dir=str(work_dir),
        refresh=True,
    )
    # fake_artifact was cleared during clean
    assert not fake_artifact.is_file()


def test_build_file_from_stage_invalidation(tmp_path):
    module = types.ModuleType("dummy_pipeline")
    module.__doc__ = "Pipeline for stage invalidation test"
    module.PIPELINE_VERSION = 1
    module.SOURCES = {
        "src": {
            "url": "http://localhost/src.txt",
            "credit": "Dummy",
            "license": "MIT",
            "license_url": "",
            "download": lambda url, target: Path(target).write_text("test"),
        }
    }
    module.build = lambda files, *, folder=None: GeoGraph(
        graph=[{1: 10.0}, {}], nodes=[[0.0, 0.0], [1.0, 1.0]]
    )

    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True)
    stage1 = work_dir / "stage1"
    stage1.mkdir()
    (stage1 / "pass1.done").write_text("done")
    (stage1 / "pass2.done").write_text("done")
    (stage1 / "stage1.done").write_text("done")

    # Invalidate starting from pass2
    build_file(
        module,
        cache_dir=str(tmp_path / "cache"),
        from_stage="pass2",
        keep_work=True,
        work_dir=str(work_dir),
        refresh=True,
    )

    # pass1.done kept, but pass2.done and stage1.done removed!
    assert (stage1 / "pass1.done").is_file()
    assert not (stage1 / "pass2.done").is_file()
    assert not (stage1 / "stage1.done").is_file()


def test_build_cli_options(tmp_path, monkeypatch, capsys):
    from scgraph.pipelines import build

    calls = []

    def mock_build_file(name, region=None, cache_dir=None, **kwargs):
        calls.append((name, region, cache_dir, kwargs))
        return "/fake/path.scgraph"

    monkeypatch.setattr(build, "build_file", mock_build_file)

    # Test full CLI arguments parsing
    build.main(
        [
            "marnet",
            "--cache-dir",
            str(tmp_path),
            "--clean",
            "--from",
            "stage2",
            "--keep-work",
            "--work-dir",
            str(tmp_path / "custom"),
            "--validate",
        ]
    )
    captured = capsys.readouterr()
    assert "/fake/path.scgraph" in captured.out
    assert len(calls) == 1
    name, region, cache_dir, kwargs = calls[0]
    assert name == "marnet"
    assert cache_dir == str(tmp_path)
    assert kwargs["clean"] is True
    assert kwargs["from_stage"] == "stage2"
    assert kwargs["keep_work"] is True
    assert kwargs["work_dir"] == str(tmp_path / "custom")
    assert kwargs["validate"] is True
    assert kwargs["resume"] is True

    # Test --no-resume
    build.main(["marnet", "--no-resume"])
    assert calls[-1][3]["resume"] is False
