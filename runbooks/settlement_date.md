# Settlement Date Mismatch

Trade settlement date does not match the agreed date between buyer and seller.

## Symptoms

- Settlement fails on expected date
- Counterparty confirms different settlement date
- Early settlement (trade settles before agreed date)
- Late settlement with counterparty complaint

## Likely Root Causes

1. Different calendar conventions (business day vs. settlement day)
2. Holiday calendar mismatch between counterparties
3. Manual entry error on trade ticket
4. Amendment to trade not reflected in settlement system

## Checks

- Compare trade ticket settlement date vs. settlement system date
- Review holiday calendars for both counterparties
- Check trade amendment history
- Verify calendar conventions agreed in ISDA documentation

## Fix Steps

1. Identify trade and settlement date discrepancy
2. Determine correct settlement date per trade agreement
3. Update settlement system with correct date
4. Notify counterparty of corrected date
5. If settlement already occurred, process adjustment

## Escalation

If trade is a structured product with complex settlement terms, escalate to Legal. If counterparty disagrees on correct date, engage Dispute Resolution.
