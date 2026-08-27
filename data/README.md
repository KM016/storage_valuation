# Data

## Observed Henry Hub prices

`henry_hub_monthly.csv` is a fixed snapshot of the Henry Hub Natural Gas Spot Price series (`MHHNGSP`).

- Original source: U.S. Energy Information Administration (EIA)
- Downloaded from: https://fred.stlouisfed.org/graph/fredgraph.csv?id=MHHNGSP
- Retrieved: 23 August 2026
- Frequency: monthly
- Units: dollars per million British thermal units (`$/MMBtu`)
- Coverage: January 1997 to July 2026
- SHA-256: `edef0a517b3a8560b47c2f55756d9cc4120c18a53221a49d759014044afc0e93`

FRED republishes this EIA series. The original EIA table is available at https://www.eia.gov/dnav/ng/hist/rngwhhdm.htm. This file supplies the observed prices used to evaluate each forecast.

## Archived EIA forecasts and market conditions

`eia_steo_july_vintages.csv` is a fixed extraction from the July Short-Term Energy Outlook (STEO) workbooks published from 2017 to 2026. The archive is available at https://www.eia.gov/outlooks/steo/outlook.php.

Each row represents one month within one July vintage. Every vintage contains 72 months, running from January four years before the vintage to December of the following year. This gives 54 historical or estimated months followed by 18 forecast months. The full file contains 720 rows.

When the vintages are combined using the latest information available at each forecast year, the earliest modelling observation is January 2013.

The included series are:

| CSV column | STEO series | Meaning | Units |
| --- | --- | --- | --- |
| `price` | `NGHHUUS` | Henry Hub spot price | `$/MMBtu` |
| `storage` | `NGWGPUS` | End-of-period U.S. working gas inventory | billion cubic feet |
| `hdd` | `ZWHDPUS` | U.S. average heating degree days | degree days |
| `hdd_normal` | `ZWHD_US_10YR` | Prior ten-year average heating degree days | degree days |
| `cdd` | `ZWCDPUS` | U.S. average cooling degree days | degree days |
| `cdd_normal` | `ZWCD_US_10YR` | Prior ten-year average cooling degree days | degree days |

EIA calculates the national degree-day series as population-weighted averages of state data published by the National Oceanic and Atmospheric Administration. The ten-year averages are the weather reference values published in the same vintage.

The `last_historical_month` field comes from the `Dates` sheet in each workbook. EIA describes the break between history and estimates or forecasts as approximate, so rows up to this date are labelled `history_or_estimate`. Rows after it are labelled `forecast`.

For a forecast covering August of year Y to July of year Y+1, the matching July vintage was publicly released before 1 August. Its future storage and weather values were therefore available when the forecast would have been made. The archived `price` forecast is retained as an external EIA benchmark and is not used as an explanatory variable when predicting the same price series.

- Retrieved: 24 August 2026
- Coverage: July vintages from 2017 to 2026
- Rows: 720, with 72 rows per vintage
- SHA-256: `3184b0cd61b5cdb63138b46c38a3cbd7f17d12073f41168726f295e1daca041f`

`eia_steo_vintage_manifest.csv` records the release date, coverage, original workbook URL and SHA-256 checksum for every source workbook. The archived workbooks are not stored in the repository because the extracted data and pinned checksums are sufficient to reproduce and verify the snapshot.

- Retrieved: 24 August 2026
- Rows: 10, with one row per vintage
- SHA-256: `10de16892b9b45a4437d3949c4a377a2e03ffa6aa32e719a777d0bdc12c05bbb`

## Reproducing the STEO snapshot

From the repository root, run:

```bash
python extract_steo_vintages.py
```

The script downloads every official workbook listed in the manifest, checks its SHA-256 checksum, locates each required row using the EIA series code and rebuilds `eia_steo_july_vintages.csv`. It also checks the date coverage, historical cutoff, row counts, duplicate keys and missing values before writing the file. The downloaded workbooks are held in a temporary directory and are removed when the extraction finishes.

The extraction reads the monthly dates from row 11 of each workbook's `Dates` sheet and the final historical or estimated month from `Dates!D7`. Series rows are found by code rather than by fixed row number because EIA changed parts of the workbook layout in 2024.
