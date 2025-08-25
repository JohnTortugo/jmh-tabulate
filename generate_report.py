#!/usr/bin/env python3
"""
JMH Benchmark Comparison Report Generator

This script reads JMH JSON results from baseline and treatment directories,
compares the performance metrics, and generates an interactive HTML report.
"""

import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import statistics
from datetime import datetime
import math


@dataclass
class BenchmarkResult:
    """Represents a single benchmark result."""
    benchmark: str
    mode: str
    threads: int
    forks: int
    jvm: str
    jvm_args: List[str]
    jdk: str
    vm_name: str
    vm_version: str
    warmup_iterations: int
    warmup_time: str
    measurement_iterations: int
    measurement_time: str
    primary_metric: Dict
    secondary_metrics: Dict
    params: Dict
    
    @property
    def score(self) -> float:
        """Get the primary metric score."""
        return self.primary_metric.get('score', 0.0)
    
    @property
    def score_error(self) -> float:
        """Get the primary metric score error."""
        return self.primary_metric.get('scoreError', 0.0)
    
    @property
    def score_unit(self) -> str:
        """Get the primary metric score unit."""
        return self.primary_metric.get('scoreUnit', '')
    
    @property
    def score_confidence(self) -> List[float]:
        """Get the primary metric score confidence interval."""
        return self.primary_metric.get('scoreConfidence', [])


