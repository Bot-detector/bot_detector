import { useCallback, useEffect, useRef, useState } from "react";
import {
  clearTokens,
  handleCallback,
  logout as discordLogout,
  startLogin,
  validAccessToken,
} from "./discordAuth";

const MAX_LINES = 100;
const ANON_STATES = ["anonymous", "checking...", "unknown"];

function pretty(data) {
  try {
    return JSON.stringify(JSON.parse(data), null, 2);
  } catch {
    return data;
  }
}

async function fetchIdentity(token) {
  const headers = token ? { "X-API-Key": token } : {};
  const res = await fetch("/me", { headers });
  if (!res.ok) throw new Error(`/me ${res.status}`);
  return res.json();
}

async function fetchTopics() {
  const res = await fetch("/firehose/topics");
  if (!res.ok) throw new Error(`/firehose/topics ${res.status}`);
  return res.json();
}

const btn =
  "rounded border border-neutral-600 bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-40 disabled:cursor-not-allowed";

export default function App() {
  const [identity, setIdentity] = useState({
    user: "checking...",
    allowed: null,
    scopes: [],
  });
  const [topics, setTopics] = useState([]);
  const [topic, setTopic] = useState("");
  const [token, setToken] = useState("");
  const [status, setStatus] = useState("disconnected");
  const [messages, setMessages] = useState([]);
  const [count, setCount] = useState(0);
  const wsRef = useRef(null);
  const callbackHandled = useRef(false);

  const connected = status === "connected";
  const bad = status.startsWith("closed") || status === "error";
  const loggedIn = !ANON_STATES.includes(identity.user) && identity.allowed !== false;

  const refreshIdentity = useCallback(async () => {
    try {
      const accessToken = await validAccessToken();
      setIdentity(await fetchIdentity(accessToken));
    } catch {
      setIdentity({ user: "unknown", allowed: null, scopes: [] });
    }
  }, []);

  useEffect(() => {
    if (callbackHandled.current) return;
    callbackHandled.current = true;

    const url = new URL(window.location.href);
    if (url.pathname === "/callback") {
      handleCallback()
        .then(() => {
          window.history.replaceState({}, "", "/");
          return refreshIdentity();
        })
        .catch((e) => setStatus(`login failed: ${e.message}`));
    } else {
      refreshIdentity();
    }

    fetchTopics()
      .then((list) => {
        setTopics(list);
        setTopic((current) => current || list[0] || "");
      })
      .catch((e) => setStatus(`topics unavailable: ${e.message}`));
  }, [refreshIdentity]);

  // revalidate the token when the tab regains focus; the access token
  // may have been refreshed or revoked elsewhere
  useEffect(() => {
    const onFocus = () => refreshIdentity();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshIdentity]);

  function disconnect() {
    if (wsRef.current) wsRef.current.close();
  }

  async function connect({ anonymous = false, manual = false } = {}) {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;
    if (!topic) {
      setStatus("no topic selected");
      return;
    }

    const params = new URLSearchParams();
    if (anonymous) {
      params.set("anonymous", "1");
      setIdentity({ user: "anonymous", allowed: true, scopes: [] });
    } else {
      const accessToken = manual ? token.trim() : await validAccessToken();
      if (accessToken) params.set("token", accessToken);
    }

    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    const query = params.size ? `?${params}` : "";
    const url = `${proto}${location.host}/firehose/${topic}${query}`;
    setStatus("connecting...");

    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => setStatus("connected");
    ws.onclose = (e) => {
      setStatus(`closed (code=${e.code}${e.reason ? " " + e.reason : ""})`);
      wsRef.current = null;
      refreshIdentity();
    };
    ws.onerror = () => setStatus("error");
    ws.onmessage = (e) => {
      setCount((c) => c + 1);
      setMessages((prev) =>
        [{ at: new Date().toISOString(), data: pretty(e.data) }, ...prev].slice(0, MAX_LINES),
      );
    };
  }

  async function doLogout() {
    await discordLogout();
    setToken("");
    refreshIdentity();
  }

  function dropStoredToken() {
    clearTokens();
    refreshIdentity();
  }

  return (
    <main className="min-h-screen bg-neutral-900 p-8 font-mono text-sm text-neutral-200">
      <h1 className="mb-6 text-lg font-bold">Bot Detector Firehose</h1>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span>
          identity: <strong>{identity.user}</strong>
          {identity.allowed === false && <em className="text-red-400"> (403 - token not allowed)</em>}
        </span>
        {identity.user === "anonymous" && identity.allowed !== false && (
          <button className={btn} onClick={() => startLogin().catch((e) => setStatus(e.message))}>
            login with discord
          </button>
        )}
        {loggedIn && (
          <button className={btn} onClick={doLogout}>
            logout
          </button>
        )}
      </div>

      {loggedIn && identity.scopes.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          scopes:
          {identity.scopes.map((s) => (
            <span key={s} className="rounded bg-neutral-800 px-2 py-0.5 text-xs">
              {s}
            </span>
          ))}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2">
          topic:
          <select
            className="rounded border border-neutral-600 bg-neutral-800 px-2 py-1.5"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={connected}
          >
            {topics.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          token:
          <input
            className="w-80 rounded border border-neutral-600 bg-neutral-800 px-2 py-1.5"
            type="password"
            placeholder="discord access token (optional)"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            disabled={connected}
          />
        </label>
      </div>

      <div className="mb-3 flex flex-wrap gap-3">
        <button className={btn} onClick={() => connect({ manual: true })} disabled={connected}>
          connect with token
        </button>
        <button className={btn} onClick={() => connect()} disabled={connected}>
          connect with login
        </button>
        <button className={btn} onClick={() => connect({ anonymous: true })} disabled={connected}>
          connect anonymous
        </button>
        <button className={btn} onClick={disconnect} disabled={!connected}>
          disconnect
        </button>
        <button className={btn} onClick={dropStoredToken} disabled={connected}>
          drop stored token
        </button>
        <button
          className={btn}
          onClick={() => {
            setMessages([]);
            setCount(0);
          }}
        >
          clear
        </button>
      </div>

      <div className="mb-4 flex items-center gap-2">
        status:{" "}
        <strong className={connected ? "text-green-400" : bad ? "text-red-400" : ""}>{status}</strong>
        <span className="text-neutral-500">|</span> messages: <strong>{count}</strong>
      </div>

      <ul>
        {messages.map((m, i) => (
          <li key={i} className="border-b border-neutral-800 py-2">
            <div className="text-xs text-neutral-500">{m.at}</div>
            <pre className="mt-1 whitespace-pre-wrap break-all">{m.data}</pre>
          </li>
        ))}
      </ul>
    </main>
  );
}
