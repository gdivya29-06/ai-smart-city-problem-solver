from dotenv import load_dotenv
load_dotenv()
import boto3
import base64
import json
import sys
from pathlib import Path

# ─── AWS Configuration ───────────────────────────────────────────────────────
import os
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION = "us-east-1"

client = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

def detect_city_issue(image_path: str) -> dict:
    # Read and encode image
    image_data = Path(image_path).read_bytes()
    base64_image = base64.standard_b64encode(image_data).decode("utf-8")

    # Detect image type
    ext = Path(image_path).suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp"
    }
    media_type = media_type_map.get(ext, "image/jpeg")

    # Build request for Amazon Nova
    request_body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": media_type.split("/")[1],
                            "source": {
                                "bytes": base64_image
                            }
                        }
                    },
                    {
                        "text": """You are an expert AI system for detecting and analyzing city infrastructure problems from images for a smart city management platform.

Analyze this image carefully and identify if it contains any of these city issues:
1. pothole - damaged road surface with holes or cracks
2. garbage_overflow - overflowing bins, litter, waste on streets
3. broken_streetlight - damaged, broken or non-functioning street lights or lamp posts

Respond ONLY in this exact JSON format with no extra text or markdown:
{
  "issue": "pothole" or "garbage_overflow" or "broken_streetlight" or "unknown",
  "confidence": a number between 0.0 and 1.0,
  "detected_object": short description of what you see in 5-8 words,
  "status": "detected" or "no_city_issue_found",
  "severity": "low" or "medium" or "high" or "critical",
  "description": "2-3 sentence detailed description of the problem visible in the image",
  "suggested_action": "specific recommended action for city authorities to fix this",
  "estimated_risk": "brief note on risk to public safety if left unattended"
}"""
                    }
                ]
            }
        ],
        "inferenceConfig": {
            "maxTokens": 256,
            "temperature": 0.1
        }
    }

    # Call Amazon Nova 2 Lite
    response = client.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        body=json.dumps(request_body),
        contentType="application/json",
        accept="application/json"
    )

    # Parse response
    response_body = json.loads(response["body"].read())
    response_text = response_body["output"]["message"]["content"][0]["text"].strip()

    # Clean up markdown if present
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    result = json.loads(response_text)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python detect.py <image_path>")
        sys.exit(1)
    image_path = sys.argv[1]
    result = detect_city_issue(image_path)
    print(json.dumps(result, indent=2))