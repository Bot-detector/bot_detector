from typing import Generator

from pydantic import BaseModel


class ReportToInsertStruct(BaseModel):
    pass


def create_reports_to_insert(
    count: int,
) -> Generator[ReportToInsertStruct, None, None]:
    raise NotImplementedError("Report seeding not yet implemented")
