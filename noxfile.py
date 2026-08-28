import nox

nox.options.default_venv_backend = "uv"


@nox.session(python=["3.11", "3.12", "3.13", "3.14"])
def tests(session):
    session.run_install(
        "uv", "sync", "--extra", "dev", "--reinstall-package", "scgraph", external=True
    )
    session.run("pytest", env={"SCGRAPH_SKIP_CPP": "0"})

    session.run_install(
        "uv",
        "sync",
        "--extra",
        "dev",
        "--reinstall-package",
        "scgraph",
        external=True,
        env={
            "SKBUILD_CMAKE_ARGS": "-DSKIP_CPP_BUILD=ON"
        },
    )
    session.run("pytest", env={"SCGRAPH_SKIP_CPP": "1"})
