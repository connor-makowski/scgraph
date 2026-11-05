#!/usr/bin/env python3
"""
Compare the speed of two versions of scgraph on this machine, with utils/bench.py.

    # dev against the release
    python3 utils/compare_versions.py 3.6.0 origin/dev
    # a PR against dev, on the sections it touches
    python3 utils/compare_versions.py origin/dev my-branch --only query
    # the same, and the report written into the description of PR 123
    python3 utils/compare_versions.py origin/dev my-branch --only query --post 123

BASE and HEAD are git refs of this repository (tag, branch, remote branch such as
origin/dev, SHA): committed code only, uncommitted changes are not measured. Both
versions run the utils/bench.py of the current checkout, so their rows are the same.

What it does, printing each step:
  1. builds one environment per version and backend in bench-results/envs/, from the
     version's own uv.lock (non-editable install), and checks its backend; a finished
     environment is reused by every later comparison;
  2. runs the benchmark once per environment, untimed (downloads, conversions, warm
     files), then --runs rounds alternating which version goes first, one process per
     run;
  3. writes report.md in a folder of bench-results/: a summary to paste into a PR
     description (versions, machine, protocol, rows that move by more than 15 %,
     memory, identical results), then the tables of benchmark.md with both versions
     side by side. The raw JSON of every run stays beside it.

Run the same command again to resume after Ctrl-C or a failure: finished environments
and runs are kept. Each comparison takes about 0.15 GB: delete bench-results/ to free
the space.

--post N writes the report into the description of issue or PR N of the repository's
GitHub remote, between two hidden markers (<!-- scgraph-bench:start --> and
<!-- scgraph-bench:end -->): it replaces that block if it exists, otherwise appends it
under a "Performance" heading. The rest of the description is not touched, and GitHub
keeps the previous versions in its edit history.

Duration, all sections (i7-8550U laptop, 3.6.0 against dev): about 10 minutes in C++
and 20 more in pure Python; building an environment takes about a minute in C++ and
seconds in pure Python. Keep the machine otherwise idle meanwhile.

Requires Python 3.11 or later (the environments use the Python that runs this script;
with another one: uv run --no-project --python 3.13 utils/compare_versions.py ...), git,
uv (https://docs.astral.sh/uv/), a C++ compiler for the cpp backend, and gh
(https://cli.github.com/) for --post. Linux and macOS; memory rows on Linux only.
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import (
    NETWORKS,
    SECTIONS,
)  # noqa: E402  (bench.py imports stdlib only)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "bench-results"
BENCH = ROOT / "utils" / "bench.py"
BACKENDS = {
    "cpp": ({"SCGRAPH_REQUIRE_CPP": "1"}, True, "C++"),
    "python": ({"SCGRAPH_NO_BUILD": "1"}, False, "pure Python"),
}
# Not needed to build or run scgraph: keeps each source copy about 1 MB
NOT_BUILT = ["docs", "geographs", "static", "examples", "test", "doc_template"]
START, END = "<!-- scgraph-bench:start -->", "<!-- scgraph-bench:end -->"
GITHUB_LIMIT = 65536
PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"


class Stop(Exception):
    """A failure with a message for the user (printed without a traceback)."""


def git(*args):
    done = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True
    )
    if done.returncode:
        raise Stop(done.stderr.strip() or f"git {' '.join(args)} failed")
    return done.stdout.strip()


def tail(text, lines=30):
    return "\n".join("    " + line for line in text.splitlines()[-lines:])


def slug(text):
    return re.sub(r"[^A-Za-z0-9._+-]+", "-", text).strip("-")


class Version:
    def __init__(self, ref):
        self.ref = ref
        try:
            self.sha = git("rev-parse", "--verify", f"{ref}^{{commit}}")
        except Stop:
            raise Stop(
                f"{ref!r} is not a commit of this repository"
                " (a remote branch is origin/NAME; git fetch?)"
            )
        self.short = self.sha[:7]
        self.about = git("log", "-1", "--format=%cs %s", self.sha)

    def env(self, backend):
        return OUT / "envs" / f"{self.sha[:12]}-{backend}-py{PYTHON}"


def preflight(base, head, args):
    print(f"Base  {base.ref} = {base.short}  {base.about}")
    print(f"Head  {head.ref} = {head.short}  {head.about}")
    if base.sha == head.sha:
        raise Stop(f"{base.ref} and {head.ref} are the same commit")
    if sys.version_info < (3, 11):
        raise Stop(
            f"Python {PYTHON} runs this script; scgraph needs 3.11 or later:"
            " uv run --no-project --python 3.13 utils/compare_versions.py ..."
        )
    if shutil.which("uv") is None:
        raise Stop(
            "uv is required: https://docs.astral.sh/uv/getting-started/installation/"
        )
    if args.post:
        if shutil.which("gh") is None:
            raise Stop("--post needs the GitHub CLI: https://cli.github.com/")
        if subprocess.run(
            ["gh", "auth", "status"], capture_output=True
        ).returncode:
            raise Stop("--post: gh is not logged in (run: gh auth login)")
    if git("rev-parse", "HEAD") in (base.sha, head.sha) and git(
        "status", "--porcelain", "--untracked-files=no"
    ):
        print(
            "Note: the checkout has uncommitted changes; they are not measured."
        )


def build(version, backend):
    """The environment of one version and backend, built once (marker file: ok)."""
    env = version.env(backend)
    flags, expected, name = BACKENDS[backend]
    if (env / "ok").exists() and python(env).exists():
        print(f"  {version.ref} ({name}): reusing {env.relative_to(ROOT)}")
        return env
    shutil.rmtree(env, ignore_errors=True)
    src, log = env.with_name(env.name + "-src"), env.with_name(
        env.name + ".log"
    )
    print(f"  {version.ref} ({name}): building {env.relative_to(ROOT)}")
    # The backend is chosen by flags only: none inherited from the shell
    build_env = {
        k: v for k, v in os.environ.items() if not k.startswith("SCGRAPH_")
    }
    build_env.update(flags, UV_PROJECT_ENVIRONMENT=str(env))
    try:
        shutil.rmtree(src, ignore_errors=True)
        src.mkdir(parents=True)
        excludes = [f":(exclude){d}" for d in NOT_BUILT]
        archive = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "archive",
                version.sha,
                "--",
                ".",
                *excludes,
            ],
            capture_output=True,
            check=True,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            try:
                tar.extractall(src, filter="data")
            except TypeError:  # Python 3.11 before 3.11.4
                tar.extractall(src)
        if not (src / "uv.lock").exists():
            raise Stop(
                f"{version.ref} has no uv.lock: only 3.6.0 and later can be compared"
            )
        with open(log, "w") as out:
            done = subprocess.run(
                ["uv", "sync", "--locked", "--no-dev", "--no-editable"]
                + ["--python", PYTHON],
                cwd=src,
                env=build_env,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        if done.returncode:
            output = log.read_text(errors="replace")
            hint = ""
            if "needs to be updated" in output:
                hint = f"\n  The uv.lock of {version.ref} is out of date:"
                hint += " run `uv lock` on that ref."
            raise Stop(
                f"building {version.ref} ({name}) failed (log: {log}):\n"
                f"{tail(output)}{hint}"
            )
        check = subprocess.run(
            [str(python(env)), "-I", "-c"]
            + ["from scgraph.utils import has_cpp; print(has_cpp())"],
            capture_output=True,
            text=True,
        )
        if check.stdout.strip() != str(expected):
            raise Stop(
                f"{version.ref}: the {name} environment answers has_cpp() ="
                f" {check.stdout.strip() or 'error'} (expected {expected}); build log:"
                f" {log}\n{tail(check.stderr, 10)}"
            )
        (env / "ok").write_text(version.sha + "\n")
        return env
    except BaseException:
        shutil.rmtree(env, ignore_errors=True)  # never reuse a half-built one
        raise
    finally:
        shutil.rmtree(src, ignore_errors=True)


def python(env):
    return env / "bin" / "python"


def seed_cache(cache):
    """Copies the networks already in the user's scgraph cache (both versions write
    beside them, so no links); returns the names that are not there."""
    if os.environ.get("SCGRAPH_CACHE_DIR"):
        source = Path(os.environ["SCGRAPH_CACHE_DIR"])
    elif sys.platform == "darwin":
        source = Path.home() / "Library" / "Caches" / "scgraph"
    else:
        source = Path.home() / ".cache" / "scgraph"
    cache.mkdir(parents=True, exist_ok=True)
    missing = []
    for net in NETWORKS:
        target = cache / f"{net}.graphjson"
        if target.exists():
            continue
        if (source / target.name).exists():
            partial = target.with_suffix(".tmp")
            shutil.copy2(source / target.name, partial)
            partial.replace(target)  # a copy cut short is never reused
        else:
            missing.append(net)
    return missing


def run_bench(env, version, cache, json_path, subset, timeout):
    """One process of bench.py (skipped if its file exists); its duration in s."""
    try:
        return json.loads(json_path.read_text())["total_s"]
    except (OSError, ValueError, KeyError):
        json_path.unlink(missing_ok=True)  # missing, or cut short: run it again
    log = json_path.with_suffix(".log")
    command = [str(python(env)), "-I", str(BENCH), "--commit", version.short]
    command += [*subset, "--json", str(json_path)]
    with open(log, "w") as out:
        try:
            done = subprocess.run(
                command,
                env={**os.environ, "SCGRAPH_CACHE_DIR": str(cache)},
                stdout=out,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            json_path.unlink(missing_ok=True)
            raise Stop(
                f"{json_path.name} took more than {timeout:.0f} s; see {log}"
            )
    if done.returncode or not json_path.exists():
        raise Stop(
            f"{json_path.name} failed (log: {log}):\n"
            f"{tail(log.read_text(errors='replace'))}"
        )
    return json.loads(json_path.read_text())["total_s"]


def campaign(base, head, backend, folder, subset, runs):
    name = BACKENDS[backend][2]
    print(f"\n{name}: environments")
    envs = {v: build(v, backend) for v in (base, head)}
    caches = {v: folder / f"cache-{v.sha[:12]}" for v in (base, head)}
    for v in (base, head):
        missing = seed_cache(caches[v])
        if missing:
            print(
                f"  {v.ref}: not in your scgraph cache, downloaded if a section"
                f" needs it: {', '.join(missing)}"
            )
    print(f"{name}: one untimed run per version")
    warm = {}
    for v in (base, head):
        path = folder / f"{backend}-warmup-{v.sha[:12]}.json"
        warm[v] = run_bench(envs[v], v, caches[v], path, subset, timeout=3600)
        print(f"  {v.ref}: {warm[v]:.1f} s")
    print(f"{name}: {runs} rounds, about {elapsed(runs * sum(warm.values()))}")
    for i in range(runs):
        for v in (base, head) if i % 2 == 0 else (head, base):
            path = folder / f"{backend}-{v.sha[:12]}-{i}.json"
            timeout = max(120, 3 * warm[v])
            seconds = run_bench(envs[v], v, caches[v], path, subset, timeout)
            print(f"  round {i + 1}/{runs}  {v.ref}: {seconds:.1f} s")
    patterns = [
        str(folder / f"{backend}-{v.sha[:12]}-[0-{runs - 1}].json")
        for v in (base, head)
    ]
    done = subprocess.run(
        [sys.executable, "-I", str(BENCH), "--labels", base.ref, head.ref]
        + ["--compare", *patterns],
        capture_output=True,
        text=True,
    )
    if done.returncode:
        raise Stop(f"bench.py --compare failed:\n{done.stderr}")
    return done.stdout


def report(base, head, outputs, args, folder, bench):
    first = sorted(folder.glob(f"*-{head.sha[:12]}-0.json"))[0]
    machine = json.loads(first.read_text())["environment"]
    ram = f", {machine['ram_gib']} GiB RAM" if machine.get("ram_gib") else ""
    summary = [
        f"**Performance: `{base.ref}` {base.short} → `{head.ref}` {head.short}**",
        "",
        f"- Machine: {machine['cpu']}{ram}, {machine['os']},"
        f" Python {machine['python']}",
        f"- Benchmark: `utils/bench.py` {bench},"
        f" {' '.join(args.subset_args) or 'all sections'}; one untimed run per"
        f" version, then {args.runs} runs per version alternating which goes"
        " first; best time (memory: median, Linux only); a row moves when its best"
        " and median times both change by more than 15 % (memory: 5 % and 5 MiB)",
        f"- Command: `python3 utils/compare_versions.py {base.ref} {head.ref}"
        f"{''.join(' ' + x for x in args.options)}`",
        "",
    ]
    tables = []
    for backend, text in outputs.items():
        name = BACKENDS[backend][2]
        first_part, _, rest = text.partition("\n## ")
        summary += [f"*{name}*", "", first_part.strip(), ""]
        tables += [f"<details><summary>{name}: all rows</summary>", ""]
        tables += ["#### " + rest.replace("\n## ", "\n#### "), "</details>", ""]
    return "\n".join(summary), "\n".join(tables)


def with_report(body, block):
    """The description with the block between the markers: replaced, or appended."""
    text = f"{START}\n{block}\n{END}"
    start = body.find(START)
    if start < 0:
        return f"{body}\n\n### Performance\n\n{text}".lstrip()
    end = body.find(END, start)
    if end < 0:
        raise Stop(f"--post: the description has {START} but no {END} after it")
    return body[:start] + text + body[end + len(END) :]


def post(number, summary, tables, report_path):
    """Writes the report into the description of issue or PR number."""

    def gh(*args, **kwargs):
        # In ROOT: gh resolves {owner}/{repo} from this repository's remote
        return subprocess.run(
            ["gh", "api", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            **kwargs,
        )

    endpoint = f"repos/{{owner}}/{{repo}}/issues/{number}"
    done = gh(endpoint, "--jq", '.body // ""')
    if done.returncode:
        raise Stop(f"--post: cannot read #{number}: {done.stderr.strip()}")
    body = done.stdout.rstrip("\n")
    new = with_report(body, f"{summary}\n{tables}")
    if len(new) > GITHUB_LIMIT:
        print(
            f"  The full report exceeds GitHub's {GITHUB_LIMIT} characters: writing"
            f" the summary only (full report: {report_path})."
        )
        new = with_report(body, summary)
        if len(new) > GITHUB_LIMIT:
            raise Stop(
                f"--post: the description would exceed {GITHUB_LIMIT} characters"
            )
    done = gh(
        "-X", "PATCH", endpoint, "--input", "-", "--jq", ".html_url",
        input=json.dumps({"body": new}),
    )  # fmt: skip
    if done.returncode:
        raise Stop(f"--post: cannot write #{number}: {done.stderr.strip()}")
    print(f"Report written into the description of {done.stdout.strip()}")


def elapsed(seconds):
    return f"{seconds / 60:.0f} min" if seconds >= 90 else f"{seconds:.0f} s"


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "base",
        metavar="BASE",
        help="git ref measured first (e.g. 3.6.0, origin/dev)",
    )
    parser.add_argument(
        "head",
        metavar="HEAD",
        help="git ref compared with it (e.g. a PR branch)",
    )
    parser.add_argument(
        "--backends",
        default="cpp",
        help="cpp, python or cpp,python (default: cpp, as in benchmark.md)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="timed runs per version and backend, 2 to 10 (default: 5)",
    )
    parser.add_argument(
        "--only",
        metavar="SECTIONS",
        help="sections a change touches, comma-separated: "
        + ", ".join(SECTIONS)
        + " (default: all)",
    )
    parser.add_argument(
        "--networks",
        metavar="NAMES",
        help="networks for load, reduce and query, comma-separated (default: all"
        " five; see bench.py --help)",
    )
    parser.add_argument(
        "--post",
        type=int,
        metavar="N",
        help="write the report into the description of issue or PR N (needs gh)",
    )
    args = parser.parse_args()
    backends = [b.strip() for b in args.backends.split(",")]
    if any(b not in BACKENDS for b in backends):
        parser.error(f"--backends: choose among {', '.join(BACKENDS)}")
    if not 2 <= args.runs <= 10:
        parser.error(
            "--runs: from 2 to 10 (the rule compares best and median times)"
        )
    for option, allowed in (("only", SECTIONS), ("networks", NETWORKS)):
        chosen = getattr(args, option)
        unknown = [
            x for x in (chosen or "").split(",") if chosen and x not in allowed
        ]
        if unknown:
            parser.error(
                f"--{option}: unknown {', '.join(unknown)} (choose among"
                f" {', '.join(allowed)})"
            )
    args.subset_args = []
    for option in ("only", "networks"):
        if getattr(args, option):
            args.subset_args += [f"--{option}", getattr(args, option)]
    args.options = (
        ["--backends", args.backends] if args.backends != "cpp" else []
    )
    args.options += ["--runs", str(args.runs)] if args.runs != 5 else []
    args.options += args.subset_args
    try:
        base, head = Version(args.base), Version(args.head)
        preflight(base, head, args)
        # The rows come from this checkout's bench.py: runs of another version of it,
        # or of another Python, are never mixed when resuming
        content = git("hash-object", str(BENCH))[:7]
        bench = git("rev-parse", "--short", "HEAD")
        if git("status", "--porcelain", "--", str(BENCH)):
            bench = f"(modified, content {content})"
        else:
            bench = f"at {bench}"
        folder = OUT / slug(
            f"{base.ref}-{head.ref}"
            + "".join("-" + x.lstrip("-") for x in args.subset_args)
            + f"-bench-{content}-py{PYTHON}"
        )
        folder.mkdir(parents=True, exist_ok=True)
        started = time.time()
        outputs = {
            b: campaign(base, head, b, folder, args.subset_args, args.runs)
            for b in backends
        }
        summary, tables = report(base, head, outputs, args, folder, bench)
        path = folder / "report.md"
        path.write_text(f"{summary}\n{tables}")
        print(f"\n{summary}")
        used = (
            sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 2**30
        )
        print(
            f"Report: {path.relative_to(ROOT)} ({elapsed(time.time() - started)};"
            f" bench-results/ holds {used:.1f} GB)"
        )
        if args.post:
            post(args.post, summary, tables, path.relative_to(ROOT))
    except Stop as error:
        sys.exit(f"\nStopped: {error}")
    except KeyboardInterrupt:
        sys.exit(
            "\nInterrupted. Finished environments and runs are kept in bench-results/:"
            " run the same command again to resume."
        )


if __name__ == "__main__":
    main()
