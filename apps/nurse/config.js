// Same toggle as frontend/config.js. Development uses the local API.
// Production uses NEXT_PUBLIC_API_URL, or the Render placeholder until you paste the live URL.

const IS_PRODUCTION = process.env.NODE_ENV === "production";

const PRODUCTION_API_URL = process.env.NEXT_PUBLIC_API_URL || "https://onrender.com";

const API_BASE_URL = IS_PRODUCTION
  ? PRODUCTION_API_URL
  : "http://127.0.0.1:8000";

export { IS_PRODUCTION, API_BASE_URL };
