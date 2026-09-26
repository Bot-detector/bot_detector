const AUTHORIZE_URL = "https://discord.com/oauth2/authorize";
const TOKEN_URL = "https://discord.com/api/oauth2/token";
const REVOKE_URL = "https://discord.com/api/oauth2/token/revoke";

const STATE_KEY = "discord_pkce_state";
const VERIFIER_KEY = "discord_pkce_verifier";
const TOKENS_KEY = "discord_tokens";
const REFRESH_SLACK_MS = 60_000;

export const SCOPE = "identify";

export function clientId() {
  return import.meta.env.VITE_DISCORD_CLIENT_ID || "";
}

export function redirectUri() {
  return `${window.location.origin}/callback`;
}

function base64url(bytes) {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

async function pkcePair() {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  );
  return { verifier, challenge: base64url(new Uint8Array(digest)) };
}

function loadTokens() {
  try {
    return JSON.parse(localStorage.getItem(TOKENS_KEY));
  } catch {
    return null;
  }
}

function saveTokens(token) {
  const tokens = { ...token, expires_at: Date.now() + token.expires_in * 1000 };
  localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
  return tokens;
}

export function clearTokens() {
  localStorage.removeItem(TOKENS_KEY);
}

async function tokenRequest(data) {
  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(data),
  });
  if (!res.ok) throw new Error(`token request failed (${res.status})`);
  return res.json();
}

export async function startLogin() {
  if (!clientId()) throw new Error("VITE_DISCORD_CLIENT_ID is not set");
  const { verifier, challenge } = await pkcePair();
  const state = base64url(crypto.getRandomValues(new Uint8Array(16)));
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId(),
    scope: SCOPE,
    state,
    redirect_uri: redirectUri(),
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  window.location.assign(`${AUTHORIZE_URL}?${params}`);
}

export async function handleCallback() {
  const url = new URL(window.location.href);
  const error = url.searchParams.get("error");
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const expected = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  if (error) throw new Error(`oauth error: ${error}`);
  if (!code) throw new Error("missing code");
  if (!expected || state !== expected) throw new Error("state mismatch");
  if (!verifier) throw new Error("missing code_verifier");
  saveTokens(
    await tokenRequest({
      client_id: clientId(),
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri(),
      code_verifier: verifier,
    }),
  );
}

export async function refreshTokens() {
  const tokens = loadTokens();
  if (!tokens?.refresh_token) throw new Error("no refresh token");
  return saveTokens(
    await tokenRequest({
      client_id: clientId(),
      grant_type: "refresh_token",
      refresh_token: tokens.refresh_token,
    }),
  );
}

export async function validAccessToken() {
  const tokens = loadTokens();
  if (!tokens?.access_token) return null;
  if (tokens.expires_at - REFRESH_SLACK_MS > Date.now()) {
    return tokens.access_token;
  }
  try {
    return (await refreshTokens()).access_token;
  } catch {
    clearTokens();
    return null;
  }
}

export async function logout() {
  const tokens = loadTokens();
  clearTokens();
  if (!tokens?.access_token) return;
  try {
    await fetch(REVOKE_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Authorization: `Bearer ${tokens.access_token}`,
      },
      body: new URLSearchParams({ token: tokens.access_token }),
    });
  } catch {
    return;
  }
}
