# firehose frontend

Manual test + showcase client for the firehose websocket. Not a brick and
not a container: plain React (vite + tailwind), run with npm on the host,
talking to the firehose API.

## Run

```sh
npm install
npm run dev
```

Open http://localhost:5173. Default proxy target is
http://localhost:5000 (a locally running firehose API). Override with:

```sh
# against the compose-dev stack (firehose mapped to localhost:8000)
FIREHOSE_URL=http://localhost:8000 npm run dev

# against any other api
FIREHOSE_URL=http://host:port npm run dev
```

The vite dev server proxies `/firehose`, `/login` and `/me` to the API,
so the app is same-origin (cookies just work, no CORS setup).

## Flows

- **anonymous** – connect without a credential, shared consumer group
- **discord login** – `/login` -> discord -> `/login/callback` sets the
  `firehose_api_key` cookie and redirects to `/me`; switch back to this
  tab and it picks up the identity
- **token** – paste a discord access token (sent as the
  `firehose_api_key_manual` cookie), or leave empty to use the login
  cookie
