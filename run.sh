#!/bin/bash
docker build . --tag "scgraph" --quiet > /dev/null
# if an arg was passed: use it as an entrypoint
if [ -z "$1" ]; then
    docker run -it --rm \
        --volume "$(pwd):/app" \
        --env RUNNING_WITH_DOCKER=1 \
        "scgraph"
else
    # pass additional args to the sub script (e.g. test specific files)
    script_arg="$1"
    shift
    docker run -i --rm \
        --volume "$(pwd):/app" \
        --entrypoint "/app/utils/$script_arg.sh" \
        --env RUNNING_WITH_DOCKER=1 \
        "scgraph" "$@"
fi