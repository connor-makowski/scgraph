# Change to the script directory
cd "$(dirname "$0")"

# Remove the existing build directory.
sudo rm -r build
sudo rm -r ../scgraph/bin

# Create a new build directory and navigate into it.
mkdir build
cd build

# Run CMake to configure the project and generate build files, then build the project.
cmake ..
cmake --build .

# Navigate back to the script directory.
cd ..

# Move the compiled binary to a 'bin' directory.
mkdir ../scgraph/bin
touch ../scgraph/bin/__init__.py
for f in build/*.so; do
    mv "$f" ../scgraph/bin/
done

sudo rm -r build