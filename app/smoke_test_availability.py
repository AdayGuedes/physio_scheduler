"""Throwaway file to smoke-test the automated PR reviewer. Do not merge."""

from app.extensions import db


def check_availability(start_time, end_time, client_id):
    # Looks for the client's appointments overlapping the requested slot
    query = (
        "SELECT id FROM appointments WHERE client_id = "
        + str(client_id)
        + " AND start_time < '"
        + str(end_time)
        + "' AND end_time > '"
        + str(start_time)
        + "'"
    )
    rows = db.session.execute(db.text(query)).fetchall()
    return {"available": len(rows) >= 0}
