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


def parse_details_file(basepath: Path) -> Dict[str, str]:
    """Parse the details file containing experiment information."""
    details_file = basepath / "details"
    details = {}
    
    if not details_file.exists():
        print(f"Details file not found at {details_file}")
        return details
    
    try:
        with open(details_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"Loading experiment details from {details_file}")
        
        # Parse the details file format
        current_key = None
        current_value = []
        
        for line in content.split('\n'):
            line = line.rstrip()
            
            # Check if this is a new section header (starts with "-")
            if line.startswith('-'):
                # Save previous key-value pair if exists
                if current_key:
                    details[current_key] = '\n'.join(current_value).strip()
                
                # Start new key - remove the leading "-" and any trailing ":"
                current_key = line[1:].strip()
                if current_key.endswith(':'):
                    current_key = current_key[:-1].strip()
                current_value = []
            
            elif current_key is not None:
                # This is content for the current section
                # Preserve the line as-is, including empty lines for formatting
                current_value.append(line)
        
        # Don't forget the last key-value pair
        if current_key:
            details[current_key] = '\n'.join(current_value).strip()
        
        print(f"Parsed {len(details)} details sections")
        return details
        
    except Exception as e:
        print(f"Error parsing details file {details_file}: {e}")
        return {}


def calculate_statistical_significance(baseline: BenchmarkResult, treatment: BenchmarkResult) -> Dict:
    """Calculate statistical significance using approximate t-test."""
    # Check for insufficient samples - need at least 2 measurement iterations for each
    baseline_iterations = baseline.measurement_iterations
    treatment_iterations = treatment.measurement_iterations
    
    # If either has only 1 sample or insufficient data, return insufficient data indicator
    if (baseline_iterations <= 1 or treatment_iterations <= 1):
        print(f"WARNING: Insufficient data to compute statistical difference for benchmark '{baseline.benchmark}' - "
              f"baseline iterations: {baseline_iterations}, treatment iterations: {treatment_iterations}, "
              f"baseline forks: {baseline.forks}, treatment forks: {treatment.forks}. "
              f"Need at least 2 measurement iterations for both baseline and treatment to compute statistical significance.")
        return {
            'is_significant': None,  # None indicates insufficient data
            'confidence_level': '?',
            't_statistic': None,
            'insufficient_data': True
        }
    
    # Use score error as estimate of standard error
    # Approximate degrees of freedom (conservative estimate)
    df = min(baseline_iterations + treatment_iterations - 2, 30)
    
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
            'confidence_level': 'N/A',
            't_statistic': 0,
            'insufficient_data': False
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
        't_statistic': t_stat,
        'insufficient_data': False
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
            print(key)
            baseline_map[key] = result
    
    for file_name, results in treatment_results.items():
        for result in results:
            params = '&'.join(f'{k}={result.params[k]}' for k in sorted(result.params))
            key = f"{result.benchmark}_{result.mode}_{result.threads}_{params}"
            print(key)
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


