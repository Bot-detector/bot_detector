from pydantic import BaseModel, field_validator

EXPECTED_SKILL_IDS: frozenset[int] = frozenset(range(25))


class Skill(BaseModel):
    id: int
    name: str
    rank: int
    level: int
    xp: int


class Activity(BaseModel):
    id: int
    name: str
    rank: int
    score: int


class PlayerStats(BaseModel):
    skills: list[Skill]
    activities: list[Activity]

    @field_validator("skills")
    @classmethod
    def _skills_complete(cls, value: list[Skill]) -> list[Skill]:
        """Rejects truncated payloads: every known skill id must be present.

        Unknown extra ids are tolerated, so a Jagex schema addition does
        not break scrapes; the smoke test flags the drift instead.
        """
        missing = EXPECTED_SKILL_IDS - {skill.id for skill in value}
        if missing:
            raise ValueError(
                f"truncated payload: missing skill ids {sorted(missing)}"
            )
        return value

    @field_validator("activities")
    @classmethod
    def _activities_present(cls, value: list[Activity]) -> list[Activity]:
        """Activities grow as Jagex adds them, so only presence and unique ids are pinned."""
        if not value:
            raise ValueError("activities must not be empty")
        ids = [activity.id for activity in value]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate activity ids")
        return value
