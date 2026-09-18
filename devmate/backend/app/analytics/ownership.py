"""
Analytics: Document ownership & staleness by team
Day 5 Phase B student challenge answer key
"""

#from __future__ import annotations

import numpy as np
import pandas as pd

from app.models import Document, DocumentCategory, User

STALE_THRESHOLD_DAYS = 90
STALE_RISK_THRESHOLD_PCT = 50.0

def _documents_to_frame(documents: list[Document]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "id": document.id,
            "owner_id": document.owner_id,
            "days_since_reviewed": document.days_since_last_reviewed(),
            "stale_eligible": document.category != DocumentCategory.POSTMORTEM
        }
        for document in documents
    ])

def _users_to_frame(users: list[User]) -> pd.DataFrame:
    return pd.DataFrame([{"id": user.id, "team": user.team} for user in users])

def compute_document_ownership(documents: list[Document], users: list[User]) -> dict:
    """
    For every team that owns at least one document: how many documents it owns, how many
    of those documents are stale(excluding postmortems), and what share of its owned documents
    that represents.

    """

    documents_df = _documents_to_frame(documents)
    users_df = _users_to_frame(users)

    merged = documents_df.merge(
        users_df, left_on="owner_id", right_on="id", suffixes=("_doc", "_user")
    )

    merged["is_stale"] = merged["stale_eligible"] & (merged["days_since_reviewed"] > STALE_THRESHOLD_DAYS)

    owned = merged.groupby("team").size()
    """
    Summing a boolean column per group (as opposed to filtering to only the stale rows and THEN
    grouping and counting) already gives every team an explicit 0 here, not a missing row - verified
    directly. The .reindex(...) is defensive, not load-bearing for this specific use case: it guarantees
    the same correct result even if this line were later rewritten as the filter-first version, where a
    team with zero stale documents WOULD otherwise disappear from the series entirely.
    """
    stale = merged.groupby("team")["is_stale"].sum().reindex(owned.index, fill_value=0)

    teams = owned.index.to_numpy()
    owned_array = owned.to_numpy(dtype=float)
    stale_array = stale.to_numpy(dtype=float)

    """
    np.divide 'where=' guards against the same zero-denominator case that the share_pct
    handled with a plain 'if' in our workload.py module. Here it is shown as an array-wide
    equivalent, since owned_array can have more than one team in it at once
    """
    stale_share_pct = np.divide(
        stale_array, owned_array,
        out=np.zeros_like(stale_array),
        where=owned_array != 0,
    ) * 100

    flagged = stale_share_pct > STALE_RISK_THRESHOLD_PCT

    team_reports = [
        {
            "team": str(team),
            "owned_document_count": int(owned_array[i]),
            "stale_document_count": int(stale_array[i]),
            "stale_share_pct": float(stale_share_pct[i]),
            "is_stale_risk": bool(flagged[i]),
        }
        for i, team in enumerate(teams)
    ]

    return {
        "teams": team_reports,
        "total_documents": int(len(documents))
    }