from fastapi import APIRouter, HTTPException

from ..database import get_db

router = APIRouter(tags=["results"])


@router.get("/events/{event_id}/results")
async def get_results(event_id: str):
    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM events WHERE id = ?", (event_id,)
        ) as cursor:
            event = await cursor.fetchone()

        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")

        async with db.execute(
            "SELECT COUNT(*) as cnt FROM submissions WHERE event_id = ?", (event_id,)
        ) as cursor:
            count_row = await cursor.fetchone()

        async with db.execute(
            """
            SELECT a.avail_date, a.hour,
                   SUM(CASE WHEN a.status='yes' THEN 1 ELSE 0 END) as yes_count,
                   SUM(CASE WHEN a.status='maybe' THEN 1 ELSE 0 END) as maybe_count,
                   SUM(CASE WHEN a.status='no' THEN 1 ELSE 0 END) as no_count,
                   (SUM(CASE WHEN a.status='yes' THEN 2 ELSE 0 END) +
                    SUM(CASE WHEN a.status='maybe' THEN 1 ELSE 0 END) -
                    SUM(CASE WHEN a.status='no' THEN 2 ELSE 0 END)) as score
            FROM availability a
            JOIN submissions s ON s.id = a.submission_id
            WHERE s.event_id = ?
            GROUP BY a.avail_date, a.hour
            ORDER BY score DESC, a.avail_date, a.hour
            """,
            (event_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    return {
        "respondent_count": count_row["cnt"],
        "slots": [
            {
                "date": r["avail_date"],
                "hour": r["hour"],
                "yes": r["yes_count"],
                "maybe": r["maybe_count"],
                "no": r["no_count"],
                "score": r["score"],
            }
            for r in rows
        ],
    }
