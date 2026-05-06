import csv
import os

CSV_FILE = "call_logs.csv"


def save_call_session(
    session_id,
    start_time,
    end_time,
    conversation,
    lead_score,
    duration_seconds,
    summary
):
    file_exists = os.path.isfile(CSV_FILE)

    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # 🔹 Header (first time only)
        if not file_exists:
            writer.writerow([
                "session_id",
                "start_time",
                "end_time",
                "duration_seconds",
                "lead_score",
                "summary",
                "conversation"
            ])

        writer.writerow([
            session_id,
            start_time,
            end_time,
            duration_seconds,
            lead_score,
            summary,
            conversation
        ])
