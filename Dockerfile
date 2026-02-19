# syntax = docker/dockerfile:1

## Uncomment the version of python you want to test against
# FROM python:3.10-slim
# FROM python:3.11-slim
# FROM python:3.12-slim
# FROM python:3.13-slim
# FROM python:3.14-slim
# Use non bookwork or trixie versions to test CPP builds
FROM python:3.14-bookworm


# Set the working directory to /app
WORKDIR /app/

# Copy and install the requirements
# This includes egg installing the scgraph package
COPY scgraph/__init__.py /app/scgraph/__init__.py
COPY scgraph/cpp /app/scgraph/cpp
COPY pyproject.toml /app/pyproject.toml
COPY CMakeLists.txt /app/CMakeLists.txt
COPY README.md /app/README.md
COPY requirements.txt /app/requirements.txt

RUN pip install -r requirements.txt

# Drop into a shell by default
CMD ["/bin/bash"]
