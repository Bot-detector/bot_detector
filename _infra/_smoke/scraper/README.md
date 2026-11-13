# scraper fetch smoke test

Fetch-level check: the real `osrs_hs_api` brick against the live Jagex
hiscores, inside the `hiscore_scraper` image. Needs outbound internet
only — no kafka, mysql or proxies. The pipeline-level smoke (real
Webshare proxies, kafka, mysql) is future work; it needs
`PROXY_API_KEY` in `.env`.

Run from the repo root:

```sh
make smoke-scraper
```

The target builds the prod image and runs the smoke runner in the
compose network. Exit 0 means every check passed.

## What is checked

1. the default client timeout is the 10s total / 5s connect bound
2. a real player fetch returns Ok and passes the full-skill-set
   `PlayerStats` validator against the live payload shape
3. a missing player maps to `Err(PlayerDoesNotExist)` (Jagex 404)
4. a fetch against a blackhole address returns Err within the timeout
   budget — real timers, not simulated ones

## Knobs (env)

none.
