# Bedrock Guardrails Setup

## Creating the Guardrail

1. Go to the AWS Bedrock Console: https://console.aws.amazon.com/bedrock
2. Navigate to **Guardrails** in the left sidebar
3. Click **Create guardrail**

## Configuration

Give the guardrail the name **triage-guardrail** and configure the following policies:

### 1. Denied Topics Policy

Create a denied topic that blocks investment advice:

- **Topic name:** Investment advice
- **Description:** Recommending buying, selling or holding securities, or predicting prices
- **Sample phrases:**
  - "Buy 100 shares of Apple immediately for short-term gains"
  - "Sell your crypto holdings now before the market drops"
  - "This stock will be up 20% next month, hold it"

### 2. Sensitive Information Policy (PII Masking)

Enable masking for these entity types:

- **Name** - Set to **MASK**
- **Email** - Set to **MASK**
- **Phone** - Set to **MASK**
- **US Social Security Number** - Set to **MASK**

### 3. Regex Filter

Add a regex filter to mask account numbers:

- **Pattern:** `ACCT-\d{8}`
- **Replace with:** `ACCT-[redacted]`

### 4. Content Filters

Enable moderate content filters:

- **Sexual:** Moderate
- **Violence:** Moderate
- **Profanity:** Moderate

## Versioning

After saving the guardrail configuration:

1. Click **Create version**
2. Give it a version description (e.g., "Initial triage guardrail configuration")
3. Note the **Guardrail ID** and **Version** - you'll need these for your application

## Environment Variables

Add these to your `.env` file:

```
GUARDRAIL_ID=<your-guardrail-id>
GUARDRAIL_VERSION=<your-guardrail-version>
```

## Using in Code

The guardrail is applied via the `apply_guardrail` API with `source="INPUT"` (on incoming exception text) and `source="OUTPUT"` (on draft fixes).
