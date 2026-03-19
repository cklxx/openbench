"""
Experiment: Verified Math Tournament — haiku vs haiku+Bash vs sonnet

ALL expected answers verified by Python computation before experiment.
Mix of difficulty levels designed to actually discriminate between agents.

Previous findings:
- T1-T3 from novel_math had WRONG expected answers (now fixed)
- Only modular arithmetic (T4) differentiated agents
- Need tasks spanning a wider difficulty range
"""
from openbench.types import AgentConfig, TaskItem, TournamentConfig

tournament = TournamentConfig(
    name="verified_math_tournament",
    description=(
        "3-way tournament with ALL answers verified by Python. "
        "haiku vs haiku+Bash vs sonnet on 10 tasks spanning easy→very hard."
    ),
    configs=[
        AgentConfig(
            name="haiku",
            model="claude-haiku-4-5",
            system_prompt=None,
            allowed_tools=[],
            max_turns=2,
        ),
        AgentConfig(
            name="haiku_code",
            model="claude-haiku-4-5",
            system_prompt=(
                "You have Bash. For every math problem, write a Python script "
                "to compute the answer, run it, then report the result. "
                "Always verify with code."
            ),
            allowed_tools=["Bash"],
            max_turns=6,
        ),
        AgentConfig(
            name="sonnet",
            model="claude-sonnet-4-6",
            system_prompt=None,
            allowed_tools=[],
            max_turns=2,
        ),
    ],
    tasks=[
        # ── EASY (warm-up, all should pass) ──────────────────────────────
        TaskItem(
            prompt=(
                "There are 35 animals (chickens and rabbits) with 94 feet total. "
                "Chickens have 2 feet, rabbits have 4. "
                "How many chickens and how many rabbits? Give both numbers."
            ),
            expected="23 chickens and 12 rabbits",
            # Verified: c+r=35, 2c+4r=94 => r=12, c=23
            check_fn='"23" in output and "12" in output',
            difficulty="easy",
        ),

        # ── MEDIUM (multi-step, verified) ────────────────────────────────
        TaskItem(
            prompt=(
                "A tank fills at 3.7 liters per minute. After 23 minutes, "
                "a drain opens removing 1.2 liters per minute (filling continues). "
                "How many liters after 40 minutes total? One decimal place."
            ),
            expected="127.6",
            # Verified: 3.7*23 + 2.5*17 = 85.1 + 42.5 = 127.6
            check_fn='"127.6" in output',
            difficulty="medium",
        ),
        TaskItem(
            prompt=(
                "You invest $2,500 at 6% annual interest compounded quarterly. "
                "After exactly 3 years, what is the total? Round to nearest cent."
            ),
            expected="$2,989.05",
            # Verified: 2500*(1+0.015)^12 = 2989.0463... ≈ 2989.05
            check_fn='"2989.05" in output or "2,989.05" in output',
            difficulty="medium",
        ),
        TaskItem(
            prompt=(
                "5-letter arrangements of {A,B,C,D,E} (no repeats) where A is "
                "neither first nor last. How many such arrangements? Single number."
            ),
            expected="72",
            # Verified: 5!-2*4!+3! = 120-48+6... no. Direct:
            # pos for A: 2nd,3rd,4th (3 choices). Remaining 4 letters in 4 spots: 4!=24.
            # 3*24=72. Confirmed by enumeration.
            check_fn='"72" in output',
            difficulty="medium",
        ),

        # ── HARD (requires careful reasoning) ────────────────────────────
        TaskItem(
            prompt=(
                "A ball drops from 243 cm. Each bounce reaches 2/3 previous height. "
                "Total distance (up+down) from drop until hitting ground after 5th bounce? "
                "Exact answer in cm."
            ),
            expected="1087",
            # Verified: 243 + 2*(162+108+72+48+32) = 243 + 2*422 = 243+844 = 1087
            check_fn='"1087" in output',
            difficulty="hard",
        ),
        TaskItem(
            prompt=(
                "What is the remainder when 7^100 is divided by 13? Single number."
            ),
            expected="9",
            # Verified: pow(7,100,13) = 9
            check_fn=(
                '"9" in output.split()[-3:] or '
                '"= 9" in output or "is 9" in output.lower() or '
                'output.strip().endswith("9")'
            ),
            difficulty="hard",
        ),
        TaskItem(
            prompt=(
                "What is the sum of ALL digits of ALL integers from 1 to 999? "
                "For example, 123 contributes 1+2+3=6. Give the total."
            ),
            expected="13500",
            # Verified by enumeration: 13500
            check_fn='"13500" in output',
            difficulty="hard",
        ),
        TaskItem(
            prompt=(
                "F(n) is the Fibonacci sequence: F(1)=1, F(2)=1, F(n)=F(n-1)+F(n-2). "
                "What are the last two digits of F(50)? Give a number."
            ),
            expected="25",
            # Verified: F(50) mod 100 = 25 (F(50) = 12586269025)
            check_fn='"25" in output',
            difficulty="hard",
        ),

        # ── VERY HARD (discriminator tasks) ──────────────────────────────
        TaskItem(
            prompt=(
                "In a room of 4 people, each person's birthday is equally likely to be "
                "any of 7 days of the week. What is the probability that at least 2 people "
                "share the same birthday-day-of-week? Express as a fraction with denominator 2401."
            ),
            expected="1561/2401",
            # Verified: 1 - 7*6*5*4/7^4 = 1 - 840/2401 = 1561/2401
            check_fn='"1561" in output and "2401" in output',
            difficulty="very_hard",
        ),
        TaskItem(
            prompt=(
                "A 4×4 grid has 16 cells. How many ways can you place 4 non-attacking "
                "rooks on this grid? (Non-attacking means no two rooks share a row or column.) "
                "Give a single number."
            ),
            expected="24",
            # Verified: 4! = 24 (one rook per row, permute columns)
            check_fn='"24" in output',
            difficulty="very_hard",
        ),
    ],
    num_samples=1,
    tags=["verified-math", "model-vs-tool", "tournament", "objective"],
)
