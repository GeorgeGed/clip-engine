import type { Env } from "./env";
import { slugify } from "./util";

const TYPES: Record<string, string> = {
  mp4: "video/mp4",
  m4v: "video/mp4",
  mov: "video/quicktime",
  webm: "video/webm",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  gif: "image/gif",
  json: "application/json",
  srt: "text/plain; charset=utf-8",
  vtt: "text/vtt",
};

function extension(key: string): string {
  return /\.([a-z0-9]+)$/i.exec(key)?.[1].toLowerCase() ?? "";
}

type ByteRange = { offset: number; length: number };

export function parseRange(header: string, size: number): ByteRange | "unsatisfiable" | null {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!m || (m[1] === "" && m[2] === "")) return null;
  if (m[1] === "") {
    const suffix = Number(m[2]);
    if (suffix === 0 || size === 0) return "unsatisfiable";
    const offset = Math.max(0, size - suffix);
    return { offset, length: size - offset };
  }
  const start = Number(m[1]);
  const end = m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
  if (start >= size || end < start) return "unsatisfiable";
  return { offset: start, length: end - start + 1 };
}

async function downloadName(env: Env, key: string): Promise<string> {
  const row = await env.DB.prepare(
    "SELECT title FROM clips WHERE video_key = ?1 OR preview_key = ?1 OR thumb_key = ?1 LIMIT 1",
  )
    .bind(key)
    .first<{ title: string | null }>();
  const ext = extension(key) || "mp4";
  const base = key.split("/").pop()!.replace(/\.[^.]*$/, "");
  return `${slugify(row?.title ?? "") || slugify(base) || "clip"}.${ext}`;
}

export async function serveFile(request: Request, env: Env, key: string): Promise<Response> {
  if (!key) return new Response("Not found", { status: 404 });
  const head = await env.CLIPS.head(key);
  if (!head) return new Response("Not found", { status: 404 });

  const headers = new Headers({
    "content-type": head.httpMetadata?.contentType || TYPES[extension(key)] || "application/octet-stream",
    "accept-ranges": "bytes",
    "cache-control": "private, max-age=3600",
    etag: head.httpEtag,
  });
  if (new URL(request.url).searchParams.get("download") === "1") {
    const name = await downloadName(env, key);
    headers.set("content-disposition", `attachment; filename="${name}"; filename*=UTF-8''${encodeURIComponent(name)}`);
  }

  const rangeHeader = request.headers.get("range");
  const range = rangeHeader ? parseRange(rangeHeader, head.size) : null;
  if (range === "unsatisfiable") {
    headers.set("content-range", `bytes */${head.size}`);
    return new Response(null, { status: 416, headers });
  }

  const length = range ? range.length : head.size;
  headers.set("content-length", String(length));
  if (range) headers.set("content-range", `bytes ${range.offset}-${range.offset + range.length - 1}/${head.size}`);
  const status = range ? 206 : 200;

  if (request.method === "HEAD") return new Response(null, { status, headers });

  const object = await env.CLIPS.get(key, range ? { range } : undefined);
  if (!object) return new Response("Not found", { status: 404 });
  return new Response(object.body, { status, headers });
}
