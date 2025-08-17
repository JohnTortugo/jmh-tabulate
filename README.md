# JMH Benchmark Comparison Tool

This tool compares JMH (Java Microbenchmark Harness) benchmark results between
two different JVM implementations (baseline and treatment) and generates an
interactive HTML report.

## Features

- **Interactive HTML Report**: Sort and filter benchmark results in your browser
- **Performance Metrics**: Shows improvement percentages, speedup factors, and statistical summaries
- **Filtering Options**: Filter by benchmark name, status (improved/regressed/unchanged), and mode
- **Export Functionality**: Export filtered results to CSV
- **Aggregate Statistics**: Shows average and median improvements across filtered results
- **Real-time Updates**: Statistics update automatically when filters are applied

## Directory Structure

The script expects the following directory structure:

```
jdk-jmh-plots/
├── generate_report.py
├── baseline/           # OpenJDK JMH JSON results
│   ├── result1.json
│   ├── result2.json
│   └── ...
└── treatment/          # GraalVM CE JMH JSON results
    ├── result1.json
    ├── result2.json
    └── ...
```

## Usage

1. **Prepare your data**:
   - Create `baseline/` directory and add your OpenJDK JMH JSON result files
   - Create `treatment/` directory and add your GraalVM CE JMH JSON result files

2. **Run the script**:
   ```bash
   python3 generate_report.py
   ```

3. **View the report**:
   - Open the generated `benchmark_comparison_report.html` file in your browser
   - Use the interactive controls to filter and sort the results

## JMH JSON Format

The script expects standard JMH JSON output format. Each JSON file should contain an array of benchmark results with the following structure:

```json
[
  {
    "benchmark": "com.example.Benchmark.testMethod",
    "mode": "thrpt",
    "threads": 1,
    "forks": 1,
    "jvm": "/path/to/java",
    "jvmArgs": [...],
    "jdk": "OpenJDK 64-Bit Server VM, 11.0.2",
    "vmName": "OpenJDK 64-Bit Server VM",
    "vmVersion": "11.0.2+9",
    "warmupIterations": 5,
    "warmupTime": "10s",
    "measurementIterations": 5,
    "measurementTime": "10s",
    "primaryMetric": {
      "score": 12345.67,
      "scoreError": 123.45,
      "scoreUnit": "ops/s",
      "scoreConfidence": [12222.22, 12468.12]
    },
    "secondaryMetrics": {...}
  }
]
```

## Report Features

### Summary Statistics
- Total number of benchmarks compared
- Count of improved/regressed/unchanged benchmarks
- Average and median improvement percentages
- Average and median speedup factors

### Interactive Table
- **Sortable columns**: Click column headers to sort
- **Benchmark filtering**: Type to filter by benchmark name
- **Status filtering**: Filter by improvement status
- **Mode filtering**: Filter by JMH mode (throughput, average time, etc.)
- **Export**: Download filtered results as CSV

### Performance Metrics
- **Improvement %**: Percentage change from baseline to treatment
  - For throughput modes (higher = better): `(treatment - baseline) / baseline * 100`
  - For latency modes (lower = better): `(baseline - treatment) / baseline * 100`
- **Speedup**: Multiplicative factor of improvement
- **Status**: Improved (green), Regressed (red), or Unchanged (gray)

## JMH Modes Supported

- `thrpt` - Throughput (operations per unit time)
- `avgt` - Average time per operation
- `sample` - Sample time
- `ss` - Single shot

## Requirements

- Python 3.6+
- Standard library modules only (no external dependencies)

## Example Output

The generated report includes:
- Summary cards showing aggregate statistics
- Interactive controls for filtering and sorting
- A detailed table with all benchmark comparisons
- Color-coded status indicators
- Export functionality for further analysis

## Troubleshooting

1. **No baseline/treatment directories**: The script will prompt you to create the required directories and add JSON files.

2. **No matching benchmarks**: If baseline and treatment results don't have common benchmarks, the script will report this issue.

3. **Invalid JSON format**: The script will skip invalid JSON files and report parsing errors.

4. **Empty results**: Make sure your JMH JSON files contain the expected structure with `primaryMetric` data.

## Performance Interpretation

- **Positive improvement %**: Treatment performs better than baseline
- **Negative improvement %**: Treatment performs worse than baseline
- **Speedup > 1.0**: Treatment is faster than baseline
- **Speedup < 1.0**: Treatment is slower than baseline

The interpretation depends on the JMH mode:
- **Throughput modes**: Higher scores are better
- **Latency modes**: Lower scores are better
