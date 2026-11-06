import os
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

load_dotenv()

AWS_PROFILE = os.environ.get("AWS_PROFILE", "bedrock-triage")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")

if not BEDROCK_MODEL_ID:
    raise EnvironmentError("BEDROCK_MODEL_ID not set in .env or environment")

session = boto3.Session(profile_name=AWS_PROFILE)
client = session.client("bedrock-runtime", region_name=AWS_REGION)

system = [{"text": "You are a concise operations assistant."}]
user_message = [{"text": "In two sentences, what is a failed trade settlement?"}]

response = client.converse(
    modelId=BEDROCK_MODEL_ID,
    system=system,
    messages=[
        {"role": "user", "content": user_message}
    ],
    inferenceConfig={
        "maxTokens": 300,
        "temperature": 0.2
    }
)

text = response["output"]["message"]["content"][0]["text"]
usage = response.get("usage", {})
input_tokens = usage.get("inputTokens", 0)
output_tokens = usage.get("outputTokens", 0)
latency = response.get("metrics", {}).get("latencyMs", 0)

print(f"Model: {BEDROCK_MODEL_ID}")
print(f"Input tokens: {input_tokens}")
print(f"Output tokens: {output_tokens}")
print(f"Latency: {latency}ms")
print(f"\n{text}")