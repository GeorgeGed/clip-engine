export interface Env {
  DB: D1Database;
  CLIPS: R2Bucket;
  APP_PASSWORD?: string;
  SESSION_SECRET?: string;
  PIPELINE_TOKEN?: string;
  MODAL_START_URL?: string;
  NOTIFY_WEBHOOK_URL?: string;
  PUBLIC_URL?: string;
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface Job {
  id: string;
  vod_url: string;
  clips_wanted: number;
  status: JobStatus;
  stage: string | null;
  message: string | null;
  progress: number | null;
  vod_title: string | null;
  channel: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  modal_call_id?: string | null;
  caption_font?: string | null;
  clip_count?: number;
  covers?: string | null;
}

export interface Clip {
  id: number;
  job_id: string;
  n: number;
  title: string | null;
  emoji: string | null;
  keyword: string | null;
  subject: string | null;
  score: number | null;
  duration: number | null;
  vod_start: number | null;
  video_key: string;
  preview_key: string | null;
  thumb_key: string | null;
  created_at: string;
}

export interface JobEvent {
  id: number;
  job_id: string;
  at: string;
  stage: string | null;
  message: string | null;
}
