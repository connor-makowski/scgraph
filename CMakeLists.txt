cmake_minimum_required(VERSION 3.15)

# -----------------------------
# Define The Project
# -----------------------------
project(scgraph LANGUAGES CXX)

# -----------------------------
# Find Packages
# -----------------------------
find_package(Python 3.10 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

# BMSSP solver: bmsspy ships its C++ sources in its wheel (build requirement)
execute_process(
    COMMAND "${Python_EXECUTABLE}" -c
        "import bmsspy, pathlib; print(pathlib.Path(bmsspy.__file__).parent.parent.as_posix())"
    OUTPUT_VARIABLE BMSSPY_ROOT
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE BMSSPY_FOUND
)
if(NOT BMSSPY_FOUND EQUAL 0 OR NOT EXISTS "${BMSSPY_ROOT}/bmsspy/cpp/src/bmssp.cpp")
    message(FATAL_ERROR "bmsspy >= 2.3 with its C++ sources is required to build scgraph's C++ extension")
endif()

# -----------------------------
# Set C++ standard
# -----------------------------
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# -----------------------------
# OPTIMIZATION FLAGS
# -----------------------------
set(CMAKE_BUILD_TYPE Release)
if(MSVC)
    set(CMAKE_CXX_FLAGS_RELEASE "/O2 /DNDEBUG")
else()
    set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG -fno-math-errno -fomit-frame-pointer")
endif()

# -----------------------------
# Graph module
# -----------------------------
nanobind_add_module(
    cpp
    STABLE_ABI
    scgraph/cpp/bindings/graph_bindings.cpp
    scgraph/cpp/src/graph.cpp
    scgraph/cpp/src/graph_utils.cpp
    scgraph/cpp/src/graph_reducer.cpp
    scgraph/cpp/src/contraction_hierarchies.cpp
    scgraph/cpp/src/transit_node_routing.cpp
    ${BMSSPY_ROOT}/bmsspy/cpp/src/bmssp.cpp
)
target_include_directories(cpp PRIVATE ${BMSSPY_ROOT})
install(TARGETS cpp DESTINATION scgraph)

# -----------------------------
# Install Python package files
# -----------------------------
install(DIRECTORY scgraph DESTINATION . FILES_MATCHING PATTERN "*.py")