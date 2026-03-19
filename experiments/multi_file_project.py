"""
Experiment: Multi-File Project Build — Expression Calculator

Agent must build a complete expression calculator from scratch:
  - Tokenizer (lexer)
  - Parser (recursive descent, handles precedence)
  - Evaluator
  - Variable support (let x = 5, then use x)
  - Error handling (division by zero, undefined variables, syntax errors)

This requires:
  - Multiple files working together
  - Correct operator precedence (*, / before +, -)
  - Parentheses handling
  - Proper error reporting
  - ~30+ tool calls to implement and debug

Tests haiku vs sonnet at max_turns=30.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    "test_calc.py": '''\
"""Comprehensive test suite for expression calculator."""
import sys
sys.path.insert(0, ".")

from calc import Calculator

def test_basic_arithmetic():
    c = Calculator()
    assert c.eval("2 + 3") == 5
    assert c.eval("10 - 4") == 6
    assert c.eval("3 * 7") == 21
    assert c.eval("20 / 4") == 5.0
    print("  basic_arithmetic: OK")

def test_precedence():
    c = Calculator()
    assert c.eval("2 + 3 * 4") == 14, f"Got {c.eval('2 + 3 * 4')}"
    assert c.eval("10 - 2 * 3") == 4
    assert c.eval("6 / 2 + 1") == 4.0
    assert c.eval("2 * 3 + 4 * 5") == 26
    print("  precedence: OK")

def test_parentheses():
    c = Calculator()
    assert c.eval("(2 + 3) * 4") == 20
    assert c.eval("((1 + 2) * (3 + 4))") == 21
    assert c.eval("(10 - (3 + 2)) * 2") == 10
    print("  parentheses: OK")

def test_negative_numbers():
    c = Calculator()
    assert c.eval("-5 + 3") == -2
    assert c.eval("3 + -2") == 1 or c.eval("3 + (-2)") == 1
    assert c.eval("-3 * -4") == 12 or c.eval("(-3) * (-4)") == 12
    print("  negative_numbers: OK")

def test_decimals():
    c = Calculator()
    assert abs(c.eval("3.14 * 2") - 6.28) < 0.001
    assert abs(c.eval("1.5 + 2.5") - 4.0) < 0.001
    print("  decimals: OK")

def test_variables():
    c = Calculator()
    c.eval("x = 10")
    assert c.eval("x + 5") == 15
    assert c.eval("x * 2") == 20
    c.eval("y = x + 3")
    assert c.eval("y") == 13
    c.eval("x = 20")  # reassignment
    assert c.eval("x") == 20
    print("  variables: OK")

def test_division_by_zero():
    c = Calculator()
    try:
        c.eval("10 / 0")
        assert False, "Should raise error for division by zero"
    except (ZeroDivisionError, ValueError, Exception):
        pass
    print("  division_by_zero: OK")

def test_undefined_variable():
    c = Calculator()
    try:
        c.eval("unknown_var + 1")
        assert False, "Should raise error for undefined variable"
    except (NameError, ValueError, KeyError, Exception):
        pass
    print("  undefined_variable: OK")

def test_syntax_error():
    c = Calculator()
    for bad_expr in ["2 +", "* 3", "2 + + 3", "(2 + 3", "2 + 3)"]:
        try:
            c.eval(bad_expr)
            # Some might be handled differently
        except Exception:
            pass
    print("  syntax_error: OK")

def test_whitespace():
    c = Calculator()
    assert c.eval("  2+3  ") == 5
    assert c.eval("2  *  3") == 6
    print("  whitespace: OK")

def test_complex_expressions():
    c = Calculator()
    assert c.eval("(2 + 3) * (4 - 1) + 6 / 2") == 18.0
    c.eval("a = 5")
    c.eval("b = 3")
    assert c.eval("a * b + (a - b)") == 17
    print("  complex_expressions: OK")

if __name__ == "__main__":
    passed = 0
    failed = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                func()
                passed += 1
            except Exception as e:
                print(f"  {name}: FAIL — {e}")
                failed += 1
    total = passed + failed
    print(f"\\nResults: {passed}/{total} passed")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"{failed} FAILED")
''',
}

experiment = Experiment(
    name="multi_file_project",
    description=(
        "Build a complete expression calculator (tokenizer + parser + evaluator + variables). "
        "haiku vs sonnet at max_turns=30."
    ),
    diff=DiffSpec(
        field="model",
        description="haiku vs sonnet on complex multi-file implementation",
    ),
    agent_a=AgentConfig(
        name="haiku",
        model="claude-haiku-4-5",
        system_prompt=(
            "Build a Python expression calculator in calc.py. Read test_calc.py first "
            "to understand all requirements. Implement a Calculator class with an eval(expr) "
            "method. Run tests after implementation. Fix any failures."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=30,
    ),
    agent_b=AgentConfig(
        name="sonnet",
        model="claude-sonnet-4-6",
        system_prompt=(
            "Build a Python expression calculator in calc.py. Read test_calc.py first "
            "to understand all requirements. Implement a Calculator class with an eval(expr) "
            "method. Run tests after implementation. Fix any failures."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=30,
    ),
    tasks=[
        TaskItem(
            prompt=(
                "Build a complete expression calculator in calc.py with:\n"
                "- Calculator class with eval(expression_string) method\n"
                "- Arithmetic: +, -, *, / with correct precedence\n"
                "- Parentheses support\n"
                "- Negative numbers\n"
                "- Decimal numbers\n"
                "- Variable assignment (x = 5) and usage\n"
                "- Error handling: division by zero, undefined variables, syntax errors\n\n"
                "Read test_calc.py for detailed requirements. Run it to verify."
            ),
            expected="ALL TESTS PASSED",
            check_fn=(
                '"ALL TESTS PASSED" in output or '
                '("passed" in output.lower() and "0 FAILED" not in output and '
                '"fail" not in output.lower().split("passed")[0])'
            ),
            difficulty="very_hard",
            tags=["parser", "evaluator", "multi-component"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=2,  # 2 samples for variance
    tags=["multi-file", "complex-build", "long-horizon"],
)
