"""
Experiment 1: Cost-Normalized Success — haiku×3 retries vs sonnet×1 shot

OPEN QUESTION: Haiku is 3× cheaper than Sonnet. If you spend the same budget,
is 3 Haiku attempts better than 1 Sonnet attempt?

Published benchmarks compare models 1:1 (same number of attempts). Nobody has
published cost-normalized pass rates. This is critical for production routing.

Design:
- haiku_retry: max_turns=8, num_samples=3 → best-of-3 at haiku price
- sonnet_single: max_turns=8, num_samples=1 → single sonnet attempt
- Cost per task: haiku_retry ≈ 3× $0.01 = $0.03, sonnet_single ≈ $0.03

Tasks: 8 multi-step tool-use problems of varying difficulty.
Metric: pass@1 for sonnet, pass@3 for haiku (did ANY of 3 attempts succeed?)
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # Task files for tool-use problems
    "data.csv": "name,age,salary,department\nAlice,30,75000,Engineering\nBob,25,55000,Marketing\nCarol,35,92000,Engineering\nDave,28,61000,Marketing\nEve,32,88000,Engineering\nFrank,45,105000,Management\nGrace,29,58000,Marketing\nHank,38,95000,Engineering\nIvy,33,72000,Sales\nJack,41,99000,Management\n",

    "config.json": '{"app_name": "TestApp", "version": "2.1.0", "features": {"auth": true, "logging": false, "cache_ttl": 300}, "database": {"host": "localhost", "port": 5432, "name": "testdb"}, "rate_limits": {"api": 100, "web": 500}}',

    "buggy_sort.py": '''\
def merge_sort(arr):
    """Merge sort with a subtle bug."""
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)

def merge(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] < right[j]:  # Bug: should be <= for stability
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result

# Test: sort list of (value, index) tuples - stability matters
data = [(3, "a"), (1, "b"), (3, "c"), (2, "d"), (1, "e")]
sorted_data = merge_sort(data)
# Stable sort should keep original order for equal values:
# (1,"b"), (1,"e"), (2,"d"), (3,"a"), (3,"c")
expected = [(1, "b"), (1, "e"), (2, "d"), (3, "a"), (3, "c")]
print(f"Result:   {sorted_data}")
print(f"Expected: {expected}")
print(f"Stable: {sorted_data == expected}")
''',

    "analyze.py": '''\
"""Template for data analysis task."""
# Agent should fill this in
''',
}

experiment = Experiment(
    name="cost_normalized_retry",
    description=(
        "Cost-normalized: haiku×3 retries (pass@3) vs sonnet×1 (pass@1). "
        "Same budget, different strategy. Which wins?"
    ),
    diff=DiffSpec(
        field="model",
        description="haiku (3 attempts, pass@3) vs sonnet (1 attempt, pass@1)",
    ),
    agent_a=AgentConfig(
        name="haiku_retry",
        model="claude-haiku-4-5",
        system_prompt=None,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    agent_b=AgentConfig(
        name="sonnet_single",
        model="claude-sonnet-4-6",
        system_prompt=None,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    tasks=[
        # ── Simple tool use (both should pass) ───────────────────────────
        TaskItem(
            prompt="Read data.csv and compute the average salary per department. Print results.",
            expected="Engineering",
            check_fn='"Engineering" in output and "Marketing" in output',
            difficulty="easy",
            tags=["data", "csv"],
        ),
        TaskItem(
            prompt="Read config.json. Change cache_ttl to 600 and logging to true. Write the updated file. Print the final JSON.",
            expected="600",
            check_fn='"600" in output and "true" in output.lower()',
            difficulty="easy",
            tags=["json", "edit"],
        ),

        # ── Medium tool use ──────────────────────────────────────────────
        TaskItem(
            prompt=(
                "Read data.csv. Write a Python script that:\n"
                "1. Finds the department with highest average salary\n"
                "2. Finds employees earning above the company median\n"
                "3. Calculates the salary gap between highest and lowest paid\n"
                "Run the script and show results."
            ),
            expected="Management",
            check_fn='"Management" in output',
            difficulty="medium",
            tags=["data-analysis", "scripting"],
        ),
        TaskItem(
            prompt=(
                "Run buggy_sort.py. It has a stability bug in merge sort. "
                "Fix the bug so the sort is stable, then run it again to verify "
                "the output matches expected."
            ),
            expected="Stable: True",
            check_fn='"Stable: True" in output or "stable: true" in output.lower()',
            difficulty="medium",
            tags=["debugging", "algorithm"],
        ),

        # ── Hard multi-step ──────────────────────────────────────────────
        TaskItem(
            prompt=(
                "Read data.csv. Write a Python script that generates a text-based "
                "report with:\n"
                "1. Summary statistics (count, mean, min, max salary per dept)\n"
                "2. A ranked list of employees by salary (highest first)\n"
                "3. Department headcount percentages\n"
                "Save the report to report.txt and print it."
            ),
            expected="Frank",
            check_fn='"Frank" in output and "105000" in output',
            difficulty="hard",
            tags=["report-generation", "multi-step"],
        ),
        TaskItem(
            prompt=(
                "Write a Python script that reads config.json and data.csv, "
                "then generates a SQL schema and INSERT statements for the data. "
                "The table name should come from config.json's database.name. "
                "Save to schema.sql and print it."
            ),
            expected="CREATE TABLE",
            check_fn='"CREATE TABLE" in output and "INSERT" in output',
            difficulty="hard",
            tags=["code-generation", "sql"],
        ),

        # ── Very hard (likely to fail on first attempt) ──────────────────
        TaskItem(
            prompt=(
                "Write a Python script that reads data.csv and performs a "
                "bootstrap statistical analysis:\n"
                "1. Resample the salary data 1000 times (with replacement)\n"
                "2. Compute the 95% confidence interval for mean salary\n"
                "3. Test if Engineering salaries are significantly different "
                "from Marketing salaries (permutation test, p-value)\n"
                "Use random seed 42 for reproducibility. Print all results."
            ),
            expected="confidence interval",
            check_fn='"confidence" in output.lower() and "p" in output.lower()',
            difficulty="very_hard",
            tags=["statistics", "bootstrap"],
        ),
        TaskItem(
            prompt=(
                "Read data.csv. Write a Python script that:\n"
                "1. Builds a simple linear regression model predicting salary from age\n"
                "2. Calculates R², slope, intercept, and p-value\n"
                "3. Predicts salary for age=50\n"
                "4. Identifies any outliers (residual > 2 std dev)\n"
                "Do NOT use sklearn — implement from scratch using only math/statistics.\n"
                "Print all results."
            ),
            expected="R²",
            check_fn=('"r" in output.lower() and ("slope" in output.lower() or "intercept" in output.lower())'),
            difficulty="very_hard",
            tags=["regression", "from-scratch"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=3,  # haiku gets 3 shots, sonnet gets 3 shots. Compare pass@3 vs pass@1.
    tags=["cost-normalized", "retry-strategy", "production-routing"],
)
