import boto3
import json

session = boto3.session.Session(profile_name='bedrock-triage')
client = session.client('bedrock-runtime', region_name='us-east-2')

input_text = "His SSN is 123-45-6789. Contact John Smith at john.smith@example.com or (555) 123-4567."

response = client.apply_guardrail(
    guardrailIdentifier='kpbvstqxc7l5',
    guardrailVersion='2',
    source='INPUT',
    content=[{'text': {'text': input_text}}],
)

with open('guardrail_raw_response.json', 'w') as f:
    json.dump(response, f, indent=2)

print("Written to guardrail_raw_response.json")