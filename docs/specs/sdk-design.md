# CAVEMAN SDK DESIGN DOC — PYTHON ASYNC API CLIENT

## GOAL
make simple api sdk

- aiohttp for http
- AsyncLimiter for rate limit
- retry decorator for retry
- endpoint decides how http status works
- no service layer
- no api client layer

---

# BIG IDEA

api call =

| rate limit gate |
→ http request |
→ status handling (manual OR raise_for_status) |
→ retry if needed |
→ return data |

---

# COMPONENTS

## 1. SDK CLASS (ONLY ONE)

holds:

- base_url
- aiohttp session
- AsyncLimiter

```python
class OsrsBotDetectorApi:
    def __init__(self, base_url, session, limiter):
        self.base_url = base_url
        self.session = session
        self.limiter = limiter
```

---

## 2. RETRY DECORATOR (ONLY RETRY LOGIC)

retry only for transient errors

```python
@retry(attempts=3, exceptions=(aiohttp.ClientError,))
```

RULES:
- retry network fail
- retry 5xx (optional if raised)
- DO NOT retry business errors like 404

---

## 3. RATE LIMIT (INSTANCE BASED)

limiter passed in constructor

```python
async with self.limiter:
    ...
```

WHY:
- per client control
- no global state
- easy test

---

# 4. HTTP HANDLING MODES

TWO MODES EXIST

---

## MODE 1: STRICT (DEFAULT)

failure = exception

```python
res.raise_for_status()
```

FLOW:
- 404 → exception
- 500 → exception
- 200 → return json

---

## MODE 2: MANUAL STATUS (IMPORTANT ADDITION)

status = data

```python
if res.status == 404:
    return None
```

FLOW:
- status is meaningful
- sdk interprets it

---

# RULE

endpoint decides http meaning

NOT global rule

---

# 5. EXAMPLE: PLAYER (STRICT MODE)

```python
@retry(attempts=3, exceptions=(aiohttp.ClientError,))
async def get_player(self, player_id):

    async with self.limiter:
        async with self.session.get(self.base_url + "/player/" + player_id) as res:

            res.raise_for_status()

            return await res.json()
```

---

# 6. EXAMPLE: PREDICTION (MANUAL MODE)

404 = not ready, not error

```python
@retry(attempts=2, exceptions=(aiohttp.ClientError,))
async def get_prediction(self, player_name):

    async with self.limiter:
        async with self.session.get(self.base_url + "/prediction/" + player_name) as res:

            if res.status == 404:
                return None

            if res.status >= 500:
                raise RetryableError()

            return await res.json()
```

---

# 7. RATE LIMIT RULE

always wrap request

```python
async with self.limiter:
    async with self.session.get(...)
```

no exceptions

---

# 8. DESIGN RULES

## DO

- keep sdk flat
- limiter per instance
- retry decorator only
- strict OR manual per endpoint
- logic lives in endpoint

---

## DO NOT

- no service layer
- no api client layer
- no global retry system
- no hidden abstraction layers
- no mixing strict + manual in same endpoint

---

# 9. DECISION RULE

ask:

is http error real error?

YES → STRICT MODE

```python
res.raise_for_status()
```

NO → MANUAL MODE

```python
if res.status == ...
```

---

# 10. MENTAL MODEL

```
limiter = traffic control
retry = resilience
endpoint = meaning of api
http status = error OR data
```

---

# 11. SUMMARY

design is:

- simple
- explicit
- async safe
- testable
- scalable

core idea:

endpoint owns meaning of http
