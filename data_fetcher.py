"""
Fetch upcoming Birdhaus events from Wix API using the birdhaus_data_pipeline.

Reuses the pipeline's API client, event querying, and transformation.
Adds V3 ticket definitions for capacity and guest counts for tickets sold.
"""

from collections import Counter
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from wix_api.client import WixAPIClient
from wix_api.events import EventsAPI
from wix_api.guests import GuestsAPI
from transformers.events import EventsTransformer


def fetch_ticket_definitions_v3(client, event_id):
    """Fetch V3 ticket definitions which include limited/initialLimit fields."""
    try:
        response = client.post(
            "/events/v3/ticket-definitions/query",
            json={
                "query": {
                    "filter": {"eventId": event_id},
                    "paging": {"limit": 100},
                }
            },
        )
        return response.get("ticketDefinitions", [])
    except Exception:
        return []


def format_ticket_info(definitions, ticket_holder_count):
    """
    Format ticket type info and capacity from V3 definitions + guest count.

    Args:
        definitions: V3 ticket definitions with limited/initialLimit
        ticket_holder_count: Number of TICKET_HOLDER guests (= tickets sold)

    Returns:
        tickets_str: e.g. "General Admission: 12"
        capacity_str: e.g. "12 / 60" or "Unlimited"
    """
    if not definitions:
        return str(ticket_holder_count), "Unknown"

    if len(definitions) == 1:
        defn = definitions[0]
        name = defn.get("name", "Ticket")
        limited = defn.get("limited", False)
        limit = defn.get("initialLimit")

        tickets_str = f"{name}: {ticket_holder_count}"
        if limited and limit is not None:
            capacity_str = f"{ticket_holder_count} / {limit}"
        else:
            capacity_str = "Unlimited"
        return tickets_str, capacity_str

    # Multiple ticket types — show types with aggregate sold count
    type_parts = []
    cap_parts = []
    for defn in definitions:
        name = defn.get("name", "Ticket")
        limited = defn.get("limited", False)
        limit = defn.get("initialLimit")
        type_parts.append(name)
        if limited and limit is not None:
            cap_parts.append(f"{name}: {limit}")
        else:
            cap_parts.append(f"{name}: Unlimited")

    tickets_str = f"{', '.join(type_parts)} ({ticket_holder_count} total)"
    capacity_str = ", ".join(cap_parts)
    return tickets_str, capacity_str


def fetch_upcoming_events(days_ahead: int = 60) -> pd.DataFrame:
    """
    Fetch upcoming TICKETING events within the next `days_ahead` days.

    Returns a DataFrame with event details, ticket type breakdown, and capacity.
    """
    cutoff_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    with WixAPIClient.from_env() as client:
        events_api = EventsAPI(client)
        raw_events = events_api.get_all_events(
            filter_dict={"status": ["UPCOMING"]}
        )

        ticketing_events = [
            e for e in raw_events
            if e.get("registration", {}).get("type") == "TICKETING"
        ]

        if not ticketing_events:
            return pd.DataFrame()

        transformed = EventsTransformer.transform_events(ticketing_events)

        filtered = [
            e for e in transformed
            if e.get("start_date") and today <= e["start_date"] <= cutoff_date
        ]

        if not filtered:
            return pd.DataFrame()

        # Fetch guests + V3 ticket definitions per event (parallel)
        guests_api = GuestsAPI(client)

        def fetch_event_data(event_id):
            try:
                guests = guests_api.get_all_guests_for_event(event_id)
                definitions = fetch_ticket_definitions_v3(client, event_id)

                defn_names = {
                    d.get("id", ""): d.get("name", "Ticket")
                    for d in definitions
                }

                holders = [g for g in guests if g.get("guestType") == "TICKET_HOLDER"]
                holder_count = len(holders)

                guest_list = []
                for g in holders:
                    details = g.get("guestDetails", {})
                    first = details.get("firstName", "")
                    last = details.get("lastName", "")
                    name = f"{first} {last}".strip() or "Guest"
                    ticket_type = defn_names.get(
                        g.get("ticketDefinitionId", ""), "Ticket"
                    )
                    guest_list.append({
                        "name": name,
                        "ticket_type": ticket_type,
                    })

                return event_id, holder_count, definitions, guest_list
            except Exception:
                return event_id, 0, [], []

        event_data = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(fetch_event_data, e["event_id"]): e["event_id"]
                for e in filtered
            }
            for future in as_completed(futures):
                event_id, holder_count, definitions, guest_list = future.result()
                event_data[event_id] = (holder_count, definitions, guest_list)

        # Build rows
        rows = []
        for event in filtered:
            holder_count, definitions, guest_list = event_data.get(
                event["event_id"], (0, [], [])
            )
            tickets_str, capacity_str = format_ticket_info(definitions, holder_count)

            rows.append({
                "Event": event.get("title", ""),
                "Date": event.get("start_date", ""),
                "Day": event.get("day_of_week", ""),
                "Time": event.get("start_time", ""),
                "Category": event.get("primary_category", ""),
                "Tickets": tickets_str,
                "Capacity": capacity_str,
                "EventUrl": event.get("event_page_url", ""),
                "Guests": guest_list,
            })

        df = pd.DataFrame(rows)
        df.sort_values("Date", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df
