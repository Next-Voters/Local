"""Google Calendar MCP server — runs as a standalone stdio subprocess.

This file is NOT imported by app code. It is launched by the registry as a
subprocess. Provides FastMCP tools wrapping the Google Calendar API v3 for
creating, listing, and deleting calendar events.

Credentials are read from the GOOGLE_SERVICE_ACCOUNT_JSON env var (JSON string
of a GCP service account key). The service account must be granted access to
the target calendar via Google Calendar's sharing settings.

Usage: python -m utils.mcp.google_calendar.server
"""

import json
import os
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("GoogleCalendar")

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_DEFAULT_CALENDAR = "primary"


def _get_service():
    """Build and return an authenticated Google Calendar API service."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON not set. "
            "Set it to the JSON content of your GCP service account key."
        )

    creds = Credentials.from_service_account_info(json.loads(sa_json), scopes=_SCOPES)
    return build("calendar", "v3", credentials=creds)


@mcp.tool
def create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    calendar_id: str = _DEFAULT_CALENDAR,
) -> dict[str, Any]:
    """Create a Google Calendar event.

    Args:
        summary: Event title.
        start_time: Start time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).
        end_time: End time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).
        description: Optional event description.
        location: Optional physical or virtual location.
        calendar_id: Calendar to create the event in (default: "primary").

    Returns:
        Created event resource dict including id and htmlLink.
    """
    service = _get_service()

    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    return service.events().insert(calendarId=calendar_id, body=body).execute()


@mcp.tool
def list_events(
    time_min: str,
    time_max: str | None = None,
    max_results: int = 10,
    calendar_id: str = _DEFAULT_CALENDAR,
) -> dict[str, Any]:
    """List upcoming calendar events within a time range.

    Args:
        time_min: Lower bound for event start time, ISO 8601 format.
        time_max: Upper bound for event start time, ISO 8601 format. Optional.
        max_results: Maximum number of events to return (default 10).
        calendar_id: Calendar to query (default: "primary").

    Returns:
        Dict with "items" list of event resource dicts.
    """
    service = _get_service()

    kwargs: dict[str, Any] = {
        "calendarId": calendar_id,
        "timeMin": time_min,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if time_max:
        kwargs["timeMax"] = time_max

    return service.events().list(**kwargs).execute()


@mcp.tool
def delete_event(
    event_id: str,
    calendar_id: str = _DEFAULT_CALENDAR,
) -> dict[str, Any]:
    """Delete a Google Calendar event by ID.

    Args:
        event_id: The ID of the event to delete.
        calendar_id: Calendar containing the event (default: "primary").

    Returns:
        Empty dict on success.
    """
    service = _get_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    return {"deleted": event_id}


if __name__ == "__main__":
    mcp.run(transport="stdio")
