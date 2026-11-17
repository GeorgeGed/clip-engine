import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

export default defineConfig(async () => {
  const migrations = await readD1Migrations("./migrations");
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          bindings: {
            TEST_MIGRATIONS: migrations,
            APP_PASSWORD: "test-password",
            SESSION_SECRET: "test-session-secret",
            PIPELINE_TOKEN: "test-pipeline-token",
            MODAL_START_URL: "https://modal.test/start",
            NOTIFY_WEBHOOK_URL: "https://notify.test/hook",
            PUBLIC_URL: "https://clips.example.com",
          },
        },
      }),
    ],
    test: { setupFiles: ["./test/apply-migrations.ts"] },
  };
});
