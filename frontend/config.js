// Toggle this depending on the environment.
// `next dev` (NODE_ENV=development) talks to the API on this machine.
// `next build` / `next start` (Replit, Vercel) uses the live backend.
// After Render prints a URL, set NEXT_PUBLIC_API_URL to that URL
// (or replace the placeholder below). Routes have no /api prefix.

const IS_PRODUCTION = process.env.NODE_ENV === "production";

const PRODUCTION_API_URL = process.env.NEXT_PUBLIC_API_URL || "https://onrender.com";

const API_BASE_URL = IS_PRODUCTION
  ? PRODUCTION_API_URL
  : "http://127.0.0.1:8000";

export { IS_PRODUCTION, API_BASE_URL };
