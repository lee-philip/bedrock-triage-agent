# Price Tolerance Break

Trade price deviates from the established tolerance range for the asset.

## Symptoms

- Trade validation fails with "price outside tolerance" error
- Margin call or additional collateral required
- Risk dashboard shows anomalous trade price
- Manual approval workflow triggered

## Likely Root Causes

1. Market gap during order execution (price moved significantly)
2. Stale price data used for validation
3. Incorrect tolerance parameters configured for the asset
4. Data entry error in trade ticket

## Checks

- Compare trade price to market reference price at trade time
- Review tolerance parameters for this asset class
- Verify timestamp alignment between trade and market data
- Check if multiple trades in same session have similar deviations

## Fix Steps

1. Identify trade and asset class
2. Retrieve market reference price for trade timestamp
3. Calculate actual deviation percentage
4. If within acceptable range, override tolerance check
5. If significant deviation, route to Risk team for manual approval
6. Document approval and update risk metrics

## Escalation

If deviation exceeds 5%, escalate to Head of Trading. If market data itself appears incorrect, engage Data Quality team and notify Risk.
