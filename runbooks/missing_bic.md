# Missing Counterparty BIC

Trade cannot be processed because the SWIFT Bank Identifier Code (BIC) is absent from the settlement instruction.

## Symptoms

- Trade rejected by SWIFT network with "BIC required" message
- Settlement delay while waiting for manual intervention
- Payment cannot be routed internationally without BIC
- Internal trade validation fails

## Likely Root Causes

1. Legacy trade record from before BIC was mandatory
2. New counterparty onboarded without complete SWIFT information
3. Data migration error from old system
4. Manual entry error on order entry form

## Checks

- Verify counterparty master record in CRM for BIC value
- Check if trade is domestic (BIC may be optional)
- Review trade timestamp — is this a legacy record?
- Search counterparty portal for complete SWIFT details

## Fix Steps

1. Identify counterparty from trade record
2. Retrieve BIC from counterparty master record or portal
3. Update trade settlement instruction with BIC
4. If counterparty is new and BIC unknown, contact counterparty directly
5. Revalidate trade and resubmit

## Escalation

If counterparty is new and no BIC can be found after 24 hours, escalate to Onboarding team. If BIC exists but trade still fails, engage SWIFT support via the Payments Ops team.
