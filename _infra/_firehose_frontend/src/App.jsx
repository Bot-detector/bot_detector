import { useCallback, useEffect, useRef, useState } from "react";
import {
  ENDPOINT_PRESETS,
  loadEndpoint,
  saveEndpoint,
  wsOrigin,
} from "./apiEndpoint";
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

async function fetchIdentity(base, token) {
  const headers = token ? { "X-API-Key": token } : {};
  const res = await fetch(`${base}/me`, { headers });
  if (!res.ok) throw new Error(`/me ${res.status}`);
  return res.json();
}

async function fetchTopics(base) {
  const res = await fetch(`${base}/firehose/topics`);
  if (!res.ok) throw new Error(`/firehose/topics ${res.status}`);
  return res.json();
}

const btn =
  "rounded border border-neutral-600 bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:opacity-40 disabled:cursor-not-allowed";

export default function App() {
  const [identity, setIdentity] = useState({
    user: "checking...",
    allowed: null,
    topics: [],
  });
  const [topics, setTopics] = useState([]);
  const [topic, setTopic] = useState("");
  const [status, setStatus] = useState("disconnected");
  const [messages, setMessages] = useState([]);
  const [count, setCount] = useState(0);
  const [endpoint, setEndpoint] = useState(() => loadEndpoint());
  const [endpointDraft, setEndpointDraft] = useState(endpoint);
  const wsRef = useRef(null);
  const callbackHandled = useRef(false);

  const connected = status === "connected";
  const bad = status.startsWith("closed") || status === "error";
  const loggedIn = !ANON_STATES.includes(identity.user) && identity.allowed !== false;

  const refreshIdentity = useCallback(async () => {
    try {
      const accessToken = await validAccessToken();
      const next = await fetchIdentity(endpoint, accessToken);
      setIdentity(next);
      // keep the selection on a topic the identity may consume
      if (next.allowed && next.user && next.user !== "anonymous") {
        setTopic((current) =>
          next.topics.length && !next.topics.includes(current)
            ? next.topics[0]
            : current,
        );
      }
    } catch {
      setIdentity({ user: "unknown", allowed: null, topics: [] });
    }
  }, [endpoint]);

  const loadTopics = useCallback(async () => {
    try {
      const list = await fetchTopics(endpoint);
      setTopics(list);
      setTopic((current) => current || list[0] || "");
    } catch (e) {
      setStatus(`topics unavailable: ${e.message}`);
    }
  }, [endpoint]);

  // oauth redirect handling; runs once
  useEffect(() => {
    if (callbackHandled.current) return;
    callbackHandled.current = true;

    const url = new URL(window.location.href);
    if (url.pathname !== "/callback") return;
    handleCallback()
      .then(() => {
        window.history.replaceState({}, "", "/");
        refreshIdentity();
      })
      .catch((e) => setStatus(`login failed: ${e.message}`));
  }, []);

  // (re)load identity + topics on mount and whenever the endpoint changes
  useEffect(() => {
    refreshIdentity();
    loadTopics();
  }, [refreshIdentity, loadTopics]);

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

  async function connect({ anonymous = false } = {}) {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;
    if (!topic) {
      setStatus("no topic selected");
      return;
    }

    const params = new URLSearchParams();
    const accessToken = anonymous ? null : await validAccessToken();
    if (accessToken) {
      params.set("token", accessToken);
    } else {
      params.set("anonymous", "1");
      setIdentity({ user: "anonymous", allowed: true, topics });
    }

    const query = params.size ? `?${params}` : "";
    const url = `${wsOrigin(endpoint)}/firehose/${topic}${query}`;
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
    refreshIdentity();
  }

  function dropStoredToken() {
    clearTokens();
    refreshIdentity();
  }

  function commitEndpoint(value) {
    const next = saveEndpoint(value);
    setEndpoint(next);
    setEndpointDraft(next);
    setStatus("disconnected");
  }

  const knownPreset = ENDPOINT_PRESETS.some((p) => p.value === endpoint);
  const selectOptions = knownPreset
    ? ENDPOINT_PRESETS
    : [...ENDPOINT_PRESETS, { label: endpoint, value: endpoint }];

  const endpointControls = (
    <>
      <select
        className="rounded border border-neutral-600 bg-neutral-800 px-2 py-1.5"
        value={endpoint}
        onChange={(e) => commitEndpoint(e.target.value)}
        disabled={connected}
      >
        {selectOptions.map((p) => (
          <option key={p.value || "proxy"} value={p.value}>
            {p.label}
          </option>
        ))}
      </select>
      <input
        className="w-72 rounded border border-neutral-600 bg-neutral-800 px-2 py-1.5 disabled:opacity-40"
        value={endpointDraft}
        placeholder="https://firehose.example.com"
        onChange={(e) => setEndpointDraft(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && commitEndpoint(endpointDraft)}
        onBlur={() => commitEndpoint(endpointDraft)}
        disabled={connected}
      />
    </>
  );

  return (
    <main className="min-h-screen bg-neutral-900 p-8 font-mono text-sm text-neutral-200">
      <h1 className="mb-6 text-lg font-bold">Bot Detector Firehose</h1>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span>
          identity: <strong>{identity.user ?? "invalid token"}</strong>
          {identity.allowed === false && (
            <em className="text-red-400">
              {identity.user ? " (not allowlisted)" : " (invalid token)"}
            </em>
          )}
        </span>
        {!loggedIn &&
          (identity.allowed !== false || identity.user == null) && (
            <button
              className={btn}
              onClick={() => startLogin().catch((e) => setStatus(e.message))}
            >
              login with discord
            </button>
          )}
        {loggedIn && (
          <button className={btn} onClick={doLogout}>
            logout
          </button>
        )}
      </div>

      {loggedIn && identity.topics.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          topics:
          {identity.topics.map((t) => (
            <span key={t} className="rounded bg-neutral-800 px-2 py-0.5 text-xs">
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2">
          endpoint:
          {endpointControls}
        </label>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2">
          topic:
          <select
            className="rounded border border-neutral-600 bg-neutral-800 px-2 py-1.5"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={connected}
          >
            {topics.map((t) => {
              const keyedOnly = loggedIn && !identity.topics.includes(t);
              return (
                <option key={t} value={t} disabled={keyedOnly}>
                  {t}
                  {keyedOnly ? " (anonymous only)" : ""}
                </option>
              );
            })}
          </select>
        </label>
      </div>

      <div className="mb-3 flex flex-wrap gap-3">
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
