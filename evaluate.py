"""
Root level wrapper for tests/evaluate.py
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.evaluate import run_evaluation

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate Text-to-SQL benchmark accuracy sequentially.")
    parser.add_argument("--limit", type=int, default=10, help="Number of sequential test cases to run (default: 10). Set 0 for all.")
    parser.add_argument("--delay", type=float, default=8.0, help="Delay in seconds between LLM calls to respect API limits.")
    args = parser.parse_args()

    run_evaluation(limit=args.limit, delay=args.delay)
