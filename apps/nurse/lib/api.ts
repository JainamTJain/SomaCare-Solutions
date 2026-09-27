import { API_BASE_URL } from "../config";

const API = API_BASE_URL;

export async function call(path: string, token: string | null, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...init, headers });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export function session() {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("tw_nurse");
  return raw ? JSON.parse(raw) : null;
}
