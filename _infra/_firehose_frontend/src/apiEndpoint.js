const STORAGE_KEY = "firehose_endpoint";

// empty value = same-origin through the vite dev proxy
export const ENDPOINT_PRESETS = [
  { label: "dev proxy (default)", value: "" },
  { label: "localhost:5000", value: "http://localhost:5000" },
  { label: "localhost:8000 (compose dev)", value: "http://localhost:8000" },
  {
    label: "live (firehose.osrsbotdetector.com)",
    value: "https://firehose.osrsbotdetector.com",
  },
];

function normalize(value) {
  return value.trim().replace(/\/+$/, "");
}

export function loadEndpoint() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored !== null) return stored;
  return import.meta.env.VITE_FIREHOSE_URL || "";
}

export function saveEndpoint(value) {
  const normalized = normalize(value);
  localStorage.setItem(STORAGE_KEY, normalized);
  return normalized;
}

// base "" -> ws(s)://<current host>; http(s) base -> ws(s) base
export function wsOrigin(base) {
  if (!base) {
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    return `${proto}${location.host}`;
  }
  return base.replace(/^http/, "ws");
}
