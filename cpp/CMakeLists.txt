cmake_minimum_required(VERSION 3.14)
project(scgraph)

# -----------------------------
# Set C++ standard
# -----------------------------
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# -----------------------------
# OPTIMIZATION FLAGS
# -----------------------------
set(CMAKE_BUILD_TYPE Release)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -DNDEBUG")
set(CMAKE_CXX_FLAGS_DEBUG "-g -O0")

# -----------------------------
# Find Packages
# -----------------------------
find_package(Python COMPONENTS Interpreter Development REQUIRED)

# -----------------------------
# Add nanobind
# -----------------------------
include(FetchContent)
FetchContent_Declare(
    nanobind
    GIT_REPOSITORY https://github.com/wjakob/nanobind.git
    GIT_TAG v2.9.2  # Specify the version you want
    GIT_SHALLOW TRUE  # Only fetch the specific commit, faster download
)
FetchContent_MakeAvailable(nanobind)

# -----------------------------
# Graph module
# -----------------------------
nanobind_add_module(graph_cpp
    bindings/graph_bindings.cpp
    src/graph.cpp
)
target_compile_features(graph_cpp PRIVATE cxx_std_17)