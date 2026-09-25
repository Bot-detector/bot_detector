import { useCallback, useEffect, useRef, useState } from "react";

const MANUAL_COOKIE = "firehose_api_key_manual";
const MAX_LINES = 100;

function setManualCookie(token) {
  if (token) {
    document.cookie = `${MANUAL_COOKIE}=${encodeURIComponent(token)}; path=/; max-age=604800; samesite=lax`;
  } else {
    // drop the override so the login cookie applies again
    document.cookie = `${MANUAL_COOKIE}=; path=/; max-age=0`;
  }
}

function pretty(data) {
  try {
    return JSON.stringify(JSON.parse(data), null, 2);
  } catch {
    return data;
  }
}

async function fetchIdentity() {
  const res = await fetch("/me");
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
  const [identity, setIdentity] = useState({ user: "checking...", allowed: null });
  const [topics, setTopics] = useState([]);
  const [topic, setTopic] = useState("");
  const [token, setToken] = useState("");
  const [status, setStatus] = useState("disconnected");
  const [messages, setMessages] = useState([]);
  const [count, setCount] = useState(0);
  const wsRef = useRef(null);

  const connected = status === "connected";
  const bad = status.startsWith("closed") || status === "error";

  const refreshIdentity = useCallback(async () => {
    try {
      setIdentity(await fetchIdentity());
    } catch {
      setIdentity({ user: "unknown", allowed: null });
    }
  }, []);

  useEffect(() => {
    refreshIdentity();
    fetchTopics()
      .then((list) => {
        setTopics(list);
        setTopic((current) => current || list[0] || "");
      })
      .catch((e) => setStatus(`topics unavailable: ${e.message}`));
  }, [refreshIdentity]);

  // after the discord oauth redirect the user lands on /me (raw json);
  // switching back to this tab re-reads identity from the new cookie
  useEffect(() => {
    const onFocus = () => refreshIdentity();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshIdentity]);

  function disconnect() {
    if (wsRef.current) wsRef.current.close();
  }

  function connect({ anonymous = false, useToken = false } = {}) {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;
    if (!topic) {
      setStatus("no topic selected");
      return;
    }
    if (useToken) setManualCookie(token.trim() || null);

    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    const url = `${proto}${location.host}/firehose/${topic}${anonymous ? "?anonymous=1" : ""}`;
    setStatus("connecting...");
    if (anonymous) setIdentity({ user: "anonymous", allowed: true });

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

  return (
    <main className="min-h-screen bg-neutral-900 p-8 font-mono text-sm text-neutral-200">
      <h1 className="mb-6 text-lg font-bold">Bot Detector Firehose</h1>

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span>
          identity: <strong>{identity.user}</strong>
          {identity.allowed === false && <em className="text-red-400"> (403 - token not allowed)</em>}
        </span>
        {identity.user === "anonymous" && identity.allowed !== false && (
          <a className="text-sky-400 underline" href="/login">
            login with discord
          </a>
        )}
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
        <button className={btn} onClick={() => connect({ useToken: true })} disabled={connected}>
          connect with token/cookie
        </button>
        <button className={btn} onClick={() => connect({ anonymous: true })} disabled={connected}>
          connect anonymous
        </button>
        <button className={btn} onClick={disconnect} disabled={!connected}>
          disconnect
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