def parse_jmh_json(file_path: Path) -> List[BenchmarkResult]:
    """Parse a JMH JSON file and return list of benchmark results."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        results = []
        for item in data:
            # Extract JVM info
            jvm_args = item.get('jvmArgs', [])
            jdk = item.get('jdk', '')
            vm_name = item.get('vmName', '')
            vm_version = item.get('vmVersion', '')
            
            # Extract benchmark info
            benchmark = item.get('benchmark', '')
            mode = item.get('mode', '')
            threads = item.get('threads', 1)
            forks = item.get('forks', 1)
            jvm = item.get('jvm', '')
            
            # Extract iteration info
            warmup_iterations = item.get('warmupIterations', 0)
            warmup_time = item.get('warmupTime', '')
            measurement_iterations = item.get('measurementIterations', 0)
            measurement_time = item.get('measurementTime', '')
            
            # Extract metrics
            primary_metric = item.get('primaryMetric', {})
            secondary_metrics = item.get('secondaryMetrics', {})
            params = item.get('params', {})
            
            result = BenchmarkResult(
                benchmark=benchmark,
                mode=mode,
                threads=threads,
                forks=forks,
                jvm=jvm,
                jvm_args=jvm_args,
                jdk=jdk,
                vm_name=vm_name,
                vm_version=vm_version,
                warmup_iterations=warmup_iterations,
                warmup_time=warmup_time,
                measurement_iterations=measurement_iterations,
                measurement_time=measurement_time,
                primary_metric=primary_metric,
                secondary_metrics=secondary_metrics,
                params=params
            )
            results.append(result)
        
        return results
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return []


def load_benchmark_results(directory: Path) -> Dict[str, List[BenchmarkResult]]:
    """Load all JMH JSON files from a directory."""
    results = {}
    
    if not directory.exists():
        print(f"Directory {directory} does not exist")
        return results
    
    for json_file in directory.glob("*.json"):
        print(f"Loading {json_file}")
        file_results = parse_jmh_json(json_file)
        if file_results:
            results[json_file.name] = file_results
    
    return results


def calculate_statistical_significance(baseline: BenchmarkResult, treatment: BenchmarkResult) -> Dict:
    """Calculate statistical significance using approximate t-test."""
    # Use score error as estimate of standard error
    # Approximate degrees of freedom (conservative estimate)
    df = 30  # Typical JMH measurement iterations
    
    # Calculate t-statistic
    baseline_score = baseline.score
    treatment_score = treatment.score
    baseline_se = baseline.score_error
    treatment_se = treatment.score_error
    
    # Pooled standard error
    pooled_se = math.sqrt(baseline_se**2 + treatment_se**2)
    
    if pooled_se == 0:
        return {
            'is_significant': False,
            'p_value': 1.0,
            'confidence_level': 'N/A'
        }
    
    # Calculate t-statistic
    t_stat = abs(treatment_score - baseline_score) / pooled_se
    
    # Critical t-value for p < 0.05 (two-tailed) with df=30
    t_critical_05 = 2.042
    # Critical t-value for p < 0.01 (two-tailed) with df=30
    t_critical_01 = 2.750
    
    # Determine significance level
    if t_stat >= t_critical_01:
        is_significant = True
        confidence_level = "p < 0.01"
    elif t_stat >= t_critical_05:
        is_significant = True
        confidence_level = "p < 0.05"
    else:
        is_significant = False
        confidence_level = "p ≥ 0.05"
    
    return {
        'is_significant': is_significant,
        'confidence_level': confidence_level,
        't_statistic': t_stat
    }


def calculate_performance_comparison(baseline: BenchmarkResult, treatment: BenchmarkResult) -> Dict:
    """Calculate performance comparison between baseline and treatment."""
    if baseline.score == 0:
        return {
            'improvement_percent': 0,
            'improvement_ratio': 0,
            'speedup': 0,
            'status': 'baseline_zero',
            'statistical_significance': {
                'is_significant': False,
                'confidence_level': 'N/A',
                't_statistic': 0
            }
        }
    
    # For throughput (higher is better): improvement = (treatment - baseline) / baseline * 100
    # For latency (lower is better): improvement = (baseline - treatment) / baseline * 100
    
    # Determine if higher or lower is better based on mode
    higher_is_better = baseline.mode in ['thrpt', 'Throughput']
    
    if higher_is_better:
        improvement_percent = ((treatment.score - baseline.score) / baseline.score) * 100
        speedup = treatment.score / baseline.score
    else:
        improvement_percent = ((baseline.score - treatment.score) / baseline.score) * 100
        speedup = baseline.score / treatment.score
    
    status = 'improved' if improvement_percent > 0 else 'regressed' if improvement_percent < 0 else 'unchanged'
    
    # Calculate statistical significance
    statistical_significance = calculate_statistical_significance(baseline, treatment)
    
    return {
        'improvement_percent': improvement_percent,
        'improvement_ratio': improvement_percent / 100,
        'speedup': speedup,
        'status': status,
        'higher_is_better': higher_is_better,
        'statistical_significance': statistical_significance
    }


def create_comparison_data(baseline_results: Dict[str, List[BenchmarkResult]], 
                         treatment_results: Dict[str, List[BenchmarkResult]]) -> List[Dict]:
    """Create comparison data between baseline and treatment results."""
    comparison_data = []
    
    # Create a mapping of benchmark name to results for easier lookup
    baseline_map = {}
    treatment_map = {}
    
    for file_name, results in baseline_results.items():
        for result in results:
            params = '&'.join(f'{k}={result.params[k]}' for k in sorted(result.params))
            key = f"{result.benchmark}_{result.mode}_{result.threads}_{params}"
            baseline_map[key] = result
    
    for file_name, results in treatment_results.items():
        for result in results:
            params = '&'.join(f'{k}={result.params[k]}' for k in sorted(result.params))
            key = f"{result.benchmark}_{result.mode}_{result.threads}_{params}"
            treatment_map[key] = result
    
    # Find common benchmarks
    common_benchmarks = set(baseline_map.keys()) & set(treatment_map.keys())
    
    for benchmark_key in common_benchmarks:
        baseline = baseline_map[benchmark_key]
        treatment = treatment_map[benchmark_key]
        
        comparison = calculate_performance_comparison(baseline, treatment)
        
        data = {
            'benchmark': baseline.benchmark,
            'mode': baseline.mode,
            'threads': baseline.threads,
            'baseline_score': baseline.score,
            'baseline_error': baseline.score_error,
            'treatment_score': treatment.score,
            'treatment_error': treatment.score_error,
            'unit': baseline.score_unit,
            'improvement_percent': comparison['improvement_percent'],
            'speedup': comparison['speedup'],
            'status': comparison['status'],
            'higher_is_better': comparison['higher_is_better'],
            'baseline_vm': baseline.vm_name,
            'treatment_vm': treatment.vm_name,
            'baseline_jdk': baseline.jdk,
            'treatment_jdk': treatment.jdk,
            'statistical_significance': comparison['statistical_significance'],
            # Additional detailed information
            'baseline_details': {
                'jvm': baseline.jvm,
                'jvm_args': baseline.jvm_args,
                'jdk': baseline.jdk,
                'vm_name': baseline.vm_name,
                'vm_version': baseline.vm_version,
                'forks': baseline.forks,
                'warmup_iterations': baseline.warmup_iterations,
                'warmup_time': baseline.warmup_time,
                'measurement_iterations': baseline.measurement_iterations,
                'measurement_time': baseline.measurement_time,
                'score_confidence': baseline.score_confidence,
                'secondary_metrics': baseline.secondary_metrics,
                'params': baseline.params
            },
            'treatment_details': {
                'jvm': treatment.jvm,
                'jvm_args': treatment.jvm_args,
                'jdk': treatment.jdk,
                'vm_name': treatment.vm_name,
                'vm_version': treatment.vm_version,
                'forks': treatment.forks,
                'warmup_iterations': treatment.warmup_iterations,
                'warmup_time': treatment.warmup_time,
                'measurement_iterations': treatment.measurement_iterations,
                'measurement_time': treatment.measurement_time,
                'score_confidence': treatment.score_confidence,
                'secondary_metrics': treatment.secondary_metrics,
                'params': treatment.params
            }
        }
        
        comparison_data.append(data)
    
    return comparison_data


def generate_html_report(comparison_data: List[Dict], output_file: str = "benchmark_comparison_report.html"):
    """Generate an interactive HTML report."""
    
    if not comparison_data:
        print("No comparison data available to generate report")
        return
    
    # Calculate summary statistics
    improvements = [d['improvement_percent'] for d in comparison_data]
    speedups = [d['speedup'] for d in comparison_data]
    
    avg_improvement = statistics.mean(improvements)
    median_improvement = statistics.median(improvements)
    avg_speedup = statistics.mean(speedups)
    median_speedup = statistics.median(speedups)
    
    improved_count = len([d for d in comparison_data if d['status'] == 'improved'])
    regressed_count = len([d for d in comparison_data if d['status'] == 'regressed'])
    unchanged_count = len([d for d in comparison_data if d['status'] == 'unchanged'])
    
    # Calculate regression-specific statistics
    regressions = [d['improvement_percent'] for d in comparison_data if d['status'] == 'regressed']
    regression_speedups = [d['speedup'] for d in comparison_data if d['status'] == 'regressed']
    
    if regressions:
        avg_regression = statistics.mean(regressions)
        median_regression = statistics.median(regressions)
        avg_regression_speedup = statistics.mean(regression_speedups)
        median_regression_speedup = statistics.median(regression_speedups)
    else:
        avg_regression = 0
        median_regression = 0
        avg_regression_speedup = 1.0
        median_regression_speedup = 1.0
    
    # Generate HTML
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JMH Benchmark Comparison Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }}
        
        .summary {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
            border-left: 4px solid #007bff;
        }}
        
        .summary h2 {{
            margin-top: 0;
            color: #007bff;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        
        .stat-card {{
            background-color: white;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #e9ecef;
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #007bff;
        }}
        
        .stat-label {{
            font-size: 14px;
            color: #6c757d;
            margin-top: 5px;
        }}
        
        .controls {{
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }}
        
        .controls input, .controls select {{
            margin: 5px;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }}
        
        .controls button {{
            padding: 8px 16px;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin: 5px;
        }}
        
        .controls button:hover {{
            background-color: #0056b3;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        
        th {{
            background-color: #f8f9fa;
            font-weight: 600;
            cursor: pointer;
            user-select: none;
            position: relative;
        }}
        
        th:hover {{
            background-color: #e9ecef;
        }}
        
        th.sorted-asc::after {{
            content: ' ↑';
            position: absolute;
            right: 8px;
        }}
        
        th.sorted-desc::after {{
            content: ' ↓';
            position: absolute;
            right: 8px;
        }}
        
        tr:hover {{
            background-color: #f8f9fa;
        }}
        
        tbody tr {{
            cursor: pointer;
        }}
        
        tbody tr:hover {{
            background-color: #e3f2fd;
        }}
        
        /* Modal styles */
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0,0,0,0.4);
        }}
        
        .modal-content {{
            background-color: #fefefe;
            margin: 2% auto;
            padding: 20px;
            border: none;
            border-radius: 8px;
            width: 90%;
            max-width: 1200px;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #007bff;
        }}
        
        .modal-title {{
            color: #333;
            margin: 0;
            font-size: 24px;
        }}
        
        .close {{
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            transition: color 0.3s;
        }}
        
        .close:hover,
        .close:focus {{
            color: #000;
            text-decoration: none;
        }}
        
        .detail-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .detail-section {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }}
        
        .detail-section h3 {{
            color: #007bff;
            margin-top: 0;
            margin-bottom: 15px;
        }}
        
        .detail-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            padding: 5px 0;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .detail-label {{
            font-weight: bold;
            color: #495057;
        }}
        
        .detail-value {{
            color: #6c757d;
            font-family: monospace;
        }}
        
        .comparison-section {{
            background-color: #fff3cd;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #ffc107;
            margin-bottom: 20px;
        }}
        
        .comparison-section h3 {{
            color: #856404;
            margin-top: 0;
        }}
        
        .metric-comparison {{
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            gap: 20px;
            align-items: center;
            margin-bottom: 15px;
        }}
        
        .metric-box {{
            text-align: center;
            padding: 15px;
            border-radius: 8px;
            background-color: white;
            border: 1px solid #dee2e6;
        }}
        
        .metric-arrow {{
            font-size: 24px;
            color: #6c757d;
        }}
        
        .metric-value {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .metric-error {{
            font-size: 14px;
            color: #6c757d;
        }}
        
        .metric-label {{
            font-size: 12px;
            color: #6c757d;
            margin-top: 5px;
        }}
        
        .secondary-metrics {{
            background-color: #e7f3ff;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #17a2b8;
        }}
        
        .secondary-metrics h4 {{
            color: #0c5460;
            margin-top: 0;
        }}
        
        .jvm-args {{
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 100px;
            overflow-y: auto;
        }}
        
        .significance-badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        
        .significance-yes {{
            background-color: #d4edda;
            color: #155724;
        }}
        
        .significance-no {{
            background-color: #f8d7da;
            color: #721c24;
        }}
        
        .status-improved {{
            color: #28a745;
            font-weight: bold;
        }}
        
        .status-regressed {{
            color: #dc3545;
            font-weight: bold;
        }}
        
        .status-unchanged {{
            color: #6c757d;
        }}
        
        .number {{
            text-align: right;
        }}
        
        .filtered-stats {{
            background-color: #e7f3ff;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
        }}
        
        .benchmark-name {{
            font-family: monospace;
            font-size: 12px;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>JMH Benchmark Comparison Report</h1>
        <p style="text-align: center; color: #6c757d;">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="summary">
            <h2 id="summaryTitle">Summary Statistics</h2>
            <div class="stats-grid" id="summaryStats">
                <div class="stat-card">
                    <div class="stat-value">{len(comparison_data)}</div>
                    <div class="stat-label">Total Benchmarks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{improved_count}</div>
                    <div class="stat-label">Improved</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{regressed_count}</div>
                    <div class="stat-label">Regressed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{avg_speedup:.2f}x</div>
                    <div class="stat-label">Avg Speedup</div>
                </div>
            </div>
        </div>
        
        <div class="controls">
            <h3>Filters and Controls</h3>
            <input type="text" id="benchmarkFilter" placeholder="Filter by benchmark name..." onkeyup="filterTable()">
            <select id="statusFilter" onchange="filterTable()">
                <option value="">All Status</option>
                <option value="improved">Improved</option>
                <option value="regressed">Regressed</option>
                <option value="unchanged">Unchanged</option>
            </select>
            <select id="modeFilter" onchange="filterTable()">
                <option value="">All Modes</option>
                <option value="thrpt">Throughput</option>
                <option value="avgt">Average Time</option>
                <option value="sample">Sample Time</option>
                <option value="ss">Single Shot</option>
            </select>
            <button onclick="resetFilters()">Reset Filters</button>
            <button onclick="exportFilteredData()">Export Filtered Data</button>
            
            <div class="filtered-stats" id="filteredStats"></div>
        </div>
        
        <table id="benchmarkTable">
            <thead>
                <tr>
                    <th onclick="sortTable(0)">Benchmark</th>
                    <th onclick="sortTable(1)">Mode</th>
                    <th onclick="sortTable(2)">Baseline Score</th>
                    <th onclick="sortTable(3)">Treatment Score</th>
                    <th onclick="sortTable(4)">Unit</th>
                    <th onclick="sortTable(5)">Speedup</th>
                    <th onclick="sortTable(6)">Statistical Significance</th>
                </tr>
            </thead>
            <tbody id="benchmarkTableBody">
"""
    
    # Add table rows
    for data in comparison_data:
        status_class = f"status-{data['status']}"
        improvement_sign = "+" if data['improvement_percent'] > 0 else ""
        sig_data = data['statistical_significance']
        significance_display = "Yes" if sig_data['is_significant'] else "No"
        
        html_content += f"""
                <tr>
                    <td class="benchmark-name" title="{data['benchmark']}">{data['benchmark']}</td>
                    <td>{data['mode']}</td>
                    <td class="number">{data['baseline_score']:.4f} ± {data['baseline_error']:.4f}</td>
                    <td class="number">{data['treatment_score']:.4f} ± {data['treatment_error']:.4f}</td>
                    <td>{data['unit']}</td>
                    <td class="number {status_class}">{data['speedup']:.2f}x</td>
                    <td>{significance_display}</td>
                </tr>
"""
    
    # Add JavaScript for interactivity
    html_content += f"""
            </tbody>
        </table>
    </div>
    
    <!-- Modal -->
    <div id="detailModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title" id="modalTitle">Benchmark Details</h2>
                <span class="close" onclick="closeModal()">&times;</span>
            </div>
            <div id="modalBody">
                <!-- Content will be dynamically populated -->
            </div>
        </div>
    </div>
    
    <script>
        let originalData = {json.dumps(comparison_data)};
        let filteredData = [...originalData];
        let currentSort = {{column: -1, direction: 'asc'}};
        
        function filterTable() {{
            const benchmarkFilter = document.getElementById('benchmarkFilter').value.toLowerCase();
            const statusFilter = document.getElementById('statusFilter').value;
            const modeFilter = document.getElementById('modeFilter').value;
            
            filteredData = originalData.filter(row => {{
                const matchesBenchmark = row.benchmark.toLowerCase().includes(benchmarkFilter);
                const matchesStatus = !statusFilter || row.status === statusFilter;
                const matchesMode = !modeFilter || row.mode === modeFilter;
                
                return matchesBenchmark && matchesStatus && matchesMode;
            }});
            
            updateTable();
            updateFilteredStats();
        }}
        
        function updateTable() {{
            const tbody = document.getElementById('benchmarkTableBody');
            tbody.innerHTML = '';
            
            filteredData.forEach((data, index) => {{
                const statusClass = `status-${{data.status}}`;
                const improvementSign = data.improvement_percent > 0 ? '+' : '';
                const significanceDisplay = data.statistical_significance.is_significant ? 'Yes' : 'No';
                
                const row = document.createElement('tr');
                row.onclick = () => showBenchmarkDetails(data);
                row.innerHTML = `
                    <td class="benchmark-name" title="${{data.benchmark}}">${{data.benchmark}}</td>
                    <td>${{data.mode}}</td>
                    <td class="number">${{data.baseline_score.toFixed(4)}} ± ${{data.baseline_error.toFixed(4)}}</td>
                    <td class="number">${{data.treatment_score.toFixed(4)}} ± ${{data.treatment_error.toFixed(4)}}</td>
                    <td>${{data.unit}}</td>
                    <td class="number ${{statusClass}}">${{data.speedup.toFixed(2)}}x</td>
                    <td>${{significanceDisplay}}</td>
                `;
                tbody.appendChild(row);
            }});
        }}
        
        function updateFilteredStats() {{
            if (filteredData.length === 0) {{
                document.getElementById('filteredStats').innerHTML = '<strong>No data matches current filters</strong>';
                document.getElementById('summaryTitle').textContent = 'Summary Statistics';
                return;
            }}
            
            const improvements = filteredData.map(d => d.improvement_percent);
            const speedups = filteredData.map(d => d.speedup);
            
            const avgImprovement = improvements.reduce((a, b) => a + b, 0) / improvements.length;
            const medianImprovement = improvements.sort((a, b) => a - b)[Math.floor(improvements.length / 2)];
            const avgSpeedup = speedups.reduce((a, b) => a + b, 0) / speedups.length;
            const medianSpeedup = speedups.sort((a, b) => a - b)[Math.floor(speedups.length / 2)];
            
            const improvedCount = filteredData.filter(d => d.status === 'improved').length;
            const regressedCount = filteredData.filter(d => d.status === 'regressed').length;
            const unchangedCount = filteredData.filter(d => d.status === 'unchanged').length;
            
            // Calculate regression-specific statistics for filtered data
            const regressions = filteredData.filter(d => d.status === 'regressed').map(d => d.improvement_percent);
            const regressionSpeedups = filteredData.filter(d => d.status === 'regressed').map(d => d.speedup);
            
            const avgRegression = regressions.length > 0 ? regressions.reduce((a, b) => a + b, 0) / regressions.length : 0;
            const medianRegression = regressions.length > 0 ? regressions.sort((a, b) => a - b)[Math.floor(regressions.length / 2)] : 0;
            const avgRegressionSpeedup = regressionSpeedups.length > 0 ? regressionSpeedups.reduce((a, b) => a + b, 0) / regressionSpeedups.length : 1.0;
            const medianRegressionSpeedup = regressionSpeedups.length > 0 ? regressionSpeedups.sort((a, b) => a - b)[Math.floor(regressionSpeedups.length / 2)] : 1.0;
            
            // Update summary statistics if filtered
            if (filteredData.length < originalData.length) {{
                document.getElementById('summaryTitle').textContent = 'Summary Statistics (Filtered)';
                document.getElementById('summaryStats').innerHTML = `
                    <div class="stat-card">
                        <div class="stat-value">${{filteredData.length}}</div>
                        <div class="stat-label">Total Benchmarks</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${{improvedCount}}</div>
                        <div class="stat-label">Improved</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${{regressedCount}}</div>
                        <div class="stat-label">Regressed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${{avgSpeedup.toFixed(2)}}x</div>
                        <div class="stat-label">Avg Speedup</div>
                    </div>
                `;
            }} else {{
                document.getElementById('summaryTitle').textContent = 'Summary Statistics';
                // Reset to original values
                document.getElementById('summaryStats').innerHTML = `
                    <div class="stat-card">
                        <div class="stat-value">{len(comparison_data)}</div>
                        <div class="stat-label">Total Benchmarks</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{improved_count}</div>
                        <div class="stat-label">Improved</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{regressed_count}</div>
                        <div class="stat-label">Regressed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{avg_speedup:.2f}x</div>
                        <div class="stat-label">Avg Speedup</div>
                    </div>
                `;
            }}
            
            document.getElementById('filteredStats').innerHTML = `
                <strong>Filtered Results:</strong> 
                ${{filteredData.length}} benchmarks | 
                ${{improvedCount}} improved | 
                ${{regressedCount}} regressed | 
                ${{unchangedCount}} unchanged | 
                Avg: ${{avgImprovement.toFixed(2)}}% | 
                Median: ${{medianImprovement.toFixed(2)}}% | 
                Avg Speedup: ${{avgSpeedup.toFixed(2)}}x
            `;
        }}
        
        function sortTable(columnIndex) {{
            const headers = document.querySelectorAll('th');
            
            // Remove existing sort classes
            headers.forEach(header => {{
                header.classList.remove('sorted-asc', 'sorted-desc');
            }});
            
            // Determine sort direction
            const direction = (currentSort.column === columnIndex && currentSort.direction === 'asc') ? 'desc' : 'asc';
            currentSort = {{column: columnIndex, direction: direction}};
            
            // Add sort class to current header
            headers[columnIndex].classList.add(direction === 'asc' ? 'sorted-asc' : 'sorted-desc');
            
            // Sort the data
            filteredData.sort((a, b) => {{
                let aVal, bVal;
                
                switch(columnIndex) {{
                    case 0: aVal = a.benchmark; bVal = b.benchmark; break;
                    case 1: aVal = a.mode; bVal = b.mode; break;
                    case 2: aVal = a.baseline_score; bVal = b.baseline_score; break;
                    case 3: aVal = a.treatment_score; bVal = b.treatment_score; break;
                    case 4: aVal = a.unit; bVal = b.unit; break;
                    case 5: aVal = a.speedup; bVal = b.speedup; break;
                    case 6: aVal = a.statistical_significance.is_significant; bVal = b.statistical_significance.is_significant; break;
                    default: return 0;
                }}
                
                if (typeof aVal === 'number' && typeof bVal === 'number') {{
                    return direction === 'asc' ? aVal - bVal : bVal - aVal;
                }} else if (typeof aVal === 'boolean' && typeof bVal === 'boolean') {{
                    return direction === 'asc' ? (aVal ? 1 : 0) - (bVal ? 1 : 0) : (bVal ? 1 : 0) - (aVal ? 1 : 0);
                }} else {{
                    const comparison = String(aVal).localeCompare(String(bVal));
                    return direction === 'asc' ? comparison : -comparison;
                }}
            }});
            
            updateTable();
        }}
        
        function resetFilters() {{
            document.getElementById('benchmarkFilter').value = '';
            document.getElementById('statusFilter').value = '';
            document.getElementById('modeFilter').value = '';
            filteredData = [...originalData];
            updateTable();
            updateFilteredStats();
        }}
        
        function exportFilteredData() {{
            const csvContent = [
                ['Benchmark', 'Mode', 'Threads', 'Baseline Score', 'Treatment Score', 'Unit', 'Improvement %', 'Speedup', 'Status'],
                ...filteredData.map(d => [
                    d.benchmark, d.mode, d.threads, d.baseline_score, d.treatment_score, 
                    d.unit, d.improvement_percent, d.speedup, d.status
                ])
            ].map(row => row.join(',')).join('\\n');
            
            const blob = new Blob([csvContent], {{ type: 'text/csv' }});
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'filtered_benchmark_results.csv';
            a.click();
            window.URL.revokeObjectURL(url);
        }}
        
        function showBenchmarkDetails(data) {{
            const modal = document.getElementById('detailModal');
            const modalTitle = document.getElementById('modalTitle');
            const modalBody = document.getElementById('modalBody');
            
            modalTitle.textContent = data.benchmark;
            
            const statusClass = `status-${{data.status}}`;
            const improvementSign = data.improvement_percent > 0 ? '+' : '';
            const significanceClass = data.statistical_significance.is_significant ? 'significance-yes' : 'significance-no';
            const significanceText = data.statistical_significance.is_significant ? 'Yes' : 'No';
            
            // Generate secondary metrics HTML
            let baselineSecondaryHtml = '';
            let treatmentSecondaryHtml = '';
            
            if (data.baseline_details.secondary_metrics && Object.keys(data.baseline_details.secondary_metrics).length > 0) {{
                baselineSecondaryHtml = Object.entries(data.baseline_details.secondary_metrics).map(([key, value]) => `
                    <div class="detail-row">
                        <span class="detail-label">${{key}}:</span>
                        <span class="detail-value">${{value.score?.toFixed(4) || 'N/A'}} ${{value.scoreUnit || ''}}</span>
                    </div>
                `).join('');
            }}
            
            if (data.treatment_details.secondary_metrics && Object.keys(data.treatment_details.secondary_metrics).length > 0) {{
                treatmentSecondaryHtml = Object.entries(data.treatment_details.secondary_metrics).map(([key, value]) => `
                    <div class="detail-row">
                        <span class="detail-label">${{key}}:</span>
                        <span class="detail-value">${{value.score?.toFixed(4) || 'N/A'}} ${{value.scoreUnit || ''}}</span>
                    </div>
                `).join('');
            }}
            
            modalBody.innerHTML = `
                <div class="comparison-section">
                    <h3>Performance Comparison</h3>
                    <div class="metric-comparison">
                        <div class="metric-box">
                            <div class="metric-value">${{data.baseline_score.toFixed(4)}}</div>
                            <div class="metric-error">± ${{data.baseline_error.toFixed(4)}}</div>
                            <div class="metric-label">Baseline (${{data.baseline_vm}})</div>
                        </div>
                        <div class="metric-arrow">→</div>
                        <div class="metric-box">
                            <div class="metric-value">${{data.treatment_score.toFixed(4)}}</div>
                            <div class="metric-error">± ${{data.treatment_error.toFixed(4)}}</div>
                            <div class="metric-label">Treatment (${{data.treatment_vm}})</div>
                        </div>
                    </div>
                    <div style="text-align: center; margin: 15px 0;">
                        <strong>Unit:</strong> ${{data.unit}} | 
                        <strong class="${{statusClass}}">Improvement:</strong> <span class="${{statusClass}}">${{improvementSign}}${{data.improvement_percent.toFixed(2)}}%</span> | 
                        <strong class="${{statusClass}}">Speedup:</strong> <span class="${{statusClass}}">${{data.speedup.toFixed(2)}}x</span>
                    </div>
                    <div style="text-align: center;">
                        <strong>Statistical Significance:</strong> 
                        <span class="significance-badge ${{significanceClass}}">${{significanceText}}</span>
                        <span style="margin-left: 10px;">(${{data.statistical_significance.confidence_level}})</span>
                    </div>
                </div>
                
                <div class="detail-grid">
                    <div class="detail-section">
                        <h3>Baseline Details</h3>
                        <div class="detail-row">
                            <span class="detail-label">JDK:</span>
                            <span class="detail-value">${{data.baseline_details.jdk || 'N/A'}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">VM Name:</span>
                            <span class="detail-value">${{data.baseline_details.vm_name || 'N/A'}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">VM Version:</span>
                            <span class="detail-value">${{data.baseline_details.vm_version || 'N/A'}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Mode:</span>
                            <span class="detail-value">${{data.mode}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Threads:</span>
                            <span class="detail-value">${{data.threads}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Forks:</span>
                            <span class="detail-value">${{data.baseline_details.forks}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Warmup Iterations:</span>
                            <span class="detail-value">${{data.baseline_details.warmup_iterations}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Warmup Time:</span>
                            <span class="detail-value">${{data.baseline_details.warmup_time || 'N/A'}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Measurement Iterations:</span>
                            <span class="detail-value">${{data.baseline_details.measurement_iterations}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Measurement Time:</span>
                            <span class="detail-value">${{data.baseline_details.measurement_time || 'N/A'}}</span>
                        </div>
                        ${{data.baseline_details.score_confidence && data.baseline_details.score_confidence.length > 0 ? `
                        <div class="detail-row">
                            <span class="detail-label">Score Confidence:</span>
                            <span class="detail-value">[${{data.baseline_details.score_confidence.map(x => x.toFixed(4)).join(', ')}}]</span>
                        </div>
                        ` : ''}}
                        <div style="margin-top: 15px;">
                            <strong>JVM Arguments:</strong>
                            <div class="jvm-args">${{data.baseline_details.jvm_args.length > 0 ? data.baseline_details.jvm_args.join('\\n') : 'None'}}</div>
                        </div>
                        ${{data.baseline_details.params && Object.keys(data.baseline_details.params).length > 0 ? `
                        <div style="margin-top: 15px;">
                            <strong>Parameters:</strong>
                            <div class="jvm-args">${{Object.entries(data.baseline_details.params).map(([key, value]) => `${{key}}: ${{value}}`).join('\\n')}}</div>
                        </div>
                        ` : ''}}
                    </div>
                    
                    <div class="detail-section">
                        <h3>Treatment Details</h3>
                        <div class="detail-row">
                            <span class="detail-label">JDK:</span>
                            <span class="detail-value">${{data.treatment_details.jdk || 'N/A'}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">VM Name:</span>
                            <span class="detail-value">${{data.treatment_details.vm_name || 'N/A'}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">VM Version:</span>
                            <span class="detail-value">${{data.treatment_details.vm_version || 'N/A'}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Mode:</span>
                            <span class="detail-value">${{data.mode}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Threads:</span>
                            <span class="detail-value">${{data.threads}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Forks:</span>
                            <span class="detail-value">${{data.treatment_details.forks}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Warmup Iterations:</span>
                            <span class="detail-value">${{data.treatment_details.warmup_iterations}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Warmup Time:</span>
                            <span class="detail-value">${{data.treatment_details.warmup_time || 'N/A'}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Measurement Iterations:</span>
                            <span class="detail-value">${{data.treatment_details.measurement_iterations}}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Measurement Time:</span>
                            <span class="detail-value">${{data.treatment_details.measurement_time || 'N/A'}}</span>
                        </div>
                        ${{data.treatment_details.score_confidence && data.treatment_details.score_confidence.length > 0 ? `
                        <div class="detail-row">
                            <span class="detail-label">Score Confidence:</span>
                            <span class="detail-value">[${{data.treatment_details.score_confidence.map(x => x.toFixed(4)).join(', ')}}]</span>
                        </div>
                        ` : ''}}
                        <div style="margin-top: 15px;">
                            <strong>JVM Arguments:</strong>
                            <div class="jvm-args">${{data.treatment_details.jvm_args.length > 0 ? data.treatment_details.jvm_args.join('\\n') : 'None'}}</div>
                        </div>
                        ${{data.treatment_details.params && Object.keys(data.treatment_details.params).length > 0 ? `
                        <div style="margin-top: 15px;">
                            <strong>Parameters:</strong>
                            <div class="jvm-args">${{Object.entries(data.treatment_details.params).map(([key, value]) => `${{key}}: ${{value}}`).join('\\n')}}</div>
                        </div>
                        ` : ''}}
                    </div>
                </div>
                
                ${{baselineSecondaryHtml || treatmentSecondaryHtml ? `
                <div class="detail-grid">
                    ${{baselineSecondaryHtml ? `
                    <div class="secondary-metrics">
                        <h4>Baseline Secondary Metrics</h4>
                        ${{baselineSecondaryHtml}}
                    </div>
                    ` : '<div></div>'}}
                    ${{treatmentSecondaryHtml ? `
                    <div class="secondary-metrics">
                        <h4>Treatment Secondary Metrics</h4>
                        ${{treatmentSecondaryHtml}}
                    </div>
                    ` : '<div></div>'}}
                </div>
                ` : ''}}
            `;
            
            modal.style.display = 'block';
        }}
        
        function closeModal() {{
            document.getElementById('detailModal').style.display = 'none';
        }}
        
        // Close modal when clicking outside of it
        window.onclick = function(event) {{
            const modal = document.getElementById('detailModal');
            if (event.target === modal) {{
                closeModal();
            }}
        }}
        
        // Close modal with Escape key
        document.addEventListener('keydown', function(event) {{
            if (event.key === 'Escape') {{
                closeModal();
            }}
        }});
        
        // Initialize
        updateFilteredStats();
        updateTable(); // Ensure click handlers are attached to initial rows
    </script>
</body>
</html>
"""
    
    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Interactive HTML report generated: {output_file}")


