import os
import uuid
import json
import base64
import smtplib
from datetime import datetime
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List

import psycopg2
import boto3
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

load_dotenv()

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AI Smart City Problem Solver", version="3.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for chat sessions  { session_id: [{"role": ..., "content": ...}] }
chat_sessions: dict = {}


# ── Database ──────────────────────────────────────────────────────────────────

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
            image_description TEXT,
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
    # Safe migrations for existing databases
    for col in [
        "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS category TEXT",
        "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS latitude FLOAT",
        "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS longitude FLOAT",
        "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS confidence_score FLOAT",
        "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS image_description TEXT",
        "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]:
        cur.execute(col)
    conn.commit()
    cur.close()
    conn.close()


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email_notification(complaint: dict):
    try:
        host = os.getenv("EMAIL_HOST")
        port = int(os.getenv("EMAIL_PORT", 587))
        user = os.getenv("EMAIL_USER")
        password = os.getenv("EMAIL_PASSWORD")
        notify = os.getenv("NOTIFY_EMAIL")

        if not all([host, user, password, notify]):
            print("Email not configured, skipping notification")
            return

        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = notify
        msg["Subject"] = f"New Complaint: {complaint['issue']} - {complaint['severity'].upper()} severity"

        lat = complaint.get("latitude")
        lon = complaint.get("longitude")
        gps_info = f"{lat}, {lon}" if lat is not None and lon is not None else "Not provided"
        confidence = complaint.get("confidence_score")
        confidence_str = f"{confidence:.0%}" if confidence is not None else "N/A"
        image_desc = complaint.get("image_description") or "No image submitted"

        body = f"""
New city complaint submitted:

ID:                {complaint['id']}
Issue:             {complaint['issue']}
Category:          {complaint.get('category', 'N/A')}
Department:        {complaint['department']}
Severity:          {complaint['severity']}
AI Confidence:     {confidence_str}
Location:          {complaint['location']}
Description:       {complaint['description']}
GPS:               {gps_info}
Status:            {complaint['status']}
Submitted:         {complaint['created_at']}

AI Image Analysis:
{image_desc}
        """

        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, notify, msg.as_string())
        print(f"Email notification sent for complaint {complaint['id']}")
    except Exception as e:
        print(f"Email notification failed: {e}")


# ── Nova AI helpers ───────────────────────────────────────────────────────────

def get_bedrock_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def call_nova(messages: list, max_tokens: int = 512, temperature: float = 0.1) -> str:
    """Call Amazon Nova Lite and return the response text."""
    client = get_bedrock_client()
    response = client.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        body=json.dumps({
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature}
        }),
        contentType="application/json",
        accept="application/json"
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"]


# ── Feature 1: Nova Vision — describe what's in the image ────────────────────

def describe_image_with_nova(image_bytes: bytes) -> str:
    """
    Ask Amazon Nova to describe what it visually sees in the submitted photo.
    Returns a plain-English description stored alongside the complaint.
    """
    try:
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages = [{
            "role": "user",
            "content": [
                {
                    "text": (
                        "You are an AI assistant helping a smart city team assess infrastructure problems. "
                        "Look at this image carefully and describe exactly what you see: the type of problem, "
                        "its visible severity, approximate size or extent, any safety hazards, and any other "
                        "relevant details a city engineer would need. Be specific and factual. "
                        "Write 2-4 sentences."
                    )
                },
                {
                    "image": {
                        "format": "jpeg",
                        "source": {"bytes": image_b64}
                    }
                }
            ]
        }]
        return call_nova(messages, max_tokens=256, temperature=0.2)
    except Exception as e:
        print(f"Nova image description failed: {e}")
        return None


# ── Feature 2: Classify complaint ────────────────────────────────────────────

