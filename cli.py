import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from app.models import RunRequest
from app.service import run_agent


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Extract tasks from fixture or Discord messages")
    parser.add_argument("--source", choices=["fixture", "discord"], default="fixture")
    parser.add_argument("--extractor", choices=["rules", "anthropic"], default="rules")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--channel-id")
    parser.add_argument("--output", type=Path, default=Path("output/report.json"))
    args = parser.parse_args()

    report = run_agent(
        RunRequest(
            source=args.source,
            extractor=args.extractor,
            limit=args.limit,
            channel_id=args.channel_id,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
