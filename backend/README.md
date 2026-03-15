AI Smart City Problem Solver
A backend API for intelligent citizen complaint reporting, powered by Amazon Nova on AWS Bedrock. Citizens submit city problems (potholes, broken lights, pollution, etc.) and the AI automatically classifies, routes, and tracks them — saving city staff hours of manual triage every week.

Built for the Amazon Nova AI Hackathon.

What It Does
A citizen spots a flooded road. They send a photo and a short description. Within seconds:

Amazon Nova sees the image — describes the damage in detail ("standing water approximately 30cm deep covering two lanes, road markings no longer visible")
Nova classifies the complaint — category, responsible department, severity, and a confidence score
The complaint is logged to PostgreSQL with GPS coordinates and full metadata
City managers get a summary — Nova groups all complaints by category and writes actionable insights ("8 flooding complaints on MG Road this week — recommend pre-monsoon drain inspection")
No manual reading. No misrouted tickets. No spreadsheets.

Amazon Nova Features
Feature	Endpoint	How Nova Is Used
Multimodal Vision	POST /report	Nova describes what it sees in the uploaded photo — damage type, size, hazards — before classification
Intelligent Classification	POST /report	Nova classifies issue into category, department, severity with a 0–1 confidence score, informed by both text and image
Cluster Summarization	GET /complaints/nova-summary	Nova reads groups of complaints by category and writes plain-English management insights with priority recommendations
Conversational Intake	POST /chat	Citizens describe their problem naturally in conversation — Nova guides them to provide all required info, then returns a structured draft ready to submit
Tech Stack
Framework: FastAPI + Uvicorn
AI: Amazon Nova Lite (multimodal) via AWS Bedrock (boto3)
Database: PostgreSQL (psycopg2-binary)
Rate Limiting: slowapi (10 requests/min on complaint submission)
Email: SMTP notifications on new complaints
Validation: Pydantic, image type + size checks
Setup
1. Install dependencies
pip install -r requirements.txt
2. Configure environment
cp .env.example .env
Edit .env with your values:

# AWS Bedrock (required)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
# PostgreSQL (required)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=smart_city
DB_USER=postgres
DB_PASSWORD=your_password
# Email notifications (optional)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=you@gmail.com
EMAIL_PASSWORD=your_app_password
NOTIFY_EMAIL=recipient@email.com
3. Create the database
In psql or pgAdmin, create the database:

CREATE DATABASE smart_city;
The tables are created automatically when the server starts.

4. Run the server
uvicorn main:app --reload --port 8000
API docs available at: http://localhost:8000/docs

API Endpoints
Method	Endpoint	Description
GET	/health	Health check
POST	/report	Submit a complaint (rate limited: 10/min)
GET	/complaints	List complaints with pagination + filters
GET	/complaints/nova-summary	Nova AI cluster summary by category
GET	/complaints/stats/summary	Aggregate statistics
GET	/complaints/{id}	Get complaint + full status history
PUT	/complaints/{id}	Update complaint fields
PATCH	/complaints/{id}/status	Update complaint status
DELETE	/complaints/{id}	Delete a complaint
POST	/chat	Conversational complaint intake via Nova
DELETE	/chat/{session_id}	Clear a chat session
Example: Submit a Complaint
curl -X POST http://localhost:8000/report \
  -F "issue=Flooded road" \
  -F "location=MG Road, near City Mall" \
  -F "description=Road is completely flooded after last night's rain, cars are stuck" \
  -F "latitude=12.9716" \
  -F "longitude=77.5946" \
  -F "image=@pothole.jpg"
Response:

{
  "id": "a3f1c2d4-...",
  "issue": "Severe Road Flooding",
  "category": "Infrastructure",
  "department": "Public Works Department",
  "severity": "high",
  "confidence_score": 0.94,
  "image_description": "Standing water approximately 30cm deep covering two lanes of road. Road markings are no longer visible. Two vehicles appear stranded near the median.",
  "status": "Complaint Registered",
  "location": "MG Road, near City Mall",
  "latitude": 12.9716,
  "longitude": 77.5946,
  "created_at": "2025-03-15T10:23:41"
}
Example: GET /complaints with filters
GET /complaints?category=Infrastructure&severity=high&page=1&limit=10
GET /complaints?search=pothole&date_from=2025-03-01
GET /complaints?status=In Progress&department=roads
Example: Conversational Intake
# Start a session
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123", "message": "there is a broken street light near the park"}'
Nova replies asking for the location. After 2-3 turns, when it has everything:

{
  "reply": "Thanks, I have all the details I need.",
  "ready_to_submit": true,
  "draft_complaint": {
    "issue": "Broken street light",
    "location": "Cubbon Park entrance, Bangalore",
    "description": "Street light has been out for 3 days, area is very dark at night"
  }
}
Send the draft_complaint fields directly to POST /report.

Filtering Reference
Parameter	Example	Description
page	1	Page number
limit	10	Results per page (max 100)
status	In Progress	Filter by status
severity	high	Filter by severity
category	Infrastructure	Filter by category
department	roads	Filter by department (partial match)
search	pothole	Keyword search across issue, description, location
date_from	2025-03-01	Complaints from this date
date_to	2025-03-31	Complaints up to this date
Database Schema
complaints
├── id                TEXT PRIMARY KEY
├── issue             TEXT
├── category          TEXT
├── department        TEXT
├── severity          TEXT  (low / medium / high / critical)
├── status            TEXT  (Complaint Registered / In Progress / Resolved / Rejected)
├── location          TEXT
├── description       TEXT
├── image_description TEXT  ← Nova's vision analysis of the photo
├── latitude          FLOAT
├── longitude         FLOAT
├── confidence_score  FLOAT ← Nova's classification confidence (0.0 – 1.0)
├── created_at        TIMESTAMP
└── updated_at        TIMESTAMP
status_history
├── id            SERIAL PRIMARY KEY
├── complaint_id  TEXT (FK → complaints)
├── old_status    TEXT
├── new_status    TEXT
└── changed_at    TIMESTAMP