def classify_with_ai(issue: str, description: str, image_bytes: bytes = None, image_description: str = None) -> dict:
    try:
        vision_context = ""
        if image_description:
            vision_context = f"\nAI Image Analysis: {image_description}"

        prompt = f"""You are a smart city complaint classifier. Analyze this complaint and respond ONLY with a valid JSON object.

Issue: {issue}
Description: {description}{vision_context}

Respond with exactly this JSON structure:
{{
  "issue": "brief issue title",
  "category": "one of: Infrastructure, Environment, Safety, Utilities, Traffic, Public Health, Other",
  "department": "responsible city department",
  "severity": "one of: low, medium, high, critical",
  "confidence_score": 0.95
}}

The confidence_score must be a float between 0.0 and 1.0. If an image was analyzed, factor its contents into your classification."""

        content = [{"text": prompt}]

        if image_bytes and len(image_bytes) <= 5 * 1024 * 1024:
            content.append({
                "image": {
                    "format": "jpeg",
                    "source": {"bytes": base64.b64encode(image_bytes).decode("utf-8")}
                }
            })

        messages = [{"role": "user", "content": content}]
        text = call_nova(messages, max_tokens=256, temperature=0.1)
        start = text.find("{")
        end = text.rfind("}") + 1
        parsed = json.loads(text[start:end])
        if "confidence_score" not in parsed:
            parsed["confidence_score"] = 0.75
        return parsed

    except Exception as e:
        print(f"AI classification failed: {e}")
        return {
            "issue": issue,
            "category": "Other",
            "department": "General Services",
            "severity": "medium",
            "confidence_score": 0.0
        }


# ── Feature 3: Nova cluster summarization ─────────────────────────────────────

def summarize_category_with_nova(category: str, complaints: list) -> str:
    """
    Ask Nova to write a plain-English insight summary for a group of complaints
    in the same category — like a city manager would want to read.
    """
    try:
        complaint_lines = "\n".join([
            f"- [{c['severity'].upper()}] {c['issue']} | {c['location']} | Status: {c['status']}"
            for c in complaints[:20]
        ])
        prompt = f"""You are an AI assistant for a city management team. Here are recent citizen complaints in the '{category}' category:

{complaint_lines}

Write a 2-3 sentence plain-English summary that a city manager would find useful. Include: the most common problem type, any patterns by location or severity, and a suggested priority action. Be concise and actionable."""

        messages = [{"role": "user", "content": [{"text": prompt}]}]
        return call_nova(messages, max_tokens=200, temperature=0.4)
    except Exception as e:
        print(f"Nova summarization failed for {category}: {e}")
        return f"Unable to generate summary for {category}."


# ── Startup ───────────────────────────────────────────────────────────────────

init_db()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "AI Smart City Problem Solver", "version": "3.0.0"}


@app.post("/report")
@limiter.limit("10/minute")
async def report_issue(
    request: Request,
    issue: str = Form(...),
    location: str = Form(...),
    description: str = Form(...),
    latitude: float = Form(None),
    longitude: float = Form(None),
    image: UploadFile = File(None)
):
    image_bytes = None
    image_description = None

    if image:
        allowed_content_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
        if image.content_type not in allowed_content_types:
            raise HTTPException(
                status_code=400,
                detail=f"Image must be one of: {', '.join(allowed_content_types)}"
            )
        contents = await image.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image must be under 5MB")
        image_bytes = contents

        # Feature 1: Nova Vision — describe the image before classification
        image_description = describe_image_with_nova(image_bytes)

    # Feature 2: Classify using both text + image + vision description
    ai_result = classify_with_ai(issue, description, image_bytes, image_description)

    complaint_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    confidence_score = ai_result.get("confidence_score", 0.0)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO complaints
            (id, issue, category, department, severity, status, location, description,
             image_description, latitude, longitude, confidence_score, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        complaint_id,
        ai_result.get("issue", issue),
        ai_result.get("category"),
        ai_result.get("department", "General Services"),
        ai_result.get("severity", "medium"),
        "Complaint Registered",
        location,
        description,
        image_description,
        latitude,
        longitude,
        confidence_score,
        created_at
    ))
    cur.execute("""
        INSERT INTO status_history (complaint_id, old_status, new_status)
        VALUES (%s, %s, %s)
    """, (complaint_id, None, "Complaint Registered"))
    conn.commit()
    cur.close()
    conn.close()

    complaint = {
        "id": complaint_id,
        "issue": ai_result.get("issue", issue),
        "category": ai_result.get("category"),
        "department": ai_result.get("department", "General Services"),
        "severity": ai_result.get("severity", "medium"),
        "confidence_score": confidence_score,
        "status": "Complaint Registered",
        "location": location,
        "description": description,
        "image_description": image_description,
        "latitude": latitude,
        "longitude": longitude,
        "created_at": str(created_at)
    }

    send_email_notification(complaint)
    return complaint


