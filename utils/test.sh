#!/bin/bash
python --version
rm -rf ./utils/test_output.txt
touch ./utils/test_output.txt
for file in /app/test/*.py; do
    [ -e "$file" ] || continue  # Skip if no files match
    # Run the files, print the output and capture the output as well
    python "$file" | tee -a ./utils/test_output.txt
done