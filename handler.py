"""Serverless function handler."""
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Doing a conditional import avoids the need to install the library
    # when deploying the function
    from scaleway_functions_python.framework.v1.hints import Context, Event, Response

from eventsbot import run, setup_from_env


def handle(event: "Event", context: "Context") -> "Response":  # noqa: ARG001
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
