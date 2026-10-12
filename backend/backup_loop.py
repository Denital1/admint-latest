from pathlib import Path
from datetime import datetime, timezone
import sqlite3, time, logging
logging.basicConfig(level=logging.INFO)
while True:
    try:
        source=Path("/data/db.sqlite3")
        if source.exists():
            destination=Path("/backups")/datetime.now(timezone.utc).strftime("admint-%Y%m%d-%H%M%S.sqlite3")
            reader=sqlite3.connect(f"file:{source}?mode=ro",uri=True)
            writer=sqlite3.connect(destination)
            try:
                reader.backup(writer)
                assert writer.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            finally: reader.close();writer.close()
            logging.info("Database backup completed")
    except Exception:
        logging.exception("Backup failed")
    time.sleep(86400)
