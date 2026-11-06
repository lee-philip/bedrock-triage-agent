# SSI Mismatch

Settlement instruction mismatch between trade order and counterparty's bank account details.

## Symptoms

- Settlement fails with "IBAN not recognized" or "account not found"
- Trade confirmation shows different bank details than order entry
- Funds sent to wrong account or returned after a delay
- Manual reconciliation notices from counterparty operations

## Likely Root Causes

1. Counterparty changed bank account without notifying internal settlement team
2. Data entry error in order entry system
3. Stale SSI data in legacy settlement database
4. Different settlement instructions used for different trade sizes or regions

## Checks

- Compare IBAN in trade order vs. counterparty SSI master record
- Check counterparty portal for updated SSI details
- Verify trade size and region to ensure correct SSI profile was applied
- Review settlement history for recurring mismatch with this counterparty

## Fix Steps

1. Retrieve current trade order and counterparty SSI from order entry system
2. Verify counterparty's current bank details via counterparty portal or direct contact
3. Update trade settlement instructions with correct IBAN and account name
4. Reconcile with counterparty confirmation to ensure both sides match
5. If funds already sent to wrong account, initiate recall procedure

## Escalation

If counterparty portal is down and direct contact fails, escalate to Counterparty Relations team. If IBAN belongs to a different company, engage Legal and notify Internal Audit of potential fraud.
