"""Serverless function handler."""
import json

from eventsbot import run, setup_from_env


def handle(*_) -> dict:
    """Handle serverless run."""

    config = setup_from_env()
    if not config:
        return {"body": json.dumps({"message": "Invalid configuration."}), "statusCode": 500}
    config["once"] = True
    added_events = run(config)
    if added_events == 0:
        msg = "No new events found."
    else:
        msg = f"{added_events} new event{'s' if added_events > 1 else ''} added."
    return {"body": json.dumps({"message": msg}), "statusCode": 200}
