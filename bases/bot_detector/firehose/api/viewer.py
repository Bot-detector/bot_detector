"""HTML viewer for the firehose websocket."""

VIEWER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bot Detector Firehose</title>
<style>
  body { font-family: monospace; background: #111; color: #ddd; margin: 2rem; }
  h1 { font-size: 1.2rem; }
  #status { font-weight: bold; }
  .open { color: #6f6; }
  .closed { color: #f66; }
  a { color: #6cf; }
  button { background: #333; color: #ddd; border: 1px solid #555; padding: 0.4rem 1rem; cursor: pointer; margin-right: 0.5rem; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  ul { list-style: none; padding: 0; }
  li { padding: 0.2rem 0; border-bottom: 1px solid #333; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>Bot Detector Firehose</h1>
<p>
  identity: <span id="identity">checking...</span>
  <a id="login" href="/login">login with discord</a>
</p>
<p>
  status: <span id="status">disconnected</span> | messages: <span id="count">0</span>
</p>
<button id="connect-token">connect with token</button>
<button id="connect-anonymous">connect anonymous</button>
<button id="disconnect" disabled>disconnect</button>
<ul id="messages"></ul>
<script>
  const statusEl = document.getElementById("status");
  const countEl = document.getElementById("count");
  const listEl = document.getElementById("messages");
  const identityEl = document.getElementById("identity");
  const loginEl = document.getElementById("login");
  const tokenBtn = document.getElementById("connect-token");
  const anonBtn = document.getElementById("connect-anonymous");
  const discBtn = document.getElementById("disconnect");
  const MAX_LINES = 25;
  let ws = null;
  let count = 0;

  function setStatus(text, cls) {
    statusEl.textContent = text;
    statusEl.className = cls || "";
  }

  function setButtons(connected) {
    tokenBtn.disabled = connected;
    anonBtn.disabled = connected;
    discBtn.disabled = !connected;
  }

  function isConnected() {
    return ws && ws.readyState === WebSocket.OPEN;
  }

  function connect(opts = {}) {
    if (isConnected() || (ws && ws.readyState === WebSocket.CONNECTING)) return;
    if (opts.token) {
      // browsers cannot set headers on the handshake; the pasted token
      // travels as its own cookie (separate from the login cookie)
      document.cookie = "firehose_api_key_manual=" + encodeURIComponent(opts.token) +
        "; path=/; max-age=604800; samesite=lax";
    }
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    const url = proto + location.host + location.pathname +
      (opts.anonymous ? "?anonymous=1" : "");
    setStatus("connecting...");
    setButtons(true);
    if (opts.anonymous) identityEl.textContent = "anonymous";
    ws = new WebSocket(url);
    ws.onopen = () => setStatus("connected", "open");
  ws.onclose = (e) => {
    setStatus(`closed (code=${e.code}${e.reason ? " " + e.reason : ""})`, "closed");
    setButtons(false);
    refreshIdentity();
  };
    ws.onerror = () => setStatus("error", "closed");
    ws.onmessage = (e) => {
      count++;
      countEl.textContent = count;
      const li = document.createElement("li");
      li.textContent = new Date().toISOString() + "  " + e.data;
      listEl.prepend(li);
      while (listEl.children.length > MAX_LINES) listEl.removeChild(listEl.lastChild);
    };
  }

  function disconnect() {
    if (ws) ws.close();
  }

  function refreshIdentity(onAllowed) {
    fetch("/me")
      .then((r) => r.json())
      .then((d) => {
        identityEl.textContent = d.user;
        loginEl.style.display =
          d.user === "anonymous" && d.allowed ? "inline" : "none";
        if (d.allowed === false) {
          setStatus("403 forbidden - token not allowed", "closed");
          setButtons(true);
          discBtn.disabled = true;
          return;
        }
        if (onAllowed) onAllowed();
      })
      .catch(() => {
        identityEl.textContent = "unknown";
        if (onAllowed) onAllowed();
      });
  }

  tokenBtn.addEventListener("click", () => {
    const token = prompt(
      "paste your discord access token,\\nor leave empty to use your existing cookie:"
    );
    if (token === null) return; // cancelled
    if (token.trim() === "") {
      // cookie mode: drop any manual override, fall back to the login cookie
      document.cookie = "firehose_api_key_manual=; path=/; max-age=0";
      refreshIdentity(() => connect());
    } else {
      connect({ token: token.trim() });
      refreshIdentity();
    }
  });

  anonBtn.addEventListener("click", () => connect({ anonymous: true }));
  discBtn.addEventListener("click", disconnect);

  refreshIdentity(() => connect());
</script>
</body>
</html>
"""