@app.get("/complaints")
async def list_complaints(
    page: int = 1,
    limit: int = 10,
    status: str = None,
    severity: str = None,
    category: str = None,
    department: str = None,
    search: str = None,
    date_from: str = None,
    date_to: str = None
):
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

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
    cur.execute(f"SELECT COUNT(*) FROM complaints {where}", params)
    total = cur.fetchone()[0]

    cur.execute(
        f"""SELECT id, issue, category, department, severity, status, location, description,
                   latitude, longitude, confidence_score, image_description, created_at
            FROM complaints {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s""",
        params + [limit, offset]
    )
    rows = cur.fetchall()
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
            "image_description": row[11],
            "created_at": str(row[12])
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


# ── Nova Cluster Summary endpoint ─────────────────────────────────────────────

@app.get("/complaints/nova-summary")
async def nova_cluster_summary():
    """
    Feature 2: Groups recent complaints by category and asks Amazon Nova
    to generate a plain-English insight summary for each group.
    Useful for city dashboards and management reports.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, issue, category, department, severity, status, location, created_at
        FROM complaints
        ORDER BY created_at DESC
        LIMIT 200
    """)
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM complaints")
    total = cur.fetchone()[0]
    cur.close()
    conn.close()

    grouped = defaultdict(list)
    for row in rows:
        cat = row[2] or "Uncategorized"
        grouped[cat].append({
            "id": row[0],
            "issue": row[1],
            "category": row[2],
            "department": row[3],
            "severity": row[4],
            "status": row[5],
            "location": row[6],
            "created_at": str(row[7])
        })

    summaries = {}
    for category, complaints in grouped.items():
        summaries[category] = {
            "count": len(complaints),
            "nova_insight": summarize_category_with_nova(category, complaints),
            "severity_breakdown": {
                s: sum(1 for c in complaints if c["severity"] == s)
                for s in ["low", "medium", "high", "critical"]
            }
        }

    return {
        "total_complaints_analyzed": total,
        "categories_found": len(summaries),
        "generated_at": str(datetime.utcnow()),
        "summaries": summaries
    }


@app.get("/complaints/stats/summary")
async def stats_summary():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM complaints")
    total = cur.fetchone()[0]

    cur.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status")
    by_status = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("SELECT severity, COUNT(*) FROM complaints GROUP BY severity")
    by_severity = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("SELECT department, COUNT(*) FROM complaints GROUP BY department ORDER BY COUNT(*) DESC LIMIT 5")
    by_department = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("SELECT category, COUNT(*) FROM complaints GROUP BY category ORDER BY COUNT(*) DESC")
    by_category = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("SELECT AVG(confidence_score) FROM complaints WHERE confidence_score IS NOT NULL")
    avg_confidence = cur.fetchone()[0]

    cur.close()
    conn.close()

    return {
        "total": total,
        "by_status": by_status,
        "by_severity": by_severity,
        "by_department": by_department,
        "by_category": by_category,
        "avg_confidence_score": round(float(avg_confidence), 3) if avg_confidence else None
    }


