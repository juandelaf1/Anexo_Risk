// Autenticación JWT compartida para el frontend de Anexo Risk.
//
// El token de acceso se guarda en localStorage. Es una credencial de sesión
// del navegador; no es un secreto de servidor. La autorización real sigue
// viviendo en el backend.

const STORAGE_KEY = "anexo_access_token";
const USER_KEY = "anexo_user";

export function getAccessToken() {
  try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
}

export function getCurrentUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

export function isAuthenticated() {
  return !!getAccessToken();
}

export function setSession(token, user) {
  try {
    localStorage.setItem(STORAGE_KEY, token);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch (e) { /* ignore */ }
}

export function clearSession() {
  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(USER_KEY);
  } catch (e) { /* ignore */ }
}

export async function login(username, password) {
  const resp = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });
  if (!resp.ok) throw new Error(`Login failed: ${resp.status}`);
  const data = await resp.json();
  setSession(data.access_token, { username });
  // Fetch identity from /me
  try {
    const me = await apiAuthedGet("/api/auth/me");
    setSession(data.access_token, me);
  } catch (e) { /* keep minimal session */ }
  return data;
}

export async function register(username, email, password) {
  const resp = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, email, password, role: "ciudadano" }),
  });
  if (!resp.ok) throw new Error(`Register failed: ${resp.status}`);
  return resp.json();
}

export function logout() {
  clearSession();
}

export function authHeaders(extra = {}) {
  const token = getAccessToken();
  const headers = { ...extra };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

// Internal helper used before importing config to avoid cycles.
async function apiAuthedGet(path) {
  const resp = await fetch(path, { headers: authHeaders() });
  if (!resp.ok) throw new Error(`GET ${path} -> ${resp.status}`);
  return resp.json();
}
