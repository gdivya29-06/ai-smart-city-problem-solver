from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import shutil, os, uuid
from detect import detect_city_issue

app = FastAPI(title="AI Smart City Problem Solver")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/")
def root():
    return {"message": "AI Smart City API is running 🚀"}

@app.post("/detect")
async def detect_issue(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are accepted.")

    file_ext = file.filename.split(".")[-1]
    temp_filename = f"{UPLOAD_DIR}/{uuid.uuid4()}.{file_ext}"

    with open(temp_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        result = detect_city_issue(temp_filename)
    finally:
        os.remove(temp_filename)

    return result
