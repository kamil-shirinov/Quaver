# Data

## French 10 industry portfolios

Source: Kenneth R. French Data Library, "10 Industry Portfolios", CSV version:
https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Industry_Portfolios_CSV.zip

The file says it was created from the 202609 CRSP database. The table used is
"Average Value Weighted Returns -- Monthly": 1203 months, 1926-07 to 2026-09, ten industries,
returns in percent.

Downloaded once on 2026-11-06 into `data/raw/`. The SHA-256 of the zip and of the CSV are pinned in
[`pins.json`](pins.json). `quaver.data.load_french10` hashes the CSV and refuses it if the hash
differs from the pin, so no other file can be loaded in its place. Run `uv run quaver data-check` to
verify the local copy.

## Why the file is not committed

The file carries a copyright line (Eugene F. Fama and Kenneth R. French) and its terms do not clearly
allow redistribution. `data/raw/` is gitignored; only the pin is committed. CI never reads
`data/raw/`.

## Getting the file again

A later download will not match the pin. French revises the file as CRSP data is restated and as
new months are added, so its hash changes. To reproduce the pinned numbers, obtain the exact file
that was downloaded on the date above; a fresh download is a different vintage and needs a new pin
and, for any pre-registered test, a dated amendment.
