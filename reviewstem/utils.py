import csv
from datetime import datetime
from pathlib import Path


def log_review_scores(case_name: str, initial_score: float, final_score: float, passes: int):
    """Log review score movement across one run."""
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    log_file = outputs_dir / "improvement_history.csv"
    file_exists = log_file.is_file()
    delta = final_score - initial_score
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with log_file.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                [
                    "Timestamp",
                    "Case Name",
                    "Passes",
                    "Initial Score",
                    "Final Score",
                    "Score Delta",
                ]
            )
        writer.writerow(
            [
                timestamp,
                case_name,
                passes,
                f"{initial_score:.2f}",
                f"{final_score:.2f}",
                f"{delta:+.2f}",
            ]
        )
