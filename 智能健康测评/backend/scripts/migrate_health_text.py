"""Encrypt legacy health text after HEALTH_DATA_ENCRYPTION_KEY is configured.

Run after a database backup and a backend restart. The ORM transparently decrypts old plaintext
values and encrypts them again on assignment; no records are deleted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.data_protection import encryption_configured
from app.core.database import SessionLocal
from app.models.assessment import UserHealthRiskAssessment
from app.models.assistant import AssistantMessage, AssistantMemory, UserProfile
from app.models.meal import MealRecord
from app.models.plan import MealPlan


FIELDS = (
    (UserProfile, ("allergies", "conditions", "preferences")),
    (AssistantMessage, ("content",)),
    (AssistantMemory, ("content",)),
    (UserHealthRiskAssessment, ("assessment_basis", "recommendations", "llm_report", "disease_condition")),
    (MealRecord, ("note",)),
    (MealPlan, ("personalization", "review_note")),
)


def main() -> None:
    if not encryption_configured():
        raise SystemExit("Set HEALTH_DATA_ENCRYPTION_KEY before migrating health text")
    db = SessionLocal()
    counts = {}
    try:
        for model, fields in FIELDS:
            count = 0
            for row in db.query(model).all():
                changed = False
                for field in fields:
                    value = getattr(row, field)
                    if value and not str(value).startswith("enc:v1:"):
                        setattr(row, field, value)
                        changed = True
                count += int(changed)
            counts[model.__tablename__] = count
        db.commit()
    finally:
        db.close()
    print(f"Encrypted legacy rows: {counts}")


if __name__ == "__main__":
    main()
