import { createExecutionContext, env, waitOnExecutionContext } from "cloudflare:test";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import { parseRange } from "../src/files";
import { parseTwitchVod } from "../src/util";

const BASE = "https://clips.example.com";
const PIPE = { authorization: "Bearer test-pipeline-token", "content-type": "application/json" };
const VOD = "https://www.twitch.tv/videos/2905408276";

async function call(path: string, init: RequestInit = {}): Promise<Response> {
  const ctx = createExecutionContext();
  const res = await worker.fetch(new Request(BASE + path, { redirect: "manual", ...init }) as Parameters<typeof worker.fetch>[0], env, ctx);
  await waitOnExecutionContext(ctx);
  return res;
}

async function login(): Promise<string> {
  const res = await call("/login", { method: "POST", body: new URLSearchParams({ password: "test-password", next: "/" }) });
  return res.headers.get("set-cookie")!.split(";")[0];
}

type FetchCall = { url: string; init: RequestInit };
let outbound: FetchCall[];
let respond: (url: string) => Response | Promise<Response>;

beforeEach(() => {
  outbound = [];
  respond = () => Response.json({ ok: true });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = input instanceof Request ? input.url : String(input);
    outbound.push({ url, init: init ?? {} });
    return respond(url);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function createJob(cookie: string, body: unknown = { vod_url: VOD, clips: 5 }) {
  const res = await call("/api/jobs", {
    method: "POST",
    headers: { cookie, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { res, job: (await res.json()) as Record<string, any> };
}

function pipeline(path: string, body: unknown, token = "test-pipeline-token") {
  return call(`/api/pipeline/${path}`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("auth", () => {
  it("redirects pages and rejects API calls without a session", async () => {
    const page = await call("/jobs/abc?x=1");
    expect(page.status).toBe(302);
    expect(page.headers.get("location")).toBe("/login?next=%2Fjobs%2Fabc%3Fx%3D1");
    expect((await call("/api/jobs")).status).toBe(401);
    expect((await call("/files/jobs/x/a.mp4")).status).toBe(302);
    expect((await call("/login")).status).toBe(200);
  });

  it("rejects a wrong password", async () => {
    const res = await call("/login", { method: "POST", body: new URLSearchParams({ password: "nope" }) });
    expect(res.status).toBe(401);
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it("sets a signed session cookie that unlocks the app", async () => {
    const res = await call("/login", {
      method: "POST",
      body: new URLSearchParams({ password: "test-password", next: "/jobs/abc" }),
    });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/jobs/abc");
    const setCookie = res.headers.get("set-cookie")!;
    expect(setCookie).toMatch(/HttpOnly/);
    expect(setCookie).toMatch(/Secure/);
    expect(setCookie).toMatch(/SameSite=Lax/);
    expect(setCookie).toMatch(/Max-Age=2592000/);
    const cookie = setCookie.split(";")[0];
    const home = await call("/", { headers: { cookie } });
    expect(home.status).toBe(200);
    expect(await home.text()).toContain("Make clips");
    expect((await call("/api/jobs", { headers: { cookie } })).status).toBe(200);
  });

  it("rejects a tampered cookie and ignores external next targets", async () => {
    const cookie = await login();
    const tampered = cookie.replace(/v1\.(\d+)/, (_, exp) => `v1.${Number(exp) + 1}`);
    expect((await call("/api/jobs", { headers: { cookie: tampered } })).status).toBe(401);
    const res = await call("/login", {
      method: "POST",
      body: new URLSearchParams({ password: "test-password", next: "//evil.com" }),
    });
    expect(res.headers.get("location")).toBe("/");
  });

  it("logout clears the cookie", async () => {
    const cookie = await login();
    const res = await call("/logout", { method: "POST", headers: { cookie } });
    expect(res.headers.get("set-cookie")).toMatch(/Max-Age=0/);
  });
});

describe("VOD URL validation", () => {
  it.each([
    ["https://www.twitch.tv/videos/123456", "https://www.twitch.tv/videos/123456"],
    ["twitch.tv/videos/123456", "https://www.twitch.tv/videos/123456"],
    ["https://twitch.tv/videos/123456?filter=archives&sort=time", "https://www.twitch.tv/videos/123456"],
    ["https://m.twitch.tv/videos/123456/", "https://www.twitch.tv/videos/123456"],
    ["  http://www.twitch.tv/videos/99?t=1h2m3s  ", "https://www.twitch.tv/videos/99"],
  ])("accepts %s", (input, expected) => {
    expect(parseTwitchVod(input)).toBe(expected);
  });

  it.each([
    "https://www.twitch.tv/somechannel",
    "https://www.twitch.tv/videos/abc",
    "https://youtube.com/videos/123",
    "https://twitch.tv.evil.com/videos/123",
    "ftp://twitch.tv/videos/123",
    "",
  ])("rejects %s", (input) => {
    expect(parseTwitchVod(input)).toBeNull();
  });

  it("returns 400 for a bad URL or clip count without dispatching", async () => {
    const cookie = await login();
    expect((await createJob(cookie, { vod_url: "https://youtube.com/watch?v=1", clips: 5 })).res.status).toBe(400);
    expect((await createJob(cookie, { vod_url: VOD, clips: 0 })).res.status).toBe(400);
    expect((await createJob(cookie, { vod_url: VOD, clips: 31 })).res.status).toBe(400);
    expect((await createJob(cookie, { vod_url: VOD, clips: 2.5 })).res.status).toBe(400);
    expect(outbound).toHaveLength(0);
  });
});

describe("jobs", () => {
  it("creates a job and dispatches it to Modal", async () => {
    const cookie = await login();
    const { res, job } = await createJob(cookie, { vod_url: "twitch.tv/videos/42?x=1" });
    expect(res.status).toBe(201);
    expect(job.id).toMatch(/^[a-z2-7]{10}$/);
    expect(job.status).toBe("queued");
    expect(job.clips_wanted).toBe(10);
    const modal = outbound.filter((o) => o.url === "https://modal.test/start");
    expect(modal).toHaveLength(1);
    expect(new Headers(modal[0].init.headers).get("authorization")).toBe("Bearer test-pipeline-token");
    expect(JSON.parse(modal[0].init.body as string)).toEqual({
      job_id: job.id,
      vod_url: "https://www.twitch.tv/videos/42",
      clips: 10,
      callback_base: "https://clips.example.com",
    });

    const list = (await (await call("/api/jobs", { headers: { cookie } })).json()) as { jobs: any[] };
    expect(list.jobs.map((j) => j.id)).toContain(job.id);
  });

  it("stores Modal's call id and shows the run timeline on the job page", async () => {
    const cookie = await login();
    respond = (url) => (url === "https://modal.test/start" ? Response.json({ ok: true, call_id: "fc-01TESTCALL" }) : Response.json({ ok: true }));
    const { job } = await createJob(cookie);
    await pipeline("progress", { job_id: job.id, stage: "download", message: "Downloading 2:52:28 of video" });
    const detail = (await (await call(`/api/jobs/${job.id}`, { headers: { cookie } })).json()) as any;
    expect(detail.job.modal_call_id).toBe("fc-01TESTCALL");
    const page = await (await call(`/jobs/${job.id}`, { headers: { cookie } })).text();
    expect(page).toContain("Run timeline");
    expect(page).toContain("fc-01TESTCALL");
    expect(page).toContain("Download VOD");
  });

  it("marks the job failed when Modal rejects it, and retry re-dispatches", async () => {
    const cookie = await login();
    respond = () => new Response("boom", { status: 500 });
    const { res, job } = await createJob(cookie);
    expect(res.status).toBe(201);
    expect(job.status).toBe("failed");
    expect(job.error).toContain("HTTP 500");

    respond = () => Response.json({ ok: true });
    const retry = await call(`/api/jobs/${job.id}/retry`, { method: "POST", headers: { cookie } });
    expect(retry.status).toBe(200);
    const retried = (await retry.json()) as any;
    expect(retried.status).toBe("queued");
    expect(retried.error).toBeNull();
    expect(outbound.filter((o) => o.url === "https://modal.test/start")).toHaveLength(2);

    const again = await call(`/api/jobs/${job.id}/retry`, { method: "POST", headers: { cookie } });
    expect(again.status).toBe(409);
  });

  it("marks the job failed when Modal is unreachable", async () => {
    const cookie = await login();
    respond = () => {
      throw new Error("connection refused");
    };
    const { job } = await createJob(cookie);
    expect(job.status).toBe("failed");
    expect(job.error).toContain("connection refused");
  });

  it("accepts a no-JS form post and redirects to the job page", async () => {
    const cookie = await login();
    const res = await call("/api/jobs", {
      method: "POST",
      headers: { cookie },
      body: new URLSearchParams({ vod_url: VOD, clips: "3" }),
    });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toMatch(/^\/jobs\/[a-z2-7]{10}$/);
  });
});

describe("pipeline callbacks", () => {
  it.each(["progress", "clip", "done"])("rejects %s without the right token", async (path) => {
    expect((await pipeline(path, { job_id: "x" }, "wrong")).status).toBe(401);
    const noAuth = await call(`/api/pipeline/${path}`, { method: "POST", body: "{}" });
    expect(noAuth.status).toBe(401);
  });

  it("progress updates the job and appends an event", async () => {
    const cookie = await login();
    const { job } = await createJob(cookie);
    const res = await pipeline("progress", {
      job_id: job.id,
      stage: "download",
      message: "Downloading VOD",
      progress: 0.25,
      vod_title: "Big tournament day",
      channel: "tarik",
    });
    expect(res.status).toBe(200);
    const detail = (await (await call(`/api/jobs/${job.id}`, { headers: { cookie } })).json()) as any;
    expect(detail.job).toMatchObject({
      status: "running",
      stage: "download",
      message: "Downloading VOD",
      progress: 0.25,
      vod_title: "Big tournament day",
      channel: "tarik",
    });
    expect(detail.events.at(-1)).toMatchObject({ stage: "download", message: "Downloading VOD" });

    expect((await pipeline("progress", { job_id: "nope", stage: "x" })).status).toBe(404);
    expect((await pipeline("progress", { job_id: job.id, status: "bogus" })).status).toBe(400);
  });

  it("clip callback upserts on (job_id, n)", async () => {
    const cookie = await login();
    const { job } = await createJob(cookie);
    const clip = {
      job_id: job.id,
      n: 3,
      title: "First take",
      emoji: "🔥",
      keyword: "ace",
      subject: "an ace",
      score: 0.9,
      duration: 41.5,
      vod_start: 3723,
      video_key: `jobs/${job.id}/03-first-take.mp4`,
      preview_key: `jobs/${job.id}/03-first-take.preview.mp4`,
      thumb_key: `jobs/${job.id}/03-first-take.jpg`,
    };
    expect((await pipeline("clip", clip)).status).toBe(200);
    expect((await pipeline("clip", { ...clip, title: "Second take", score: 0.95 })).status).toBe(200);
    const detail = (await (await call(`/api/jobs/${job.id}`, { headers: { cookie } })).json()) as any;
    expect(detail.clips).toHaveLength(1);
    expect(detail.clips[0]).toMatchObject({ n: 3, title: "Second take", score: 0.95 });

    const page = await (await call(`/jobs/${job.id}`, { headers: { cookie } })).text();
    expect(page).toContain("Second take");
    expect(page).toContain(`${VOD}?t=1h2m3s`);
    expect(page).toContain(`/files/jobs/${job.id}/03-first-take.mp4?download=1`);

    expect((await pipeline("clip", { ...clip, n: "x" })).status).toBe(400);
  });

  it("notifies when a VOD is submitted and when the pipeline starts running", async () => {
    const cookie = await login();
    const { job } = await createJob(cookie);
    const hook = () => outbound.filter((o) => o.url === "https://notify.test/hook").map((o) => JSON.parse(o.init.body as string));
    expect(hook()).toEqual([
      {
        title: "VOD submitted",
        body: "Twitch VOD 2905408276: 5 clips requested. Sending it to Modal now.",
        url: `https://clips.example.com/jobs/${job.id}`,
      },
    ]);
    outbound = [];
    await pipeline("progress", { job_id: job.id, stage: "download", message: "Downloading 2:52:28 of video", vod_title: "FNS scrims" });
    expect(hook()).toEqual([
      {
        title: "Clips in progress",
        body: "Modal started working on FNS scrims. Downloading 2:52:28 of video.",
        url: `https://clips.example.com/jobs/${job.id}`,
      },
    ]);
    outbound = [];
    await pipeline("progress", { job_id: job.id, stage: "transcribe", message: "Transcribing" });
    expect(hook()).toEqual([]);
  });

  it("done finalizes the job and calls the notification webhook", async () => {
    const cookie = await login();
    const { job } = await createJob(cookie);
    await pipeline("progress", { job_id: job.id, stage: "render", message: "Rendering", vod_title: "VOD title" });
    await pipeline("clip", { job_id: job.id, n: 1, title: "A", video_key: `jobs/${job.id}/01-a.mp4` });
    outbound = [];
    const res = await pipeline("done", { job_id: job.id, status: "done" });
    expect(res.status).toBe(200);
    expect(outbound).toHaveLength(1);
    expect(outbound[0].url).toBe("https://notify.test/hook");
    expect(JSON.parse(outbound[0].init.body as string)).toEqual({
      title: "Clips ready",
      body: "1 clip is uploaded and ready to download for VOD title.",
      url: `https://clips.example.com/jobs/${job.id}`,
    });
    expect(new Headers(outbound[0].init.headers).get("idempotency-key")).toMatch(new RegExp(`^${job.id}:done:`));
    const detail = (await (await call(`/api/jobs/${job.id}`, { headers: { cookie } })).json()) as any;
    expect(detail.job.status).toBe("done");
    expect(detail.job.progress).toBe(1);
    expect(detail.job.finished_at).toBeTruthy();

    outbound = [];
    await pipeline("done", { job_id: job.id, status: "done" });
    expect(outbound).toHaveLength(0);
  });

  it("failed done reports the error, and a broken webhook does not fail the callback", async () => {
    const cookie = await login();
    const { job } = await createJob(cookie);
    outbound = [];
    respond = () => {
      throw new Error("push service down");
    };
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const res = await pipeline("done", { job_id: job.id, status: "failed", error: "VOD is sub-only" });
    expect(res.status).toBe(200);
    expect(JSON.parse(outbound[0].init.body as string)).toMatchObject({ title: "Clip job failed", body: "Twitch VOD 2905408276 failed: VOD is sub-only" });
    expect(errSpy).toHaveBeenCalled();
    const detail = (await (await call(`/api/jobs/${job.id}`, { headers: { cookie } })).json()) as any;
    expect(detail.job).toMatchObject({ status: "failed", error: "VOD is sub-only" });

    expect((await pipeline("done", { job_id: job.id, status: "running" })).status).toBe(400);
  });
});

describe("files", () => {
  const bytes = Uint8Array.from({ length: 1000 }, (_, i) => i % 256);

  it("serves full objects, ranges, and downloads with a friendly name", async () => {
    const cookie = await login();
    const { job } = await createJob(cookie);
    const key = `jobs/${job.id}/01-clip.mp4`;
    await env.CLIPS.put(key, bytes);
    await pipeline("clip", { job_id: job.id, n: 1, title: "Ace on Haven!", video_key: key });

    const full = await call(`/files/${key}`, { headers: { cookie } });
    expect(full.status).toBe(200);
    expect(full.headers.get("content-type")).toBe("video/mp4");
    expect(full.headers.get("accept-ranges")).toBe("bytes");
    expect(new Uint8Array(await full.arrayBuffer())).toEqual(bytes);

    const part = await call(`/files/${key}`, { headers: { cookie, range: "bytes=100-199" } });
    expect(part.status).toBe(206);
    expect(part.headers.get("content-range")).toBe("bytes 100-199/1000");
    expect(part.headers.get("content-length")).toBe("100");
    expect(new Uint8Array(await part.arrayBuffer())).toEqual(bytes.slice(100, 200));

    const open = await call(`/files/${key}`, { headers: { cookie, range: "bytes=990-" } });
    expect(open.status).toBe(206);
    expect(open.headers.get("content-range")).toBe("bytes 990-999/1000");
    expect((await open.arrayBuffer()).byteLength).toBe(10);

    const bad = await call(`/files/${key}`, { headers: { cookie, range: "bytes=5000-" } });
    expect(bad.status).toBe(416);
    expect(bad.headers.get("content-range")).toBe("bytes */1000");

    const dl = await call(`/files/${key}?download=1`, { headers: { cookie } });
    expect(dl.headers.get("content-disposition")).toContain('attachment; filename="ace-on-haven.mp4"');

    expect((await call(`/files/jobs/${job.id}/missing.mp4`, { headers: { cookie } })).status).toBe(404);
  });

  it("parses range headers", () => {
    expect(parseRange("bytes=0-0", 10)).toEqual({ offset: 0, length: 1 });
    expect(parseRange("bytes=-3", 10)).toEqual({ offset: 7, length: 3 });
    expect(parseRange("bytes=5-100", 10)).toEqual({ offset: 5, length: 5 });
    expect(parseRange("bytes=0-1,4-5", 10)).toBeNull();
    expect(parseRange("bytes=8-2", 10)).toBe("unsatisfiable");
  });

  it("delete removes the job, its clips and its R2 objects", async () => {
    const cookie = await login();
    const { job } = await createJob(cookie);
    await env.CLIPS.put(`jobs/${job.id}/01.mp4`, "a");
    await env.CLIPS.put(`jobs/${job.id}/01.jpg`, "b");
    await env.CLIPS.put("jobs/other/01.mp4", "c");
    await pipeline("clip", { job_id: job.id, n: 1, video_key: `jobs/${job.id}/01.mp4` });
    const res = await call(`/api/jobs/${job.id}`, { method: "DELETE", headers: { cookie } });
    expect(res.status).toBe(200);
    expect((await env.CLIPS.list({ prefix: `jobs/${job.id}/` })).objects).toHaveLength(0);
    expect(await env.CLIPS.head("jobs/other/01.mp4")).not.toBeNull();
    expect((await call(`/api/jobs/${job.id}`, { headers: { cookie } })).status).toBe(404);
    const n = await env.DB.prepare("SELECT COUNT(*) AS n FROM clips WHERE job_id = ?").bind(job.id).first("n");
    expect(n).toBe(0);
  });
});
