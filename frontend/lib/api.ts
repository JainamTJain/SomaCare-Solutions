import { API_BASE_URL } from "../config";

export const API_URL = API_BASE_URL;

export type HowTo = { code: string; params: Record<string, string> };
export type Visit = {
  visit_id: string;
  resident: { id: string; preferred_name: string; room: string; language?: string };
  tasks: string[];
  due_at: string;
  priority: number;
  why: Record<string, unknown>;
  how_to: HowTo[];
  two_person: boolean;
  camera_online: boolean;
  position: string;
  alert_id: string | null;
  settled: boolean;
};
export type TimeSaved = {
  minutes: number;
  hours: number;
  remainder_min: number;
  verified_checks: number;
  merged_visits: number;
};
export type ChartLine = { ts: string; code: string; params: Record<string, string> };
export type Shift = {
  shift_id: string;
  language: string;
  staff: { id: string; display_name: string; role: string };
  items: Visit[];
  verified_checks: number;
  time_saved?: TimeSaved;
  chart_lines?: ChartLine[];
  generated_at: string;
};

async function request(path: string, token: string | null, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return response.json();
  return response.text();
}

export const api = {
  roster: () => request("/auth/roster", null),
  login: (staff_id: string, pin: string) =>
    request("/auth/login", null, { method: "POST", body: JSON.stringify({ staff_id, pin }) }),
  shift: (token: string) => request("/me/shift", token) as Promise<Shift>,
  calendar: (token: string) => request("/me/shift.ics", token) as Promise<string>,
  engineer: (token: string) => request("/engineer/board", token),
  director: (token: string) => request("/director/board", token),
  card: (token: string, id: string) => request(`/residents/${id}/card`, token),
  history: (token: string, id: string) => request(`/residents/${id}/history?days=7`, token),
  continence: (token: string, id: string) => request(`/residents/${id}/continence`, token),
  accept: (token: string, id: string) => request(`/alerts/${id}/accept`, token, { method: "POST" }),
  pass: (token: string, id: string) => request(`/alerts/${id}/pass`, token, { method: "POST" }),
  confirm: (token: string, id: string) => request(`/alerts/${id}/confirm`, token, { method: "POST" }),
  help: (token: string, resident_id: string) =>
    request("/help", token, { method: "POST", body: JSON.stringify({ resident_id }) }),
  note: (token: string, text_note: string) => {
    const body = new FormData();
    body.set("text_note", text_note);
    return request("/handoff/notes", token, { method: "POST", body });
  },
};

const DB = "turnwise-cna";

function idb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open(DB, 1);
    open.onupgradeneeded = () => open.result.createObjectStore("kv");
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error);
  });
}

export async function cacheShift(shift: Shift) {
  const db = await idb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("kv", "readwrite");
    tx.objectStore("kv").put(shift, "shift");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function cachedShift(): Promise<Shift | null> {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("kv", "readonly");
    const req = tx.objectStore("kv").get("shift");
    req.onsuccess = () => resolve((req.result as Shift) || null);
    req.onerror = () => reject(req.error);
  });
}
