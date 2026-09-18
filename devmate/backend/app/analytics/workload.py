"""
Analytics: Team workload distribution (Business question #3)

Deliberately its own module, the same way app/ingestion/document_loader.py is -
a focused piece that knows how to answer ONE question, given plain data, with no 
FastAPI awareness at all. KnowledgeBaseService will call into this; but it does
not contain the pandas/numpy logic itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models import Ticket, User

PRIORITY_WEIGHT = {"Low": 1, "Medium":2, "High":3, "Critical":4}

OPEN_STATUSES = {"Open", "In-Progress"}


def _tickets_to_frame(tickets: list[Ticket]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "id": ticket.id,
            "priority": ticket.priority.value,
            "status": ticket.status.value,
            "assignee_id": ticket.assignee_id
        }
        for ticket in tickets
    ])

def _users_to_frame(users: list[User]) -> pd.DataFrame:
    return pd.DataFrame([{"id": user.id, "team": user.team} for user in users])


def compute_team_workload(tickets: list[Ticket], users: list[User]) -> dict:
    """
    Answers business question #3

    For every team with at least one OPEN or IN-PROGRESS ticket: how many
    such tickets it has, a priority-wighted 'load score', that team's share 
    of the total load across all teams, and whether its load is a statistical
    outlier (more than one standard deviation above the mean).
    """

    tickets_df = _tickets_to_frame(tickets)
    users_df = _users_to_frame(users)

    #this merge function acts very similarly to a join in SQL
    merged = tickets_df.merge(
        users_df, left_on="assignee_id", right_on="id", suffixes=("_ticket", "_user")
    )

    #here we can filter the merged df to only include tickets that have an open status
    open_tickets = merged[merged["status"].isin(OPEN_STATUSES).copy()]

    #here we map our priority values to their corresponding weights
    open_tickets["priority_weight"] = open_tickets["priority"].map(PRIORITY_WEIGHT)

    #group tickets by their team
    counts = open_tickets.groupby("team").size()
    #load score for each team
    load = open_tickets.groupby("team")["priority_weight"].sum()

    #next, we can convert the team names and load values to numpy arrays for further calculations
    teams = load.index.to_numpy()
    load_array = load.to_numpy(dtype=float)

    #next, we calculate the total load, share percentage, mean load, and standard deviation of the load
    #and if a team is overloaded
    total_load = float(np.sum(load_array)) if load_array.size else 0.0
    share_pct = (load_array / total_load * 100) if total_load > 0 else np.zeros_like(load_array)
    mean_load = float(np.mean(load_array)) if load_array.size else 0.0
    std_load = float(np.std(load_array)) if load_array.size else 0.0
    overloaded = load_array > (mean_load + std_load)

    #finally, we can construct a report for each team
    team_reports = [
        {
            "team": str(team),
            "open_ticket_count": int(counts[team]),
            "load_score": float(load_array[i]),
            "load_share_pct": float(share_pct[i]),
            "is_overloaded": bool(overloaded[i])
        }
        for i, team in enumerate(teams)
    ]

    return {
        "teams": team_reports,
        "total_open_tickets": int(len(open_tickets)),
        "mean_load_score": mean_load,
        "std_load_score": std_load,
    }