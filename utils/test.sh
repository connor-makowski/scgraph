#!/bin/bash

# If not in DOCKER, ensure in a virtual environment and install dependencies
if [ -z "$RUNNING_WITH_DOCKER" ]; then
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt --require-virtualenv
    else
        source venv/bin/activate
    fi
fi
python --version

# Check for args (files to run otherwise run all tests)
if [ "$#" -gt 0 ]; then
    for file in "$@"; do
        if [ -e "$file" ]; then
            echo "Running $file..."
            python "$file"
        else
            echo "File $file does not exist."
        fi
    done
    exit 0
fi

rm -rf ./utils/test_output.txt
touch ./utils/test_output.txt
for file in ./test/*.py; do
    [ -e "$file" ] || continue  # Skip if no files match
    # Run the files, print the output and capture the output as well
    python "$file" | tee -a ./utils/test_output.txt
done