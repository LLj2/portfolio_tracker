# Data Contracts

# Holdings CSV (non-Degiro)
account,name,isin_or_symbol,asset_class,currency,quantity,book_cost

- asset_class ∈ {Equity, Bonds, Fund, Crypto, Commodity, Lending, Cash, Other}
- Crypto code:  CRYPTO:BTC, CRYPTO:ETH, ...
- Lending code: LEND:<custom>
- quantity is required
- book_cost is OPTIONAL (total acquisition cost in account currency). Leave blank if unknown.


## NAV CSV (Funds/Lending)
`date,isin_or_symbol,nav,currency`  (YYYY-MM-DD)
