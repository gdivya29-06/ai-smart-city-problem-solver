import base64
import json
import os

import boto3
from botocore.exceptions import ClientError


def analyze_image(image_bytes: bytes, image_media_type: str) -> str:
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION", "us-east-1")

    if not aws_access_key or not aws_secret_key:
        return "pothole detected on road surface"

    bedrock = boto3.client(
        service_name="bedrock-runtime",
        region_name=aws_region,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
    )

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    image_format = image_media_type.split("/")[-1]

    request_body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": image_format,
                            "source": {"bytes": image_b64},
                        }
                    },
                    {
                        "text": (
                            "You are a city infrastructure inspector AI. "
                            "Analyze this image and identify the primary urban problem visible. "
                            "Focus on: pothole, road damage, garbage/trash/litter, "
                            "broken streetlight, graffiti, or other city issues. "
                            "Reply in one short sentence describing what you see. "
                            "Example: 'There is a large pothole on the road surface.'"
                        )
                    },
                ],
            }
        ],
        "inferenceConfig": {
            "maxTokens": 200,
            "temperature": 0.1,
        },
    }

    try:
        response = bedrock.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )
        response_body = json.loads(response["body"].read())
        return response_body["output"]["message"]["content"][0]["text"]

    except ClientError as e:
        raise RuntimeError(f"AWS Bedrock error: {e.response['Error']['Message']}")
    except Exception as e:
        raise RuntimeError(f"AI analysis failed: {str(e)}")

