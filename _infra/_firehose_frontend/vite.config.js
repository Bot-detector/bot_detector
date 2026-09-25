import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// firehose api target; override with FIREHOSE_URL=http://host:port npm run dev
const target = process.env.FIREHOSE_URL || "http://localhost:5000";

export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    port: 5173,
    proxy: {
      // ws: true upgrades websocket connections (/firehose/{topic})
      "/firehose": { target, ws: true },
      "/login": { target },
      "/me": { target },
    },
  },
});
