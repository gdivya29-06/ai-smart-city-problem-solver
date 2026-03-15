import os
import uuid
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "smart_city"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "")
    )


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id TEXT PRIMARY KEY,
            issue TEXT NOT NULL,
            category TEXT,
            department TEXT NOT NULL,
            severity TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'Complaint Registered',
            location TEXT,
            description TEXT,
            latitude FLOAT,
            longitude FLOAT,
            confidence_score FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS status_history (
            id SERIAL PRIMARY KEY,
            complaint_id TEXT REFERENCES complaints(id) ON DELETE CASCADE,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized successfully.")


def save_complaint(issue, department, location, description, category=None, severity="medium",
                   latitude=None, longitude=None, confidence_score=None):
    complaint_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    status = "Complaint Registered"

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO complaints
                (id, issue, category, department, severity, status, location, description, latitude, longitude, confidence_score, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (complaint_id, issue, category, department, severity, status,
              location, description, latitude, longitude, confidence_score, created_at))
        cur.execute("""
            INSERT INTO status_history (complaint_id, old_status, new_status)
            VALUES (%s, %s, %s)
        """, (complaint_id, None, status))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {
        "id": complaint_id,
        "issue": issue,
        "category": category,
        "department": department,
        "severity": severity,
        "status": status,
        "location": location,
        "description": description,
        "latitude": latitude,
        "longitude": longitude,
        "confidence_score": confidence_score,
        "created_at": str(created_at),
    }


def get_all_complaints(page=1, limit=10, status=None, severity=None,
                       category=None, department=None, search=None,
                       date_from=None, date_to=None):
    offset = (page - 1) * limit
    filters = []
    params = []

    if status:
        filters.append("status = %s")
        params.append(status)
    if severity:
        filters.append("severity = %s")
        params.append(severity)
    if category:
        filters.append("category ILIKE %s")
        params.append(f"%{category}%")
    if department:
        filters.append("department ILIKE %s")
        params.append(f"%{department}%")
    if search:
        filters.append("(issue ILIKE %s OR description ILIKE %s OR location ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if date_from:
        filters.append("created_at >= %s")
        params.append(date_from)
    if date_to:
        filters.append("created_at <= %s")
        params.append(date_to)

    where = "WHERE " + " AND ".join(filters) if filters else ""

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM complaints {where}", params)
        total = cur.fetchone()[0]

        cur.execute(
            f"""SELECT id, issue, category, department, severity, status, location, description,
                       latitude, longitude, confidence_score, created_at
                FROM complaints {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s""",
            params + [limit, offset]
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "issue": row[1],
            "category": row[2],
            "department": row[3],
            "severity": row[4],
            "status": row[5],
            "location": row[6],
            "description": row[7],
            "latitude": row[8],
            "longitude": row[9],
            "confidence_score": row[10],
            "created_at": str(row[11])
        })

    total_pages = (total + limit - 1) // limit
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        "results": results
    }


def get_complaint_by_id(complaint_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, issue, category, department, severity, status, location, description,
                   latitude, longitude, confidence_score, created_at
            FROM complaints WHERE id = %s
        """, (complaint_id,))
        row = cur.fetchone()

        cur.execute("""
            SELECT old_status, new_status, changed_at
            FROM status_history WHERE complaint_id = %s ORDER BY changed_at ASC
        """, (complaint_id,))
        history = [
            {"from": r[0], "to": r[1], "changed_at": str(r[2])}
            for r in cur.fetchall()
        ]
    finally:
        cur.close()
        conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "issue": row[1],
        "category": row[2],
        "department": row[3],
        "severity": row[4],
        "status": row[5],
        "location": row[6],
        "description": row[7],
        "latitude": row[8],
        "longitude": row[9],
        "confidence_score": row[10],
        "created_at": str(row[11]),
        "status_history": history
    }


def update_complaint_status(complaint_id, new_status):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT status FROM complaints WHERE id = %s", (complaint_id,))
        row = cur.fetchone()
        if not row:
            return False

        old_status = row[0]
        cur.execute(
            "UPDATE complaints SET status = %s, updated_at = %s WHERE id = %s",
            (new_status, datetime.utcnow(), complaint_id)
        )
        cur.execute(
            "INSERT INTO status_history (complaint_id, old_status, new_status) VALUES (%s, %s, %s)",
            (complaint_id, old_status, new_status)
        )
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()
