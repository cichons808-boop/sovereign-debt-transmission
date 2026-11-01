# Observation contract

The schema is enumerated in `schema.json`. Every silver row contains the
provider, dataset, stable series identifier, provider geography, ISO3 mapping,
native period and frequency, value, native units, economic dimensions,
observation attributes, retrieval vintage, original SHA256 and source URL.

1. The within-partition key is `(series_id, period)`; duplicate observations
   block publication. Provider, dataset and all economic dimensions enter the
   series identity. Source IDs remain separate across providers and releases.
2. The primary geography is the original reference area. ISO3 maps countries
   and territories; aggregates have a separate flag. Unknown geographies remain
   unknown, rather than being forced into either classification. Current World
   Bank income/region classifications are labeled as current metadata.
3. Annual values retain annual periods. Quarterly, monthly, daily and exact
   monetary-event timestamps retain their observed granularity. No frequency
   conversion or interpolation happens in the source-normalization layer.
4. Missing values stay missing and zeros stay zero. A suppressed value is not
   reconstructed. BIS metadata-only series rows without periods are retained
   in raw files and do not become observations. A numeric value without a
   period is an error.
5. `value` stays in the source's reported numeric representation. When
   `unit_multiplier` is known, a compatible amount in base units is
   `value * 10**unit_multiplier`. Missing multipliers are not assumed to be zero.
   Native unit codes are kept even when their labels are in the raw DSD.
6. IMF's current API returns actual-unit observation values while `SCALE`
   controls display scaling. `SCALE` remains in attributes; it is not applied
   again to the value. Explicit units in provider labels can be read into the
   unit field; unresolved units remain null and are counted in coverage reports.
7. Creditor residence, creditor sector, debt denomination, issuer sector,
   instrument coverage, consolidation, valuation and original/remaining
   maturity are independent dimensions. They cannot be silently substituted.
   Gross/net, central/general government, budgetary/public sector, nominal/
   market value, securities/all-debt and stocks/flows remain distinguishable.
8. Latest revised historical data are not automatically point-in-time data.
   `retrieved_at` measures acquisition, `source_updated` is the provider update
   field, and `publication_date` is populated only when explicitly available.
   A filename release date is labeled as such in attributes. A historical
   backtest must use a verified archived release or its actual availability.
9. `is_estimate` uses IMF's latest-actual-year field when provided. Years after
   that threshold can be staff estimates even when they are in the past.
   `is_forecast` remains unknown unless the source explicitly identifies a
   forecast; estimates are not relabeled as forecasts by calendar arithmetic.
10. Event-window price changes, raw surprises, orthogonalized surprises and
    monetary/information decompositions keep distinct variables and source
    identities. BDY's `DEU` denotes the euro-area policy issuer; its normalized
    reference area is `U2`, while `original_iso3=DEU` remains in attributes.
11. The monthly NBP convention is not imposed on daily observations. Published
    exchange rates and historical currency denominations keep their original
    conventions. USMPD retains precise event timestamps and event types;
    EA-MPD retains separate event windows and their documented bps/percent units.
12. Quality flags and provider failures are part of the evidence. A request with
    no rows does not increase data coverage. Country coverage requires a
    nonmissing value. Successful transfer counts are separate from normalized
    observations and unique underlying economic information.

## Derived refinancing view

For the BIS nominal-value debt-security portfolio, the construction uses
original short debt `S`, originally long debt due within one year `LS`, and the
same portfolio's total `T`:

\[
\text{refinance share}_{it}=\frac{S_{it}+LS_{it}}{T_{it}}.
\]

All selections, scales, sectors and valuations must match. A missing numerator
component prevents a ratio. Totals must be positive. Shares outside the
documented rounding tolerance are flagged for review. The result does not
identify the joint creditor-by-remaining-maturity allocation.

## Validation boundaries

The test suite covers native periods, aggregate/country mapping, preservation
of zeros and missingness, labeled BIS codes, distinct ECB provider dimensions,
World Bank pagination, IMF actual-unit/display-scale separation, estimate
flags, duplicate rejection and concurrent queue integrity. Live runs additionally
verify original/Parquet SHA256, schema and row counts. Scientific comparability,
release timing and causal identification still require a research-specific
sample definition.
