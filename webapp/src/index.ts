import { clearSessionCookie, hasSession, sessionCookie } from "./auth";
import type { Clip, Env, Job, JobEvent, JobStatus } from "./env";
import { serveFile } from "./files";
import { homePage, jobPage, loginPage, notFoundPage } from "./views";
import { json, newJobId, now, parseTwitchVod, publicUrl, safeEqual } from "./util";

const STATUSES: JobStatus[] = ["queued", "running", "done", "failed"];

function html(body: string, status = 200, headers: HeadersInit = {}): Response {
  return new Response(body, {
    status,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}

function redirect(location: string, headers: HeadersInit = {}): Response {
  return new Response(null, { status: 303, headers: { location, ...headers } });
}

async function readJson(request: Request): Promise<Record<string, unknown> | null> {
  const body = await request.json().catch(() => null);
  return body && typeof body === "object" && !Array.isArray(body) ? (body as Record<string, unknown>) : null;
}

const str = (v: unknown) => (typeof v === "string" ? v : null);
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

function getJob(env: Env, id: string): Promise<Job | null> {
  return env.DB.prepare("SELECT * FROM jobs WHERE id = ?").bind(id).first<Job>();
}

function addEvent(env: Env, jobId: string, stage: string | null, message: string | null): D1PreparedStatement {
  return env.DB.prepare("INSERT INTO events (job_id, at, stage, message) VALUES (?, ?, ?, ?)").bind(
    jobId,
    now(),
    stage,
    message,
  );
}

async function listJobs(env: Env): Promise<Job[]> {
  const { results } = await env.DB.prepare(
    `SELECT j.*, (SELECT COUNT(*) FROM clips c WHERE c.job_id = j.id) AS clip_count,
       (SELECT group_concat(thumb_key, '|') FROM (SELECT thumb_key FROM clips c WHERE c.job_id = j.id AND c.thumb_key IS NOT NULL ORDER BY c.n LIMIT 3)) AS covers
     FROM jobs j ORDER BY j.created_at DESC LIMIT 100`,
  ).all<Job>();
  return results;
}

async function jobDetail(env: Env, id: string) {
  const job = await getJob(env, id);
  if (!job) return null;
  const [clips, events] = await env.DB.batch<Clip | JobEvent>([
    env.DB.prepare("SELECT * FROM clips WHERE job_id = ? ORDER BY n").bind(id),
    env.DB.prepare("SELECT * FROM events WHERE job_id = ? ORDER BY id DESC LIMIT 50").bind(id),
  ]);
  return {
    job: { ...job, clip_count: clips.results.length },
    clips: clips.results as Clip[],
    events: (events.results as JobEvent[]).reverse(),
  };
}

async function failJob(env: Env, id: string, error: string): Promise<void> {
  const t = now();
  await env.DB.batch([
    env.DB.prepare(
      "UPDATE jobs SET status = 'failed', stage = 'failed', message = NULL, error = ?, updated_at = ?, finished_at = ? WHERE id = ?",
    ).bind(error, t, t, id),
    addEvent(env, id, "failed", error),
  ]);
}

function vodName(job: Pick<Job, "vod_title" | "vod_url">): string {
  const t = job.vod_title?.trim();
  return t ? (t.length > 140 ? t.slice(0, 139) + "…" : t) : `Twitch VOD ${job.vod_url.split("/").pop()}`;
}

async function notify(env: Env, key: string, payload: { title: string; body: string; url: string }): Promise<void> {
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await fetch(env.NOTIFY_WEBHOOK_URL!, {
        method: "POST",
        headers: { "content-type": "application/json", "idempotency-key": key },
        body: JSON.stringify({ ...payload, body: payload.body.slice(0, 2000) }),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) console.error(`Notification webhook returned HTTP ${res.status}`);
      return;
    } catch (e) {
      console.error(`Notification webhook failed (attempt ${attempt}):`, e);
    }
  }
}

function announce(
  env: Env,
  ctx: ExecutionContext,
  request: Request,
  job: Pick<Job, "id" | "vod_title" | "vod_url">,
  event: "submitted" | "running" | "done" | "failed",
  title: string,
  body: string,
): void {
  if (!env.NOTIFY_WEBHOOK_URL) return;
  ctx.waitUntil(
    notify(env, `${job.id}:${event}:${now()}`, { title, body, url: `${publicUrl(env, request)}/jobs/${job.id}` }),
  );
}

async function dispatch(env: Env, ctx: ExecutionContext, request: Request, job: Job): Promise<Job> {
  let error: string | null = null;
  if (!env.MODAL_START_URL) {
    error = "MODAL_START_URL is not configured";
  } else {
    try {
      const res = await fetch(env.MODAL_START_URL, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${env.PIPELINE_TOKEN ?? ""}` },
        body: JSON.stringify({
          job_id: job.id,
          vod_url: job.vod_url,
          clips: job.clips_wanted,
          callback_base: publicUrl(env, request),
        }),
        signal: AbortSignal.timeout(20_000),
      });
      if (!res.ok) error = `Pipeline start failed: HTTP ${res.status} ${(await res.text()).slice(0, 300)}`.trim();
    } catch (e) {
      error = `Pipeline start failed: ${e instanceof Error ? e.message : String(e)}`;
    }
  }
  if (error) {
    await failJob(env, job.id, error);
    announce(env, ctx, request, job, "failed", "Clip job failed", `${vodName(job)} could not start: ${error}`);
  } else await addEvent(env, job.id, "queued", "Sent to pipeline").run();
  return (await getJob(env, job.id))!;
}

async function createJob(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const isForm = (request.headers.get("content-type") ?? "").includes("application/x-www-form-urlencoded");
  let input: Record<string, unknown> | null;
  if (isForm) {
    const form = await request.formData();
    input = { vod_url: form.get("vod_url"), clips: form.get("clips") };
  } else {
    input = await readJson(request);
  }
  if (!input) return json({ error: "Expected a JSON body" }, 400);

  const vodUrl = parseTwitchVod(input.vod_url);
  if (!vodUrl) return json({ error: "Enter a Twitch VOD link like https://www.twitch.tv/videos/1234567890" }, 400);
  const clipsRaw = input.clips ?? 10;
  const clips = typeof clipsRaw === "string" && clipsRaw.trim() !== "" ? Number(clipsRaw) : clipsRaw;
  if (typeof clips !== "number" || !Number.isInteger(clips) || clips < 1 || clips > 30)
    return json({ error: "Number of clips must be a whole number from 1 to 30" }, 400);

  const id = newJobId();
  const t = now();
  await env.DB.batch([
    env.DB.prepare(
      "INSERT INTO jobs (id, vod_url, clips_wanted, status, stage, message, created_at, updated_at) VALUES (?, ?, ?, 'queued', 'queued', 'Waiting for the pipeline', ?, ?)",
    ).bind(id, vodUrl, clips, t, t),
    addEvent(env, id, "queued", `Job created for ${vodUrl} (${clips} clips)`),
  ]);
  const created = (await getJob(env, id))!;
  announce(env, ctx, request, created, "submitted", "VOD submitted", `${vodName(created)}: ${clips} clip${clips === 1 ? "" : "s"} requested. Sending it to Modal now.`);
  const job = await dispatch(env, ctx, request, created);
  return isForm ? redirect(`/jobs/${id}`) : json({ ...job, clip_count: 0 }, 201);
}

async function retryJob(request: Request, env: Env, ctx: ExecutionContext, id: string): Promise<Response> {
  const job = await getJob(env, id);
  if (!job) return json({ error: "Job not found" }, 404);
  if (job.status !== "failed") return json({ error: "Only failed jobs can be retried" }, 409);
  await env.DB.batch([
    env.DB.prepare(
      "UPDATE jobs SET status = 'queued', stage = 'queued', message = 'Retrying', progress = NULL, error = NULL, finished_at = NULL, updated_at = ? WHERE id = ?",
    ).bind(now(), id),
    addEvent(env, id, "queued", "Retry requested"),
  ]);
  return json(await dispatch(env, ctx, request, (await getJob(env, id))!));
}

async function deleteJob(env: Env, id: string): Promise<Response> {
  if (!(await getJob(env, id))) return json({ error: "Job not found" }, 404);
  let cursor: string | undefined;
  do {
    const page = await env.CLIPS.list({ prefix: `jobs/${id}/`, cursor });
    if (page.objects.length) await env.CLIPS.delete(page.objects.map((o) => o.key));
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM events WHERE job_id = ?").bind(id),
    env.DB.prepare("DELETE FROM clips WHERE job_id = ?").bind(id),
    env.DB.prepare("DELETE FROM jobs WHERE id = ?").bind(id),
  ]);
  return json({ deleted: id });
}

async function pipelineProgress(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  body: Record<string, unknown>,
): Promise<Response> {
  const id = str(body.job_id);
  const job = id && (await getJob(env, id));
  if (!job) return json({ error: "Unknown job_id" }, 404);
  const status = body.status == null ? null : str(body.status);
  if (status !== null && !STATUSES.includes(status as JobStatus)) return json({ error: "Invalid status" }, 400);
  const hasProgress = "progress" in body;
  const progress = body.progress == null ? null : num(body.progress);
  if (hasProgress && body.progress != null && progress === null) return json({ error: "Invalid progress" }, 400);
  const stage = str(body.stage);
  const message = str(body.message);

  const statements = [
    env.DB.prepare(
      `UPDATE jobs SET
        status = COALESCE(?1, CASE WHEN status = 'queued' THEN 'running' ELSE status END),
        stage = COALESCE(?2, stage),
        message = COALESCE(?3, message),
        progress = CASE WHEN ?4 THEN ?5 ELSE progress END,
        vod_title = COALESCE(?6, vod_title),
        channel = COALESCE(?7, channel),
        updated_at = ?8
      WHERE id = ?9`,
    ).bind(
      status,
      stage,
      message,
      hasProgress ? 1 : 0,
      progress === null ? null : Math.min(1, Math.max(0, progress)),
      str(body.vod_title),
      str(body.channel),
      now(),
      id,
    ),
  ];
  if (stage || message) statements.push(addEvent(env, id, stage, message));
  await env.DB.batch(statements);
  if (job.status === "queued" && (status === null || status === "running")) {
    const named = { ...job, vod_title: str(body.vod_title) ?? job.vod_title };
    announce(env, ctx, request, named, "running", "Clips in progress", `Modal started working on ${vodName(named)}.${message ? ` ${message}.` : ""}`);
  }
  return json({ ok: true });
}

async function pipelineClip(env: Env, body: Record<string, unknown>): Promise<Response> {
  const id = str(body.job_id);
  if (!id || !(await getJob(env, id))) return json({ error: "Unknown job_id" }, 404);
  const n = body.n;
  const videoKey = str(body.video_key);
  if (typeof n !== "number" || !Number.isInteger(n) || n < 0) return json({ error: "n must be an integer" }, 400);
  if (!videoKey) return json({ error: "video_key is required" }, 400);

  await env.DB.prepare(
    `INSERT INTO clips (job_id, n, title, emoji, keyword, subject, score, duration, vod_start, video_key, preview_key, thumb_key, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)
     ON CONFLICT (job_id, n) DO UPDATE SET
       title = excluded.title, emoji = excluded.emoji, keyword = excluded.keyword, subject = excluded.subject,
       score = excluded.score, duration = excluded.duration, vod_start = excluded.vod_start,
       video_key = excluded.video_key, preview_key = excluded.preview_key, thumb_key = excluded.thumb_key`,
  )
    .bind(
      id,
      n,
      str(body.title),
      str(body.emoji),
      str(body.keyword),
      str(body.subject),
      num(body.score),
      num(body.duration),
      num(body.vod_start),
      videoKey,
      str(body.preview_key),
      str(body.thumb_key),
      now(),
    )
    .run();
  await env.DB.prepare("UPDATE jobs SET updated_at = ? WHERE id = ?").bind(now(), id).run();
  return json({ ok: true });
}

async function pipelineDone(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  body: Record<string, unknown>,
): Promise<Response> {
  const id = str(body.job_id);
  const job = id && (await getJob(env, id));
  if (!job) return json({ error: "Unknown job_id" }, 404);
  const status = body.status;
  if (status !== "done" && status !== "failed") return json({ error: "status must be 'done' or 'failed'" }, 400);
  const error = status === "failed" ? str(body.error) || "Pipeline reported failure" : null;
  const count = (await env.DB.prepare("SELECT COUNT(*) AS n FROM clips WHERE job_id = ?").bind(id).first<number>("n")) ?? 0;
  const message = status === "done" ? `Finished with ${count} clip${count === 1 ? "" : "s"}` : null;
  const t = now();

  await env.DB.batch([
    env.DB.prepare(
      `UPDATE jobs SET status = ?1, stage = ?1, message = ?2, error = ?3,
        progress = CASE WHEN ?1 = 'done' THEN 1 ELSE progress END, updated_at = ?4, finished_at = ?4 WHERE id = ?5`,
    ).bind(status, message, error, t, id),
    addEvent(env, id, status, message ?? error),
  ]);

  if (job.status !== status) {
    if (status === "done")
      announce(env, ctx, request, job, "done", "Clips ready", `${count} clip${count === 1 ? " is" : "s are"} uploaded and ready to download for ${vodName(job)}.`);
    else announce(env, ctx, request, job, "failed", "Clip job failed", `${vodName(job)} failed: ${error}`);
  }
  return json({ ok: true });
}

async function handlePipeline(request: Request, env: Env, ctx: ExecutionContext, path: string): Promise<Response> {
  const token = /^Bearer\s+(.+)$/i.exec(request.headers.get("authorization") ?? "")?.[1] ?? "";
  if (!env.PIPELINE_TOKEN) console.error("PIPELINE_TOKEN is not configured; rejecting pipeline callback");
  if (!env.PIPELINE_TOKEN || !(await safeEqual(token, env.PIPELINE_TOKEN))) return json({ error: "Unauthorized" }, 401);
  if (request.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const body = await readJson(request);
  if (!body) return json({ error: "Expected a JSON body" }, 400);
  switch (path) {
    case "/api/pipeline/progress":
      return pipelineProgress(request, env, ctx, body);
    case "/api/pipeline/clip":
      return pipelineClip(env, body);
    case "/api/pipeline/done":
      return pipelineDone(request, env, ctx, body);
  }
  return json({ error: "Not found" }, 404);
}

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}

async function handleLogin(request: Request, env: Env, url: URL): Promise<Response> {
  if (request.method === "GET") return html(loginPage(null, safeNext(url.searchParams.get("next"))));
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
  if (!env.APP_PASSWORD || !env.SESSION_SECRET)
    return html(loginPage("Server is missing APP_PASSWORD or SESSION_SECRET.", "/"), 500);
  const form = await request.formData();
  const next = safeNext(str(form.get("next")));
  if (!(await safeEqual(str(form.get("password")) ?? "", env.APP_PASSWORD)))
    return html(loginPage("Wrong password.", next), 401);
  return redirect(next, { "set-cookie": await sessionCookie(env) });
}

async function route(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  if (path.startsWith("/api/pipeline/")) return handlePipeline(request, env, ctx, path);
  if (path === "/login") return handleLogin(request, env, url);

  if (!(await hasSession(request, env))) {
    if (path.startsWith("/api/")) return json({ error: "Unauthorized" }, 401);
    if (method === "GET" || method === "HEAD")
      return new Response(null, {
        status: 302,
        headers: { location: `/login?next=${encodeURIComponent(path + url.search)}` },
      });
    return new Response("Unauthorized", { status: 401 });
  }

  if (path === "/logout" && method === "POST") return redirect("/login", { "set-cookie": clearSessionCookie() });
  if (path === "/" && method === "GET") return html(homePage(await listJobs(env)));

  if (path.startsWith("/files/") && (method === "GET" || method === "HEAD")) {
    let key: string;
    try {
      key = decodeURIComponent(path.slice("/files/".length));
    } catch {
      return new Response("Bad request", { status: 400 });
    }
    return serveFile(request, env, key);
  }

  const page = /^\/jobs\/([a-z2-7]+)$/.exec(path);
  if (page && method === "GET") {
    const detail = await jobDetail(env, page[1]);
    return detail
      ? html(jobPage(detail.job, detail.clips, detail.events, await listJobs(env)))
      : html(notFoundPage(), 404);
  }

  if (path === "/api/jobs") {
    if (method === "GET") return json({ jobs: await listJobs(env) });
    if (method === "POST") return createJob(request, env, ctx);
    return json({ error: "Method not allowed" }, 405);
  }
  const api = /^\/api\/jobs\/([a-z2-7]+)(\/retry)?$/.exec(path);
  if (api) {
    const [, id, retry] = api;
    if (retry) return method === "POST" ? retryJob(request, env, ctx, id) : json({ error: "Method not allowed" }, 405);
    if (method === "GET") {
      const detail = await jobDetail(env, id);
      return detail ? json(detail) : json({ error: "Job not found" }, 404);
    }
    if (method === "DELETE") return deleteJob(env, id);
    return json({ error: "Method not allowed" }, 405);
  }

  return path.startsWith("/api/") ? json({ error: "Not found" }, 404) : html(notFoundPage(), 404);
}

export default {
  async fetch(request, env, ctx) {
    try {
      return await route(request, env, ctx);
    } catch (e) {
      console.error(e);
      return json({ error: "Internal error" }, 500);
    }
  },
} satisfies ExportedHandler<Env>;
