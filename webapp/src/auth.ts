import type { Env } from "./env";

const COOKIE = "ce_session";
const MAX_AGE = 30 * 24 * 60 * 60;

function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);
}

function b64url(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function unb64url(s: string): Uint8Array | null {
  try {
    const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
}

export async function sessionCookie(env: Env): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + MAX_AGE;
  const payload = `v1.${exp}`;
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(env.SESSION_SECRET!), new TextEncoder().encode(payload));
  return `${COOKIE}=${payload}.${b64url(sig)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${MAX_AGE}`;
}

export function clearSessionCookie(): string {
  return `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

export async function hasSession(request: Request, env: Env): Promise<boolean> {
  if (!env.SESSION_SECRET) return false;
  const value = request.headers
    .get("cookie")
    ?.split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${COOKIE}=`))
    ?.slice(COOKIE.length + 1);
  const m = value && /^(v1\.(\d+))\.([A-Za-z0-9_-]+)$/.exec(value);
  if (!m || Number(m[2]) < Date.now() / 1000) return false;
  const sig = unb64url(m[3]);
  if (!sig) return false;
  return crypto.subtle.verify("HMAC", await hmacKey(env.SESSION_SECRET), sig, new TextEncoder().encode(m[1]));
}
