All relevant development code for this repo can be found in the `scgraph` directory.

- scgraph/*.py: Relevant python code
- scgraph/cpp/*: A directory containing some optimized C++ Code to replace slower python code.
    - The python code is still kept as a fallback for systems that cannot compile the C++ code.

Testing:
- All tests are located in the `test` directory and should be named `*_test.py` to be automatically discovered by the test runner.
- Containerized testing: `./run.sh test`
    - To run a specific test file in Docker, you can run `./run.sh test test/test_file.py`

Linting:

- Linting is always done with `./run.sh prettify` to ensure consistent formatting across all code and tests.

Other Instructions:

Ignore content in gitignored files like __pycache__, venv, .claude, *.egg-info, build, dist, etc. is not relevant to the codebase and should not be considered when making edits or suggestions.


