from pydantic import BaseModel


class FeedbackExportItem(BaseModel):
    subject_name: str
    is_banned: bool
    vote: int
    prediction: str