def generate_html_report(comparison_data: List[Dict], experiment_details: Dict[str, str] = None, output_file: str = "benchmark_comparison_report.html"):
    """Generate an interactive HTML report."""
    
    if not comparison_data:
        print("No comparison data available to generate report")
        return
    
    # Remove common prefix and suffix from benchmark names
    def find_common_prefix_suffix(names):
        if not names:
            return "", ""
        
        # Find common prefix
        prefix = names[0]
        for name in names[1:]:
            while prefix and not name.startswith(prefix):
                prefix = prefix[:-1]
        
        # Find common suffix
        suffix = names[0]
        for name in names[1:]:
            while suffix and not name.endswith(suffix):
                suffix = suffix[1:]
        
        return prefix, suffix
    
    # Get all benchmark names
    benchmark_names = [data['benchmark'] for data in comparison_data]
    common_prefix, common_suffix = find_common_prefix_suffix(benchmark_names)
    
    # Remove common prefix and suffix, but ensure we don't remove everything
    for data in comparison_data:
        original_name = data['benchmark']
        trimmed_name = original_name
        
        # Remove prefix if it exists and leaves meaningful content
        if common_prefix and len(common_prefix) > 0:
            trimmed_name = trimmed_name[len(common_prefix):]
        
        # Remove suffix if it exists and leaves meaningful content
        if common_suffix and len(common_suffix) > 0 and len(trimmed_name) > len(common_suffix):
            trimmed_name = trimmed_name[:-len(common_suffix)]
        
        # Ensure we have at least some meaningful name left
        if not trimmed_name or len(trimmed_name.strip()) == 0:
            trimmed_name = original_name
        
        # Clean up any leading/trailing dots or separators that might be left
        trimmed_name = trimmed_name.strip('.')
        if not trimmed_name:
            trimmed_name = original_name
            
        data['display_name'] = trimmed_name
    
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
    
    # Determine the report title
    report_title = "JMH Benchmark Comparison Report"
    if experiment_details and 'Title' in experiment_details:
        report_title = experiment_details['Title'].strip()
    
    # Generate HTML
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>""" + report_title + """</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // Fallback chart implementation using SVG when Chart.js fails to load
        let chartJsLoaded = false;
        
        // Check if Chart.js loaded successfully
        window.addEventListener('load', function() {
            chartJsLoaded = typeof Chart !== 'undefined';
            if (!chartJsLoaded) {
                console.log('Chart.js not available, using fallback SVG chart');
            }
        });
    </script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        
        .summary {
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
            border-left: 4px solid #007bff;
        }
        
        .summary h2 {
            margin-top: 0;
            color: #007bff;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background-color: white;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #e9ecef;
            text-align: center;
        }
        
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #007bff;
        }
        
        .stat-label {
            font-size: 14px;
            color: #6c757d;
            margin-top: 5px;
        }
        
        .controls {
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        
        .controls input, .controls select {
            margin: 5px;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        
        .controls button {
            padding: 8px 16px;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin: 5px;
        }
        
        .controls button:hover {
            background-color: #0056b3;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        
        th {
            background-color: #f8f9fa;
            font-weight: 600;
            cursor: pointer;
            user-select: none;
            position: relative;
            text-align: center;
        }
        
        th:hover {
            background-color: #e9ecef;
        }
        
        th.sorted-asc::after {
            content: ' ↑';
            position: absolute;
            right: 8px;
        }
        
        th.sorted-desc::after {
            content: ' ↓';
            position: absolute;
            right: 8px;
        }
        
        tr:hover {
            background-color: #f8f9fa;
        }
        
        tbody tr {
            cursor: pointer;
        }
        
        tbody tr:hover {
            background-color: #e3f2fd;
        }
        
        /* Modal styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0,0,0,0.4);
        }
        
        .modal-content {
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
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #007bff;
        }
        
        .modal-title {
            color: #333;
            margin: 0;
            font-size: 24px;
        }
        
        .close {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            transition: color 0.3s;
        }
        
        .close:hover,
        .close:focus {
            color: #000;
            text-decoration: none;
        }
        
        .detail-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .detail-section {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }
        
        .detail-section h3 {
            color: #007bff;
            margin-top: 0;
            margin-bottom: 15px;
        }
        
        .detail-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            padding: 5px 0;
            border-bottom: 1px solid #e9ecef;
        }
        
        .detail-label {
            font-weight: bold;
            color: #495057;
        }
        
        .detail-value {
            color: #6c757d;
            font-family: monospace;
        }
        
        .comparison-section {
            background-color: #fff3cd;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #ffc107;
            margin-bottom: 20px;
        }
        
        .comparison-section h3 {
            color: #856404;
            margin-top: 0;
        }
        
        .metric-comparison {
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            gap: 20px;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .metric-box {
            text-align: center;
            padding: 15px;
            border-radius: 8px;
            background-color: white;
            border: 1px solid #dee2e6;
        }
        
        .metric-arrow {
            font-size: 24px;
            color: #6c757d;
        }
        
        .metric-value {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .metric-error {
            font-size: 14px;
            color: #6c757d;
        }
        
        .metric-label {
            font-size: 12px;
            color: #6c757d;
            margin-top: 5px;
        }
        
        .secondary-metrics {
            background-color: #e7f3ff;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #17a2b8;
        }
        
        .secondary-metrics h4 {
            color: #0c5460;
            margin-top: 0;
        }
        
        .jvm-args {
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 100px;
            overflow-y: auto;
        }
        
        .significance-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        
        .significance-yes {
            background-color: #d4edda;
            color: #155724;
        }
        
        .significance-no {
            background-color: #f8d7da;
            color: #721c24;
        }
        
        .status-improved {
            color: #28a745;
            font-weight: bold;
        }
        
        .status-regressed {
            color: #dc3545;
            font-weight: bold;
        }
        
        .status-unchanged {
            color: #6c757d;
        }
        
        .number {
            text-align: right;
        }
        
        .filtered-stats {
            background-color: #e7f3ff;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
        }
        
        .benchmark-name {
            font-family: monospace;
            font-size: 12px;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>""" + report_title + """</h1>
        <p style="text-align: center; color: #6c757d;">Generated on """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
        
        """ + (f'<div style="text-align: center; margin-bottom: 20px;"><a href="#" onclick="showExperimentDetails(); return false;" style="color: #007bff; text-decoration: none; font-weight: bold;">📋 Experiment Details</a></div>' if experiment_details else '') + """
        
        <div class="summary">
            <h2 id="summaryTitle">Summary Statistics</h2>
            <div class="stats-grid" id="summaryStats">
                <div class="stat-card">
                    <div class="stat-value">""" + str(len(comparison_data)) + """</div>
                    <div class="stat-label">Total Benchmarks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">""" + str(improved_count) + """</div>
                    <div class="stat-label">Improved</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">""" + str(regressed_count) + """</div>
                    <div class="stat-label">Regressed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">""" + f"{avg_speedup:.2f}x" + """</div>
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
            <select id="significanceFilter" onchange="filterTable()">
                <option value="">All Significance</option>
                <option value="significant">Statistically Significant</option>
                <option value="not_significant">Not Significant</option>
                <option value="insufficient_data">Insufficient Data (?)</option>
            </select>
            <button onclick="resetFilters()">Reset Filters</button>
            <button onclick="exportFilteredData()">Export Filtered Data</button>
            <button onclick="showBarChart()">Show Bar Chart</button>
            
            <div class="filtered-stats" id="filteredStats"></div>
        </div>
        
        <table id="benchmarkTable">
            <thead>
                <tr>
                    <th onclick="sortTable(0)" title="Benchmark Name">Benchmark</th>
                    <th onclick="sortTable(1)" title="Baseline Score with Error">Baseline</th>
                    <th onclick="sortTable(2)" title="Treatment Score with Error">Treatment</th>
                    <th onclick="sortTable(3)" title="JMH Mode">Mode</th>
                    <th onclick="sortTable(4)" title="Measurement Unit">Unit</th>
                    <th onclick="sortTable(5)" title="Performance Speedup Factor">Speedup</th>
                    <th onclick="sortTable(6)" title="Statistical Significance">SS</th>
                </tr>
            </thead>
            <tbody id="benchmarkTableBody">
"""
    
    # Add table rows
    for data in comparison_data:
        status_class = f"status-{data['status']}"
        sig_data = data['statistical_significance']
        
        # Handle insufficient data case
        if sig_data.get('insufficient_data', False):
            significance_display = "?"
        else:
            significance_display = "Yes" if sig_data['is_significant'] else "No"
        
        html_content += f"""
                <tr>
                    <td class="benchmark-name" title="{data['benchmark']}">{data['display_name']}</td>
                    <td class="number">{data['baseline_score']:.4f} ± {data['baseline_error']:.4f}</td>
                    <td class="number">{data['treatment_score']:.4f} ± {data['treatment_error']:.4f}</td>
                    <td style="text-align: center;">{data['mode']}</td>
                    <td style="text-align: center;">{data['unit']}</td>
                    <td class="number {status_class}" style="text-align: center;">{data['speedup']:.2f}x</td>
                    <td style="text-align: center;">{significance_display}</td>
                </tr>
"""
    
    # Add JavaScript for interactivity (patched error bar plugin placement)
    html_content += """
            </tbody>
        </table>
    </div>
    
    <!-- Detail Modal -->
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
    
    <!-- Experiment Details Modal -->
    <div id="experimentModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">📋 Experiment Details</h2>
                <span class="close" onclick="closeExperimentModal()">&times;</span>
            </div>
            <div id="experimentModalBody">
                <!-- Content will be dynamically populated -->
            </div>
        </div>
    </div>
    
    <!-- Chart Modal -->
    <div id="chartModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Benchmark Speedup Chart</h2>
                <span class="close" onclick="closeChartModal()">&times;</span>
            </div>
            <div style="height: 400px; position: relative;">
                <canvas id="benchmarkChart"></canvas>
            </div>
        </div>
    </div>
    
    <script>
        let originalData = """ + json.dumps(comparison_data) + """;
        let filteredData = [...originalData];
        let currentSort = {column: -1, direction: 'asc'};
        let experimentDetails = """ + (json.dumps(experiment_details) if experiment_details else 'null') + """;
        
        function filterTable() {
            const benchmarkFilter = document.getElementById('benchmarkFilter').value.toLowerCase();
            const statusFilter = document.getElementById('statusFilter').value;
            const modeFilter = document.getElementById('modeFilter').value;
            const significanceFilter = document.getElementById('significanceFilter').value;
            
            filteredData = originalData.filter(row => {
                const matchesBenchmark = row.benchmark.toLowerCase().includes(benchmarkFilter);
                const matchesStatus = !statusFilter || row.status === statusFilter;
                const matchesMode = !modeFilter || row.mode === modeFilter;
                const matchesSignificance = !significanceFilter || 
                    (significanceFilter === 'significant' && row.statistical_significance.is_significant) ||
                    (significanceFilter === 'not_significant' && !row.statistical_significance.is_significant) ||
                    (significanceFilter === 'insufficient_data' && row.statistical_significance.insufficient_data);
                
                return matchesBenchmark && matchesStatus && matchesMode && matchesSignificance;
            });
            
            updateTable();
            updateFilteredStats();
        }
        
        function updateTable() {
            const tbody = document.getElementById('benchmarkTableBody');
            tbody.innerHTML = '';
            
            filteredData.forEach((data, index) => {
                const statusClass = `status-${data.status}`;
                
                // Handle insufficient data case
                let significanceDisplay;
                if (data.statistical_significance.insufficient_data) {
                    significanceDisplay = '?';
                } else {
                    significanceDisplay = data.statistical_significance.is_significant ? 'Yes' : 'No';
                }
                
                const row = document.createElement('tr');
                row.onclick = () => showBenchmarkDetails(data);
                row.innerHTML = `
                    <td class="benchmark-name" title="${data.benchmark}">${data.display_name || data.benchmark}</td>
                    <td class="number">${data.baseline_score.toFixed(4)} ± ${data.baseline_error.toFixed(4)}</td>
                    <td class="number">${data.treatment_score.toFixed(4)} ± ${data.treatment_error.toFixed(4)}</td>
                    <td style="text-align: center;">${data.mode}</td>
                    <td style="text-align: center;">${data.unit}</td>
                    <td class="number ${statusClass}" style="text-align: center;">${data.speedup.toFixed(2)}x</td>
                    <td style="text-align: center;">${significanceDisplay}</td>
                `;
                tbody.appendChild(row);
            });
        }
        
        function updateFilteredStats() {
            if (filteredData.length === 0) {
                document.getElementById('filteredStats').innerHTML = '<strong>No data matches current filters</strong>';
                document.getElementById('summaryTitle').textContent = 'Summary Statistics';
                return;
            }
            
            const improvements = filteredData.map(d => d.improvement_percent);
            const speedups = filteredData.map(d => d.speedup);
            
            const avgImprovement = improvements.reduce((a, b) => a + b, 0) / improvements.length;
            const medianImprovement = improvements.slice().sort((a, b) => a - b)[Math.floor(improvements.length / 2)];
            const avgSpeedup = speedups.reduce((a, b) => a + b, 0) / speedups.length;
            const medianSpeedup = speedups.slice().sort((a, b) => a - b)[Math.floor(speedups.length / 2)];
            
            const improvedCount = filteredData.filter(d => d.status === 'improved').length;
            const regressedCount = filteredData.filter(d => d.status === 'regressed').length;
            const unchangedCount = filteredData.filter(d => d.status === 'unchanged').length;
            
            // Update summary statistics if filtered
            if (filteredData.length < originalData.length) {
                document.getElementById('summaryTitle').textContent = 'Summary Statistics (Filtered)';
                document.getElementById('summaryStats').innerHTML = `
                    <div class="stat-card">
                        <div class="stat-value">${filteredData.length}</div>
                        <div class="stat-label">Total Benchmarks</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${improvedCount}</div>
                        <div class="stat-label">Improved</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${regressedCount}</div>
                        <div class="stat-label">Regressed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${avgSpeedup.toFixed(2)}x</div>
                        <div class="stat-label">Avg Speedup</div>
                    </div>
                `;
            } else {
                document.getElementById('summaryTitle').textContent = 'Summary Statistics';
                // Reset to original values
                document.getElementById('summaryStats').innerHTML = `
                    <div class="stat-card">
                        <div class="stat-value">""" + str(len(comparison_data)) + """</div>
                        <div class="stat-label">Total Benchmarks</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">""" + str(improved_count) + """</div>
                        <div class="stat-label">Improved</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">""" + str(regressed_count) + """</div>
                        <div class="stat-label">Regressed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">""" + f"{avg_speedup:.2f}x" + """</div>
                        <div class="stat-label">Avg Speedup</div>
                    </div>
                `;
            }
            
            document.getElementById('filteredStats').innerHTML = `
                <strong>Filtered Results:</strong> 
                ${filteredData.length} benchmarks | 
                ${improvedCount} improved | 
                ${regressedCount} regressed | 
                ${unchangedCount} unchanged | 
                Avg: ${avgImprovement.toFixed(2)}% | 
                Median: ${medianImprovement.toFixed(2)}% | 
                Avg Speedup: ${avgSpeedup.toFixed(2)}x
            `;
        }
        
        function sortTable(columnIndex) {
            const headers = document.querySelectorAll('th');
            
            // Remove existing sort classes
            headers.forEach(header => {
                header.classList.remove('sorted-asc', 'sorted-desc');
            });
            
            // Determine sort direction
            const direction = (currentSort.column === columnIndex && currentSort.direction === 'asc') ? 'desc' : 'asc';
            currentSort = {column: columnIndex, direction: direction};
            
            // Add sort class to current header
            headers[columnIndex].classList.add(direction === 'asc' ? 'sorted-asc' : 'sorted-desc');
            
            // Sort the data
            filteredData.sort((a, b) => {
                let aVal, bVal;
                
                switch(columnIndex) {
                    case 0: aVal = a.benchmark; bVal = b.benchmark; break;
                    case 1: aVal = a.baseline_score; bVal = b.baseline_score; break;
                    case 2: aVal = a.treatment_score; bVal = b.treatment_score; break;
                    case 3: aVal = a.mode; bVal = b.mode; break;
                    case 4: aVal = a.unit; bVal = b.unit; break;
                    case 5: aVal = a.speedup; bVal = b.speedup; break;
                    case 6: aVal = a.statistical_significance.is_significant; bVal = b.statistical_significance.is_significant; break;
                    default: return 0;
                }
                
                if (typeof aVal === 'number' && typeof bVal === 'number') {
                    return direction === 'asc' ? aVal - bVal : bVal - aVal;
                } else if (typeof aVal === 'boolean' && typeof bVal === 'boolean') {
                    return direction === 'asc' ? (aVal ? 1 : 0) - (bVal ? 1 : 0) : (bVal ? 1 : 0) - (aVal ? 1 : 0);
                } else {
                    const comparison = String(aVal).localeCompare(String(bVal));
                    return direction === 'asc' ? comparison : -comparison;
                }
            });
            
            updateTable();
        }
        
        function resetFilters() {
            document.getElementById('benchmarkFilter').value = '';
            document.getElementById('statusFilter').value = '';
            document.getElementById('modeFilter').value = '';
            document.getElementById('significanceFilter').value = '';
            filteredData = [...originalData];
            updateTable();
            updateFilteredStats();
        }
        
        function exportFilteredData() {
            const csvContent = [
                ['Benchmark', 'Mode', 'Threads', 'Baseline Score', 'Treatment Score', 'Unit', 'Improvement %', 'Speedup', 'Status'],
                ...filteredData.map(d => [
                    d.benchmark, d.mode, d.threads, d.baseline_score, d.treatment_score, 
                    d.unit, d.improvement_percent, d.speedup, d.status
                ])
            ].map(row => row.join(',')).join('\\n');
            
            const blob = new Blob([csvContent], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'filtered_benchmark_results.csv';
            a.click();
            window.URL.revokeObjectURL(url);
        }
        
        function showExperimentDetails() {
            if (!experimentDetails) {
                alert('No experiment details available');
                return;
            }
            
            const modal = document.getElementById('experimentModal');
            const modalBody = document.getElementById('experimentModalBody');
            
            let detailsHtml = '<div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #007bff;">';
            
            Object.entries(experimentDetails).forEach(([key, value], index) => {
                if (index > 0) {
                    detailsHtml += '<hr style="margin: 20px 0; border: none; border-top: 1px solid #dee2e6;">';
                }
                detailsHtml += `
                    <div style="margin-bottom: 15px;">
                        <h4 style="color: #007bff; margin: 0 0 10px 0; font-size: 16px;">${key}</h4>
                        <div style="background-color: white; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto;">${value.replace(/\\n/g, '<br>')}</div>
                    </div>
                `;
            });
            
            detailsHtml += '</div>';
            modalBody.innerHTML = detailsHtml;
            modal.style.display = 'block';
        }
        
        function closeExperimentModal() {
            document.getElementById('experimentModal').style.display = 'none';
        }
        
        function showBenchmarkDetails(data) {
            // Implementation for benchmark details modal
            const modal = document.getElementById('detailModal');
            const modalTitle = document.getElementById('modalTitle');
            const modalBody = document.getElementById('modalBody');
            
            modalTitle.textContent = data.benchmark;
            
            const statusClass = `status-${data.status}`;
            
            // Handle insufficient data case for significance display
            let significanceClass, significanceText;
            if (data.statistical_significance.insufficient_data) {
                significanceClass = 'significance-no';
                significanceText = '?';
            } else {
                significanceClass = data.statistical_significance.is_significant ? 'significance-yes' : 'significance-no';
                significanceText = data.statistical_significance.is_significant ? 'Yes' : 'No';
            }
            
            modalBody.innerHTML = `
                <div class="comparison-section">
                    <h3>Performance Comparison</h3>
                    <div class="metric-comparison">
                        <div class="metric-box">
                            <div class="metric-value">${data.baseline_score.toFixed(4)}</div>
                            <div class="metric-error">± ${data.baseline_error.toFixed(4)}</div>
                            <div class="metric-label">Baseline (${data.baseline_vm})</div>
                        </div>
                        <div class="metric-arrow">→</div>
                        <div class="metric-box">
                            <div class="metric-value">${data.treatment_score.toFixed(4)}</div>
                            <div class="metric-error">± ${data.treatment_error.toFixed(4)}</div>
                            <div class="metric-label">Treatment (${data.treatment_vm})</div>
                        </div>
                    </div>
                    <div style="text-align: center; margin: 15px 0;">
                        <strong>Unit:</strong> ${data.unit} | 
                        <strong class="${statusClass}">Improvement:</strong> <span class="${statusClass}">${data.improvement_percent.toFixed(2)}%</span> | 
                        <strong class="${statusClass}">Speedup:</strong> <span class="${statusClass}">${data.speedup.toFixed(2)}x</span>
                    </div>
                    <div style="text-align: center;">
                        <strong>Statistical Significance:</strong> 
                        <span class="significance-badge ${significanceClass}">${significanceText}</span>
                        <span style="margin-left: 10px;">(${data.statistical_significance.confidence_level})</span>
                    </div>
                </div>
            `;
            
            modal.style.display = 'block';
        }
        
        function closeModal() {
            document.getElementById('detailModal').style.display = 'none';
        }
        
        function showBarChart() {
            const modal = document.getElementById('chartModal');
            
            // Check if Chart.js is available
            if (typeof Chart !== 'undefined') {
                // Use Chart.js implementation
                showChartJsBarChart();
            } else {
                // Use fallback SVG implementation
                showSvgBarChart();
            }
            
            modal.style.display = 'block';
        }
        
        // --------- PATCHED VERSION: proper plugin registration + EPS guards ---------
        function showChartJsBarChart() {
            const canvas = document.getElementById('benchmarkChart');
            const ctx = canvas.getContext('2d');
            
            // Clear any existing chart
            if (window.benchmarkChartInstance) {
                window.benchmarkChartInstance.destroy();
            }
            
            // Prepare data for the chart
            const labels = filteredData.map(d => d.display_name || d.benchmark);
            const speedups = filteredData.map(d => d.speedup);
            const colors = filteredData.map(d => {
                if (d.status === 'improved') return '#0066cc';  // Blue for improved (colorblind friendly)
                if (d.status === 'regressed') return '#ff6600'; // Orange for regressed (colorblind friendly)
                return '#6c757d';
            });
            
            // Prepare confidence interval data for error bars with EPS to avoid /0
            const EPS = 1e-12;
            const errorBars = filteredData.map((d) => {
                const baselineConf = d.baseline_details.score_confidence || [];
                const treatmentConf = d.treatment_details.score_confidence || [];
                
                if (baselineConf.length === 2 && treatmentConf.length === 2) {
                    const bLo = Math.max(baselineConf[0], EPS);
                    const bHi = Math.max(baselineConf[1], EPS);
                    const tLo = Math.max(treatmentConf[0], EPS);
                    const tHi = Math.max(treatmentConf[1], EPS);
                    
                    let minSpeedup, maxSpeedup;
                    if (d.higher_is_better) {
                        // For throughput: speedup = treatment / baseline
                        minSpeedup = tLo / bHi; // min treatment / max baseline
                        maxSpeedup = tHi / bLo; // max treatment / min baseline
                    } else {
                        // For latency: speedup = baseline / treatment
                        minSpeedup = bLo / tHi; // min baseline / max treatment
                        maxSpeedup = bHi / tLo; // max baseline / min treatment
                    }
                    
                    return {
                        minus: Math.max(0, d.speedup - minSpeedup),
                        plus:  Math.max(0, maxSpeedup - d.speedup)
                    };
                }
                
                // Fallback to using score errors if confidence intervals not available
                const be = d.baseline_error;
                const te = d.treatment_error;
                
                if (be > 0 && te > 0 && d.baseline_score > 0 && d.treatment_score > 0) {
                    // Approximate error propagation for speedup calculation
                    const relativeError = Math.sqrt(
                        Math.pow(te / d.treatment_score, 2) + 
                        Math.pow(be / d.baseline_score, 2)
                    );
                    const speedupError = d.speedup * relativeError;
                    
                    return { minus: speedupError, plus: speedupError };
                }
                
                return { minus: 0, plus: 0 };
            });
            
            // Define custom plugin to draw error bars (register at top-level, not options.plugins)
            const errorBarsPlugin = {
                id: 'errorBars',
                afterDatasetsDraw(chart) {
                    const ctx = chart.ctx;
                    const meta = chart.getDatasetMeta(0);
                    if (!meta || !meta.data) return;
                    
                    const yScale = chart.scales.y;
                    ctx.save();
                    ctx.strokeStyle = '#000';
                    ctx.lineWidth = 1.5;
                    ctx.fillStyle = '#000';
                    
                    meta.data.forEach((bar, index) => {
                        const eb = errorBars[index];
                        if (!eb || (eb.minus <= 0 && eb.plus <= 0)) return;
                        
                        const x = bar.x;
                        const v = speedups[index];
                        const yMin = yScale.getPixelForValue(Math.max(0, v - eb.minus));
                        const yMax = yScale.getPixelForValue(v + eb.plus);
                        const yCtr = yScale.getPixelForValue(v);
                        
                        // vertical line
                        ctx.beginPath();
                        ctx.moveTo(x, yMin);
                        ctx.lineTo(x, yMax);
                        ctx.stroke();
                        
                        // caps
                        ctx.beginPath();
                        ctx.moveTo(x - 8, yMin); ctx.lineTo(x + 8, yMin);
                        ctx.moveTo(x - 8, yMax); ctx.lineTo(x + 8, yMax);
                        ctx.stroke();
                        
                        // center point
                        ctx.beginPath();
                        ctx.arc(x, yCtr, 2, 0, Math.PI * 2);
                        ctx.fill();
                    });
                    
                    ctx.restore();
                }
            };
            
            // Create the chart with plugin properly registered
            window.benchmarkChartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Speedup Factor',
                        data: speedups,
                        backgroundColor: colors,
                        borderColor: colors,
                        borderWidth: 1
                    }]
                },
                plugins: [errorBarsPlugin],
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Speedup Factor (x)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Benchmarks'
                            },
                            ticks: {
                                maxRotation: 45,
                                minRotation: 45
                            }
                        }
                    },
                    plugins: {
                        title: {
                            display: true,
                            text: 'Benchmark Performance Speedup (with Confidence Intervals)'
                        },
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                afterLabel: function(context) {
                                    const index = context.dataIndex;
                                    const d = filteredData[index];
                                    const eb = errorBars[index];
                                    
                                    const lines = [
                                        `Mode: ${d.mode}`,
                                        `Unit: ${d.unit}`,
                                        `Improvement: ${d.improvement_percent.toFixed(2)}%`,
                                        `Status: ${d.status}`
                                    ];
                                    
                                    if (eb.minus > 0 || eb.plus > 0) {
                                        lines.push(`Confidence: ${(d.speedup - eb.minus).toFixed(2)}x – ${(d.speedup + eb.plus).toFixed(2)}x`);
                                    }
                                    
                                    return lines;
                                }
                            }
                        }
                    }
                }
            });
        }
        
        function showSvgBarChart() {
            const chartContainer = document.querySelector('#chartModal .modal-content > div');
            
            // Clear existing content
            chartContainer.innerHTML = '<h3 style="text-align: center; margin-bottom: 20px;">Benchmark Performance Speedup (with Confidence Intervals)</h3>';
            
            // Calculate chart dimensions
            const width = 800;
            const height = 400;
            const margin = { top: 20, right: 30, bottom: 80, left: 60 };
            const chartWidth = width - margin.left - margin.right;
            const chartHeight = height - margin.top - margin.bottom;
            
            // Prepare data
            const data = filteredData.map((d, index) => {
                const baselineConf = d.baseline_details.score_confidence || [];
                const treatmentConf = d.treatment_details.score_confidence || [];
                
                let errorBar = { minus: 0, plus: 0 };
                
                if (baselineConf.length === 2 && treatmentConf.length === 2) {
                    const EPS = 1e-12;
                    const bLo = Math.max(baselineConf[0], EPS);
                    const bHi = Math.max(baselineConf[1], EPS);
                    const tLo = Math.max(treatmentConf[0], EPS);
                    const tHi = Math.max(treatmentConf[1], EPS);
                    
                    let minSpeedup, maxSpeedup;
                    if (d.higher_is_better) {
                        minSpeedup = tLo / bHi;
                        maxSpeedup = tHi / bLo;
                    } else {
                        minSpeedup = bLo / tHi;
                        maxSpeedup = bHi / tLo;
                    }
                    
                    errorBar = {
                        minus: Math.max(0, d.speedup - minSpeedup),
                        plus: Math.max(0, maxSpeedup - d.speedup)
                    };
                }
                
                return {
                    label: d.display_name || d.benchmark,
                    speedup: d.speedup,
                    color: d.status === 'improved' ? '#0066cc' : d.status === 'regressed' ? '#ff6600' : '#6c757d',
                    errorBar: errorBar,
                    data: d
                };
            });
            
            // Calculate scales
            const maxSpeedup = Math.max(...data.map(d => d.speedup + d.errorBar.plus));
            const minSpeedup = Math.min(0, ...data.map(d => d.speedup - d.errorBar.minus));
            const yScale = (height - margin.top - margin.bottom) / (maxSpeedup - minSpeedup);
            const barWidth = (width - margin.left - margin.right) / data.length * 0.8;
            const barSpacing = (width - margin.left - margin.right) / data.length;
            
            // Create SVG
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('width', width);
            svg.setAttribute('height', height);
            svg.style.border = '1px solid #ddd';
            svg.style.backgroundColor = 'white';
            
            // Draw Y-axis
            const yAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            yAxis.setAttribute('x1', margin.left);
            yAxis.setAttribute('y1', margin.top);
            yAxis.setAttribute('x2', margin.left);
            yAxis.setAttribute('y2', height - margin.bottom);
            yAxis.setAttribute('stroke', '#333');
            yAxis.setAttribute('stroke-width', '1');
            svg.appendChild(yAxis);
            
            // Draw X-axis
            const xAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            xAxis.setAttribute('x1', margin.left);
            xAxis.setAttribute('y1', height - margin.bottom);
            xAxis.setAttribute('x2', width - margin.right);
            xAxis.setAttribute('y2', height - margin.bottom);
            xAxis.setAttribute('stroke', '#333');
            xAxis.setAttribute('stroke-width', '1');
            svg.appendChild(xAxis);
            
            // Draw Y-axis labels and grid lines
            const yTicks = 5;
            for (let i = 0; i <= yTicks; i++) {
                const value = minSpeedup + (maxSpeedup - minSpeedup) * i / yTicks;
                const y = height - margin.bottom - (value - minSpeedup) * yScale;
                
                // Grid line
                const gridLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                gridLine.setAttribute('x1', margin.left);
                gridLine.setAttribute('y1', y);
                gridLine.setAttribute('x2', width - margin.right);
                gridLine.setAttribute('y2', y);
                gridLine.setAttribute('stroke', '#eee');
                gridLine.setAttribute('stroke-width', '1');
                svg.appendChild(gridLine);
                
                // Label
                const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                label.setAttribute('x', margin.left - 10);
                label.setAttribute('y', y + 4);
                label.setAttribute('text-anchor', 'end');
                label.setAttribute('font-size', '12');
                label.setAttribute('fill', '#666');
                label.textContent = value.toFixed(1) + 'x';
                svg.appendChild(label);
            }
            
            // Draw bars and error bars
            data.forEach((d, index) => {
                const chartHeight = height - margin.top - margin.bottom;
                const x = margin.left + index * barSpacing + (barSpacing - barWidth) / 2;
                const barHeight = (d.speedup - minSpeedup) * yScale;
                const y = height - margin.bottom - barHeight;
                
                // Draw bar
                const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                bar.setAttribute('x', x);
                bar.setAttribute('y', y);
                bar.setAttribute('width', barWidth);
                bar.setAttribute('height', barHeight);
                bar.setAttribute('fill', d.color);
                bar.setAttribute('stroke', d.color);
                bar.setAttribute('stroke-width', '1');
                svg.appendChild(bar);
                
                // Draw error bars if available
                if (d.errorBar.minus > 0 || d.errorBar.plus > 0) {
                    const centerX = x + barWidth / 2;
                    const minY = height - margin.bottom - (d.speedup - d.errorBar.minus - minSpeedup) * yScale;
                    const maxY = height - margin.bottom - (d.speedup + d.errorBar.plus - minSpeedup) * yScale;
                    const centerY = height - margin.bottom - (d.speedup - minSpeedup) * yScale;
                    
                    // Vertical line
                    const errorLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    errorLine.setAttribute('x1', centerX);
                    errorLine.setAttribute('y1', minY);
                    errorLine.setAttribute('x2', centerX);
                    errorLine.setAttribute('y2', maxY);
                    errorLine.setAttribute('stroke', '#000');
                    errorLine.setAttribute('stroke-width', '2');
                    svg.appendChild(errorLine);
                    
                    // Top cap
                    const topCap = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    topCap.setAttribute('x1', centerX - 8);
                    topCap.setAttribute('y1', maxY);
                    topCap.setAttribute('x2', centerX + 8);
                    topCap.setAttribute('y2', maxY);
                    topCap.setAttribute('stroke', '#000');
                    topCap.setAttribute('stroke-width', '2');
                    svg.appendChild(topCap);
                    
                    // Bottom cap
                    const bottomCap = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    bottomCap.setAttribute('x1', centerX - 8);
                    bottomCap.setAttribute('y1', minY);
                    bottomCap.setAttribute('x2', centerX + 8);
                    bottomCap.setAttribute('y2', minY);
                    bottomCap.setAttribute('stroke', '#000');
                    bottomCap.setAttribute('stroke-width', '2');
                    svg.appendChild(bottomCap);
                    
                    // Center point
                    const centerPoint = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                    centerPoint.setAttribute('cx', centerX);
                    centerPoint.setAttribute('cy', centerY);
                    centerPoint.setAttribute('r', '3');
                    centerPoint.setAttribute('fill', '#000');
                    svg.appendChild(centerPoint);
                }
                
                // X-axis label
                const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                label.setAttribute('x', x + barWidth / 2);
                label.setAttribute('y', height - margin.bottom + 15);
                label.setAttribute('text-anchor', 'middle');
                label.setAttribute('font-size', '10');
                label.setAttribute('fill', '#666');
                label.textContent = d.label.length > 15 ? d.label.substring(0, 12) + '...' : d.label;
                svg.appendChild(label);
            });
            
            // Add Y-axis title
            const yTitle = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            yTitle.setAttribute('x', 20);
            yTitle.setAttribute('y', height / 2);
            yTitle.setAttribute('text-anchor', 'middle');
            yTitle.setAttribute('font-size', '12');
            yTitle.setAttribute('fill', '#333');
            yTitle.setAttribute('transform', `rotate(-90, 20, ${height / 2})`);
            yTitle.textContent = 'Speedup Factor (x)';
            svg.appendChild(yTitle);
            
            chartContainer.appendChild(svg);
            
            // Add legend
            const legend = document.createElement('div');
            legend.style.textAlign = 'center';
            legend.style.marginTop = '10px';
            legend.style.fontSize = '12px';
            legend.innerHTML = `
                <span style="color: #0066cc;">■ Improved</span> &nbsp;&nbsp;
                <span style="color: #ff6600;">■ Regressed</span> &nbsp;&nbsp;
                <span style="color: #6c757d;">■ Unchanged</span> &nbsp;&nbsp;
                <span style="color: #000;">| Error bars show confidence intervals</span>
            `;
            chartContainer.appendChild(legend);
        }
        
        function closeChartModal() {
            document.getElementById('chartModal').style.display = 'none';
        }
        
        // Close modal when clicking outside of it
        window.onclick = function(event) {
            const detailModal = document.getElementById('detailModal');
            const chartModal = document.getElementById('chartModal');
            const experimentModal = document.getElementById('experimentModal');
            if (event.target === detailModal) {
                closeModal();
            }
            if (event.target === chartModal) {
                closeChartModal();
            }
            if (event.target === experimentModal) {
                closeExperimentModal();
            }
        }
        
        // Close modal with Escape key
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                closeModal();
                closeChartModal();
                closeExperimentModal();
            }
        });
        
        // Initialize
        updateFilteredStats();
        updateTable();
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
    
    # Parse experiment details if available
    experiment_details = parse_details_file(Path(basepath))
    
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
    generate_html_report(comparison_data, experiment_details, output_file=basepath + "/benchmark_comparison_report.html")
    
    print("Done! Open 'benchmark_comparison_report.html' in your browser to view the report.")


if __name__ == "__main__":
    if len(sys.argv) <= 1 :
        print("Usage: " + sys.argv[0] + " <basepath-for-results-dir>")
    else: 
        main(sys.argv[1])
