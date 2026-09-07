"""
Text-to-SQL Sequential Evaluation Benchmark Script
Optimized for rate limits: 1 LLM call per question, 60s backoff on 429 quota.
"""

import os
import json
import time
import argparse
import pandas as pd
from app.llm import generate_sql
from app.database import execute_query
from app.sql_guard import is_safe_query

CSV_PATH = os.path.join("TextToSQL_Datasets", "text_to_sql_test_cases.csv")

def run_evaluation(limit=None, delay=8.0):
    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found.")
        return

    df = pd.read_csv(CSV_PATH)
    total_test_cases = len(df)
    if limit and limit > 0:
        df = df.iloc[:limit]
        print(f"Running sequential evaluation on top {limit} of {total_test_cases} test cases...")
    else:
        print(f"Running full sequential evaluation on all {total_test_cases} test cases...")

    passed_sql_guard = 0
    executed_successfully = 0
    exact_data_matches = 0
    results_list = []
    
    # Maintain conversation history across sequential test cases
    chat_history = []

    start_time = time.time()

    for idx, row in df.iterrows():
        question = str(row["Question"])
        expected_sql = str(row["SQL Query"])
        expected_result_str = str(row["Expected Result"])

        print(f"\n[{idx + 1}/{len(df)}] Q: {question}")

        # Format history string for LLM context (Only includes previous questions & generated SQLs)
        history_text = "\n".join(
            f"Q: {h['question']}\nSQL: {h['sql']}" for h in chat_history[-3:]
        )

        generated_sql = ""
        error_msg = None
        executed_data = None
        is_safe = False
        is_match = False

        # Attempt SQL Generation with 60s retry backoff for API rate limits
        for attempt in range(1, 4):
            try:
                generated_sql = generate_sql(question, history=history_text)
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait_time = 60
                    print(f"  [Rate limited 429] Quota exceeded. Waiting {wait_time}s for quota reset (attempt {attempt}/3)...")
                    time.sleep(wait_time)
                else:
                    error_msg = err_str
                    break

        if generated_sql:
            is_safe = is_safe_query(generated_sql)
            if is_safe:
                passed_sql_guard += 1
                try:
                    executed_data = execute_query(generated_sql)
                    executed_successfully += 1

                    # Compare results against expected dataset json
                    try:
                        expected_data = json.loads(expected_result_str)
                        if isinstance(expected_data, dict) and len(executed_data) >= 1:
                            key = list(expected_data.keys())[0]
                            val = expected_data[key]
                            first_val = list(executed_data[0].values())[0]
                            if first_val == val or executed_data[0] == expected_data:
                                is_match = True
                        elif isinstance(expected_data, list):
                            if len(executed_data) == len(expected_data):
                                is_match = True
                    except Exception:
                        pass

                    if is_match:
                        exact_data_matches += 1

                except Exception as e:
                    error_msg = f"SQL Execution error: {e}"
            else:
                error_msg = "Blocked by sql_guard security check"

        status_str = "MATCH" if is_match else ("EXEC_OK" if executed_data is not None else "FAIL")
        print(f"  Generated SQL: {generated_sql}")
        print(f"  Status: {status_str} | Safe: {is_safe}")
        if error_msg:
            print(f"  Error: {error_msg}")

        # Update chat history for subsequent follow-up questions
        if is_safe and executed_data is not None:
            chat_history.append({
                "question": question,
                "sql": generated_sql
            })

        results_list.append({
            "id": idx + 1,
            "question": question,
            "expected_sql": expected_sql,
            "generated_sql": generated_sql,
            "is_safe": is_safe,
            "executed": executed_data is not None,
            "is_match": is_match,
            "error": error_msg
        })

        time.sleep(delay)

    elapsed_time = round(time.time() - start_time, 2)
    eval_count = len(df)

    summary = {
        "total_test_cases": eval_count,
        "passed_sql_guard": passed_sql_guard,
        "sql_guard_rate": f"{(passed_sql_guard / eval_count) * 100:.1f}%",
        "executed_successfully": executed_successfully,
        "execution_success_rate": f"{(executed_successfully / eval_count) * 100:.1f}%",
        "data_matches": exact_data_matches,
        "match_rate": f"{(exact_data_matches / eval_count) * 100:.1f}%",
        "elapsed_seconds": elapsed_time
    }

    print("\n" + "="*60)
    print("SEQUENTIAL EVALUATION BENCHMARK SUMMARY")
    print("="*60)
    print(f"Total Evaluated        : {summary['total_test_cases']}")
    print(f"SQL Guard Passed       : {summary['passed_sql_guard']} ({summary['sql_guard_rate']})")
    print(f"SQL Executed Cleanly   : {summary['executed_successfully']} ({summary['execution_success_rate']})")
    print(f"Data Match Accuracy    : {summary['data_matches']} ({summary['match_rate']})")
    print(f"Time Taken             : {elapsed_time}s")
    print("="*60)

    with open("evaluation_report.json", "w") as f:
        json.dump({"summary": summary, "results": results_list}, f, indent=2)
    print("Detailed report saved to evaluation_report.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Text-to-SQL benchmark accuracy sequentially.")
    parser.add_argument("--limit", type=int, default=10, help="Number of sequential test cases to run (default: 10). Set 0 for all.")
    parser.add_argument("--delay", type=float, default=8.0, help="Delay in seconds between LLM calls to respect API limits.")
    args = parser.parse_args()

    run_evaluation(limit=args.limit, delay=args.delay)