def main(basepath):
    """Main function to generate the benchmark comparison report."""
    print("JMH Benchmark Comparison Report Generator")
    print("=" * 50)
    
    # Check if baseline and treatment directories exist
    baseline_dir = Path(basepath, "baseline")
    treatment_dir = Path(basepath, "treatment")
    
    if not baseline_dir.exists():
        print(f"Error: Baseline directory '{baseline_dir}' does not exist")
        print("Please create the baseline directory and add your OpenJDK JMH JSON files")
        return
    
    if not treatment_dir.exists():
        print(f"Error: Treatment directory '{treatment_dir}' does not exist")
        print("Please create the treatment directory and add your GraalVM CE JMH JSON files")
        return
    
    # Load benchmark results
    print("Loading baseline results...")
    baseline_results = load_benchmark_results(baseline_dir)
    
    print("Loading treatment results...")
    treatment_results = load_benchmark_results(treatment_dir)
    
    if not baseline_results:
        print("No baseline results found. Please add JMH JSON files to the baseline directory.")
        return
    
    if not treatment_results:
        print("No treatment results found. Please add JMH JSON files to the treatment directory.")
        return
    
    print(f"Found {len(baseline_results)} baseline result files")
    print(f"Found {len(treatment_results)} treatment result files")
    
    # Create comparison data
    print("Creating comparison data...")
    comparison_data = create_comparison_data(baseline_results, treatment_results)
    
    if not comparison_data:
        print("No matching benchmarks found between baseline and treatment results.")
        return
    
    print(f"Found {len(comparison_data)} matching benchmarks")
    
    # Generate HTML report
    print("Generating HTML report...")
    generate_html_report(comparison_data, output_file=basepath + "/benchmark_comparison_report.html")
    
    print("Done! Open 'benchmark_comparison_report.html' in your browser to view the report.")


if __name__ == "__main__":
    if len(sys.argv) <= 1 :
        print("Usage: " + sys.argv[0] + " <basepath-for-results-dir>")
    else: 
        main(sys.argv[1])
