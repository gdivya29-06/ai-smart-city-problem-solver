<<<<<<< HEAD
AI model code for detecting city problems like potholes and garbage.
=======
# 🏙️ AI Smart City Problem Solver

> Powered by **Amazon Nova** — Built for the Amazon Nova Hackathon

An AI-powered platform that allows citizens to report city infrastructure problems by simply uploading a photo. Amazon Nova Vision automatically detects and analyzes the issue, assigns a priority score, and routes it to city authorities for resolution.

---

## 🎯 Problem We're Solving

Cities receive thousands of infrastructure complaints daily — potholes, garbage overflow, broken streetlights — but manual classification is slow, inconsistent, and expensive. Our platform uses Amazon Nova's vision AI to instantly analyze photos, classify issues, assess severity, and suggest actions — saving cities hours of manual work every week.

---

## 🤖 How Amazon Nova Powers This

We use **Amazon Nova 2 Lite** (via Amazon Bedrock) as the core vision intelligence:

- **Image Understanding** — Nova analyzes uploaded photos and identifies city infrastructure problems
- **Rich Analysis** — Nova returns not just a label, but severity, priority score, detailed description, suggested action, estimated risk, and category tags
- **Natural Language** — Nova describes what it sees in human-readable language that city authorities can act on immediately

### Sample Nova Output:
```json
{
  "issue": "garbage_overflow",
  "confidence": 0.95,
  "detected_object": "pile of waste",
  "severity": "high",
  "priority_score": 9,
  "description": "Large pile of waste including plastic bags and bottles overflowing onto roadside, posing significant environmental and public health hazard.",
  "suggested_action": "Immediate waste collection and proper disposal required.",
  "estimated_risk": "High risk of disease spread and environmental pollution.",
  "tags": ["sanitation", "public_hazard", "environmental"]
}
```

---

## 🏗️ Architecture
```
citizen uploads photo
        │
        ▼
  [Frontend - React]
        │
        ▼
  [AI Model - FastAPI :8001]
        │
        ▼
  [Amazon Nova 2 Lite via Bedrock]
        │
        ▼
  rich JSON analysis
        │
        ▼
  [Backend - FastAPI :8000]
        │
        ▼
  [Database - stores complaint]
        │
        ▼
  [Dashboard - city authorities]
```

---

## 🔍 Detected Issue Types

| Issue | Description | Example Tags |
|-------|-------------|--------------|
| 🕳️ Pothole | Road surface damage | road_safety, traffic_risk |
| 🗑️ Garbage Overflow | Overflowing bins, litter | sanitation, public_hazard |
| 💡 Broken Streetlight | Damaged/non-functioning lights | lighting, pedestrian_risk |

---

## 👥 Team

| Name | Role |
|------|------|
| **Gummala Divya** | AI Model — Amazon Nova Integration |
| **Manya Katayayan** | Backend — FastAPI & Database |
| **Vyom Misra** | Frontend — React Dashboard |

---

## 🚀 How to Run

### AI Model (Port 8001)
```bash
cd ai-model
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn boto3 python-multipart python-dotenv
cp .env.example .env  # Add your AWS credentials
uvicorn main:app --port 8001
```

### Backend (Port 8000)
```bash
cd backend
# Follow backend README
```

### Frontend
```bash
cd frontend
# Follow frontend README
```

---

## 🔗 API Reference

### AI Detection Endpoint
```
POST http://localhost:8001/detect
Content-Type: multipart/form-data
Body: file = <image>

Response:
{
  "issue": "pothole",
  "confidence": 0.95,
  "severity": "high",
  "priority_score": 9,
  "description": "...",
  "suggested_action": "...",
  "estimated_risk": "...",
  "tags": [...]
}
```

---

## 🌟 Key Features

- **Instant AI Detection** — Results in under 3 seconds
- **Priority Scoring** — 1-10 urgency score for city authorities
- **Rich Analysis** — Not just a label — full actionable intelligence
- **3 Issue Types** — Potholes, Garbage, Streetlights
- **REST API** — Easy integration with any frontend or backend

---

## 🏆 Built With

- **Amazon Nova 2 Lite** — Vision AI via Amazon Bedrock
- **Python + FastAPI** — AI model server
- **React.js** — Frontend dashboard
- **AWS Bedrock** — AI infrastructure

---

*Built with ❤️ for the Amazon Nova Hackathon 2026*
>>>>>>> 12a650693235b934f9aab9e3085e8ad9f5db7cd3
