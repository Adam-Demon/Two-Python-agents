"""
init_db.py
Creates a small SQLite database of SYNTHETIC hospital equipment and
maintenance records. No real patient data, PHI, or credentials.

Run once:
    python data/init_db.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "hospital_equipment.db")


def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE equipment (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            status TEXT NOT NULL,
            last_service_date TEXT NOT NULL,
            next_service_due TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE maintenance_log (
            id INTEGER PRIMARY KEY,
            equipment_id INTEGER NOT NULL,
            technician TEXT NOT NULL,
            notes TEXT NOT NULL,
            service_date TEXT NOT NULL,
            FOREIGN KEY (equipment_id) REFERENCES equipment (id)
        )
    """)

    equipment_rows = [
        (1, "Infusion Pump A12", "Ward 3", "operational", "2026-08-01", "2026-11-01"),
        (2, "Portable Ventilator V7", "ICU", "needs_service", "2026-05-15", "2026-10-15"),
        (3, "Defibrillator D3", "ER Bay 2", "operational", "2026-09-10", "2026-12-10"),
        (4, "MRI Scanner M1", "Radiology", "operational", "2026-07-20", "2027-01-20"),
        (5, "Patient Monitor PM9", "Ward 1", "out_of_service", "2026-06-01", "2026-09-01"),
    ]
    cur.executemany(
        "INSERT INTO equipment VALUES (?, ?, ?, ?, ?, ?)", equipment_rows
    )

    maintenance_rows = [
        (1, 1, "Tech. Ahmed Saleh", "Routine calibration, no issues found.", "2026-08-01"),
        (2, 2, "Tech. Lina Youssef", "Flow sensor replaced, follow-up required.", "2026-05-15"),
        (3, 3, "Tech. Ahmed Saleh", "Battery replaced, tested OK.", "2026-09-10"),
        (4, 5, "Tech. Omar Faris", "Display unit failure, awaiting replacement part.", "2026-06-01"),
    ]
    cur.executemany(
        "INSERT INTO maintenance_log VALUES (?, ?, ?, ?, ?)", maintenance_rows
    )

    conn.commit()
    conn.close()
    print(f"Synthetic hospital equipment DB created at: {DB_PATH}")


if __name__ == "__main__":
    init_db()
