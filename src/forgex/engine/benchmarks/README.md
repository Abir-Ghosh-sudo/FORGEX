# FORGEX Engine Benchmarks

Performance benchmarking utilities for the FORGEX engine.

## Components

- BenchmarkRunner: executes repeatable benchmarks.
- EngineBenchmarks: standard engine workload collection.
- BenchmarkResult: individual benchmark measurements.
- BenchmarkReport: aggregate benchmark report.

## Usage

```python
from forgex.engine.benchmarks import (
    BenchmarkRunner,
    EngineBenchmarks,
)

from forgex._native import (
    CoreEngine,
    SourceParser,
    CodeSearchEngine,
)

runner = BenchmarkRunner(
    warmup_iterations=2,
    default_iterations=10,
)

benchmarks = EngineBenchmarks(runner)

report = benchmarks.run_all(
    core=CoreEngine,
    parser=SourceParser(),
    search=CodeSearchEngine(),
)

print(report)