@app.get("/complaints/{complaint_id}")
async def get_complaint(complaint_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, issue, category, department, severity, status, location, description,
                  latitude, longitude, confidence_score, image_description, created_at
           FROM complaints WHERE id = %s""",
        (complaint_id,)
    )
    row = cur.fetchone()
    cur.execute(
        "SELECT old_status, new_status, changed_at FROM status_history WHERE complaint_id = %s ORDER BY changed_at ASC",
        (complaint_id,)
    )
    history = [{"from": r[0], "to": r[1], "changed_at": str(r[2])} for r in cur.fetchall()]
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Complaint not found")

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
        "image_description": row[11],
        "created_at": str(row[12]),
        "status_history": history
    }


@app.patch("/complaints/{complaint_id}/status")
async def update_status(complaint_id: str, status: str = Form(...)):
    valid = ["Complaint Registered", "In Progress", "Resolved", "Rejected"]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(valid)}")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM complaints WHERE id = %s", (complaint_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Complaint not found")

    old_status = row[0]
    cur.execute("UPDATE complaints SET status=%s, updated_at=%s WHERE id=%s", (status, datetime.utcnow(), complaint_id))
    cur.execute(
        "INSERT INTO status_history (complaint_id, old_status, new_status) VALUES (%s, %s, %s)",
        (complaint_id, old_status, status)
    )
    conn.commit()
    cur.close()
    conn.close()

    return {"message": "Status updated", "id": complaint_id, "old_status": old_status, "new_status": status}


@app.put("/complaints/{complaint_id}")
async def update_complaint(
    complaint_id: str,
    issue: str = Form(None),
    location: str = Form(None),
    description: str = Form(None),
    department: str = Form(None),
    severity: str = Form(None),
    latitude: float = Form(None),
    longitude: float = Form(None)
):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM complaints WHERE id = %s", (complaint_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Complaint not found")

    fields = []
    params = []
    if issue is not None:
        fields.append("issue = %s"); params.append(issue)
    if location is not None:
        fields.append("location = %s"); params.append(location)
    if description is not None:
        fields.append("description = %s"); params.append(description)
    if department is not None:
        fields.append("department = %s"); params.append(department)
    if severity is not None:
        valid_severities = ["low", "medium", "high", "critical"]
        if severity not in valid_severities:
            raise HTTPException(status_code=400, detail=f"Severity must be one of: {', '.join(valid_severities)}")
        fields.append("severity = %s"); params.append(severity)
    if latitude is not None:
        fields.append("latitude = %s"); params.append(latitude)
    if longitude is not None:
        fields.append("longitude = %s"); params.append(longitude)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    fields.append("updated_at = %s")
    params.append(datetime.utcnow())
    params.append(complaint_id)
    cur.execute(f"UPDATE complaints SET {', '.join(fields)} WHERE id = %s", params)
    conn.commit()
    cur.close()
    conn.close()

    return {"message": "Complaint updated", "id": complaint_id}


@app.delete("/complaints/{complaint_id}")
async def delete_complaint(complaint_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM complaints WHERE id=%s", (complaint_id,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    if not deleted:
        raise HTTPException(status_code=404, detail="Complaint not found")

    return {"message": "Complaint deleted", "id": complaint_id}


# ── Feature 3: Conversational Intake ─────────────────────────────────────────

class ChatMessage(BaseModel):
    session_id: str
    message: str


SYSTEM_PROMPT = """You are a friendly AI assistant helping citizens report city problems through a smart city portal.
Your goal is to gather all the information needed to file a proper complaint by having a natural conversation.

You need to collect:
1. What the problem is (issue title)
2. Where it is located (street, area, or landmark)
3. A brief description of the problem

Ask for one piece of missing information at a time. Be friendly and concise.
Once you have all three pieces of information, end your response with exactly this on a new line:
READY_TO_SUBMIT: {"issue": "...", "location": "...", "description": "..."}

If the user has already provided all info in their first message, extract it and respond with the READY_TO_SUBMIT line immediately."""


@app.post("/chat")
async def chat_with_nova(body: ChatMessage):
    """
    Feature 3: Conversational complaint intake powered by Amazon Nova.
    Citizens describe their issue in natural language across multiple turns.
    Nova guides them to provide all required information, then returns a
    structured draft ready to submit to POST /report.
    """
    session_id = body.session_id
    user_message = body.message

    if session_id not in chat_sessions:
        chat_sessions[session_id] = []

    history = chat_sessions[session_id]
    history.append({"role": "user", "content": [{"text": user_message}]})

    system_prompt_message = {
        "role": "user",
        "content": [{"text": SYSTEM_PROMPT + "\n\nConversation starts now. Wait for the citizen's first message."}]
    }
    assistant_ack = {
        "role": "assistant",
        "content": [{"text": "Understood. I'll help citizens report their city problems conversationally."}]
    }

    full_messages = [system_prompt_message, assistant_ack] + history

    try:
        reply = call_nova(full_messages, max_tokens=512, temperature=0.5)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Nova call failed: {e}")

    history.append({"role": "assistant", "content": [{"text": reply}]})
    chat_sessions[session_id] = history

    draft = None
    if "READY_TO_SUBMIT:" in reply:
        try:
            marker = "READY_TO_SUBMIT:"
            json_str = reply[reply.index(marker) + len(marker):].strip()
            end = json_str.rfind("}") + 1
            draft = json.loads(json_str[:end])
            reply = reply[:reply.index(marker)].strip()
        except Exception:
            pass

    return {
        "session_id": session_id,
        "reply": reply,
        "draft_complaint": draft,
        "ready_to_submit": draft is not None,
        "turns": len([m for m in history if m["role"] == "user"])
    }


@app.delete("/chat/{session_id}")
async def clear_chat_session(session_id: str):
    """Clear a chat session to start over."""
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    return {"message": "Session cleared", "session_id": session_id}
