"""Local CLI. Output is JSON; fixture IDs never imply real Meta resources."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from adloom.config import AdLoomError, load_config
from adloom.jobs import JobStore
from adloom.pipeline import approve_job, edit_job, inspect_job, publish_job, resume_job, run_file


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adloom", description="AdLoom offline fixture workflow")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Create six videos using registered mock fixtures")
    run.add_argument("--video", required=True, type=Path)
    run.add_argument("--note")
    run.add_argument("--note-audio", type=Path)
    run.add_argument("--region", required=True)
    run.add_argument("--budget", required=True, type=int)
    run.add_argument("--destination")
    commands.add_parser("list", help="List local jobs, including failed runs")
    for command in ("inspect", "resume", "approve", "publish", "edit"):
        sub = commands.add_parser(command)
        sub.add_argument("job_id")
        if command == "approve":
            sub.add_argument("--actor", required=True)
            sub.add_argument(
                "--digest", help="Digest printed by inspect; stale reviews are refused"
            )
        if command == "edit":
            sub.add_argument("--hook-a")
            sub.add_argument("--hook-b")
            sub.add_argument("--primary-text")
            sub.add_argument("--headline")
    args = parser.parse_args(argv)
    try:
        settings = load_config()
        if args.command == "run":
            result: object = run_file(
                settings,
                args.video,
                args.note,
                args.region,
                args.budget,
                args.note_audio,
                args.destination,
            ).model_dump(mode="json")
        elif args.command == "list":
            store = JobStore(settings.data_dir)
            result = [
                store.load(path.parent.name).model_dump(mode="json")
                for path in sorted((store.root / "jobs").glob("*/job.json"))
            ]
        elif args.command == "inspect":
            result = inspect_job(settings, args.job_id)
        elif args.command == "resume":
            result = resume_job(settings, args.job_id).model_dump(mode="json")
        elif args.command == "approve":
            result = approve_job(settings, args.job_id, args.actor, args.digest).model_dump(
                mode="json"
            )
        elif args.command == "publish":
            result = publish_job(settings, args.job_id).model_dump(mode="json")
        else:
            result = edit_job(
                settings,
                args.job_id,
                hook_a=args.hook_a,
                hook_b=args.hook_b,
                primary_text=args.primary_text,
                headline=args.headline,
            ).model_dump(mode="json")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except AdLoomError as error:
        print(
            json.dumps({"error": error.error.model_dump(mode="json")}, ensure_ascii=False),
            file=sys.stderr,
        )
    except ValidationError:
        print(
            json.dumps(
                {"error": {"code": "E_INPUT_INVALID", "detail": "Input violates the data contract"}}
            ),
            file=sys.stderr,
        )
    except OSError as error:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "E_INPUT_INVALID",
                        "detail": f"Local file operation failed ({type(error).__name__})",
                    }
                }
            ),
            file=sys.stderr,
        )
    return 1
