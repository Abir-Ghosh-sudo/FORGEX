# FORGEX Native Engine Binding

This package connects the C++ engine with Python through pybind11.

## Components

- CoreEngine: native text and utility operations.
- SourceParser: lexical tokenization.
- CodeSearchEngine: text and regex search.
- RepositoryIndexer: repository file indexing.
- IndexStore: native index persistence.

## Build

The native extension is built through the root CMake configuration.

Required:
- C++20 compiler
- CMake
- Python development headers
- pybind11

## Python usage

```python
from forgex._native import (
    CoreEngine,
    SourceParser,
    CodeSearchEngine,
    RepositoryIndexer,
)

print(CoreEngine.get_info().version)

parser = SourceParser()
result = parser.parse(
    "def hello(): return 42",
    "python",
)

search = CodeSearchEngine()
matches = search.search_text(
    "hello world",
    "world",
)

indexer = RepositoryIndexer()
result = indexer.index_directory(".")