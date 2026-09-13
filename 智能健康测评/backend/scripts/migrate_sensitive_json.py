"""Backup and migrate health JSON columns to AES-256-GCM ciphertext.

Run once against the configured database before deploying the new models:
`venv/Scripts/python.exe scripts/migrate_sensitive_json.py`.
"""

import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.data_protection import encrypt_text
from app.core.database import Base, engine
from app.utils.minio_client import get_minio


MIGRATIONS = {
    "meal_records": [("items", "id")],
    "tongue_records": [("box", "id"), ("detail", "id")],
}


def backup(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    dump = out_dir / "health_assessment.sql"
    mysqldump = shutil.which("mysqldump")
    if mysqldump:
        cmd = [mysqldump, "--host", settings.MYSQL_HOST, "--port", str(settings.MYSQL_PORT),
               "--user", settings.MYSQL_USER, f"--password={settings.MYSQL_PASSWORD}",
               "--single-transaction", settings.MYSQL_DB]
        with dump.open("w", encoding="utf-8") as handle:
            subprocess.run(cmd, stdout=handle, check=True)
    else:
        # A row-level JSON backup still gives a recoverable snapshot when mysqldump is absent.
        with engine.begin() as conn, (out_dir / "sensitive_rows.json").open("w", encoding="utf-8") as handle:
            snapshot = {}
            for table, columns in MIGRATIONS.items():
                fields = ["id", *(column for column, _ in columns)]
                rows = conn.execute(text(f"SELECT {', '.join(fields)} FROM {table}")).mappings().all()
                snapshot[table] = [{key: value for key, value in row.items()} for row in rows]
            json.dump(snapshot, handle, ensure_ascii=False, default=str, indent=2)


def migrate() -> None:
    if engine.dialect.name != "mysql":
        raise SystemExit(f"This migration targets MySQL, got {engine.dialect.name}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup(Path("backups") / f"health_data_{timestamp}")
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in MIGRATIONS.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for column, key in columns:
                if column not in existing:
                    continue
                rows = conn.execute(text(f"SELECT {key}, {column} FROM {table}")).all()
                conn.execute(text(f"ALTER TABLE {table} MODIFY COLUMN {column} LONGTEXT"))
                for row_id, value in rows:
                    if value is None:
                        continue
                    if isinstance(value, str):
                        try:
                            payload = json.loads(value)
                        except json.JSONDecodeError:
                            payload = value
                    else:
                        payload = value
                    token = encrypt_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                    conn.execute(text(f"UPDATE {table} SET {column} = :value WHERE {key} = :id"),
                                 {"value": token, "id": row_id})
        # New private-image metadata columns are additive and therefore safe to run repeatedly.
        tongue_columns = {column["name"] for column in inspector.get_columns("tongue_records")}
        if "image_bucket" not in tongue_columns:
            conn.execute(text("ALTER TABLE tongue_records ADD COLUMN image_bucket VARCHAR(100) DEFAULT 'health-tongue'"))
        if "image_object_name" not in tongue_columns:
            conn.execute(text("ALTER TABLE tongue_records ADD COLUMN image_object_name LONGTEXT"))
        if "image_mime" not in tongue_columns:
            conn.execute(text("ALTER TABLE tongue_records ADD COLUMN image_mime VARCHAR(80) DEFAULT 'image/jpeg'"))
        if "image_url" in tongue_columns:
            conn.execute(text("ALTER TABLE tongue_records MODIFY COLUMN image_url LONGTEXT"))
        # Migrate legacy public tongue URLs when the object store is reachable. Unmigrated URLs
        # are still encrypted in the database and can be handled by the deletion outbox later.
        rows = conn.execute(text("SELECT id, image_url, image_object_name FROM tongue_records "
                                "WHERE image_url IS NOT NULL AND image_url <> ''")).all()
        for row_id, image_url, object_name in rows:
            if object_name:
                continue
            encrypted_url = encrypt_text(image_url)
            try:
                parsed = urlparse(image_url)
                parts = parsed.path.strip("/").split("/", 1)
                payload = get_minio().download_bytes_from_bucket(parts[0], parts[1]) if len(parts) == 2 else None
                if payload:
                    new_name = f"tongue/legacy/{uuid.uuid4().hex}.enc"
                    get_minio().upload_private_encrypted_bytes("health-tongue", new_name, payload, "image/jpeg")
                    conn.execute(text("UPDATE tongue_records SET image_url = :url, image_bucket = 'health-tongue', "
                                       "image_object_name = :name, image_mime = 'image/jpeg' WHERE id = :id"),
                                 {"url": "", "name": encrypt_text(new_name), "id": row_id})
                    continue
            except Exception:
                pass
            conn.execute(text("UPDATE tongue_records SET image_url = :url WHERE id = :id"),
                         {"url": encrypted_url, "id": row_id})
    Base.metadata.create_all(bind=engine)
    print("Sensitive JSON migration completed; backup created before ALTER TABLE.")


if __name__ == "__main__":
    migrate()
