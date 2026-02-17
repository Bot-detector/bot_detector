from bot_detector.event_queue import ReportsToInsertProducer
from fastapi import HTTPException, Request, status


def get_reports_to_insert_producer(request: Request) -> ReportsToInsertProducer:
    producer = getattr(request.app.state, "reports_to_insert_producer", None)
    if producer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="reports producer is not available",
        )
    return producer
