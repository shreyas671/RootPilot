import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import test from "node:test";
import { setTimeout as delay } from "node:timers/promises";

const port = 3210;

async function waitForServer(process) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (process.exitCode !== null) {
      throw new Error(`Next.js exited before becoming ready (${process.exitCode})`);
    }
    try {
      return await fetch(`http://127.0.0.1:${port}/`);
    } catch {
      await delay(200);
    }
  }
  throw new Error("Timed out waiting for the Next.js production server");
}

test("server-renders the RootPilot operations console", async (context) => {
  const server = spawn(
    process.execPath,
    [
      "node_modules/next/dist/bin/next",
      "start",
      "--hostname",
      "127.0.0.1",
      "--port",
      String(port),
    ],
    {
      cwd: new URL("..", import.meta.url),
      stdio: "pipe",
    },
  );
  context.after(() => server.kill("SIGTERM"));

  const response = await waitForServer(server);
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>RootPilot Operations<\/title>/i);
  assert.match(html, /Operations command center/);
  assert.match(html, /Queue an incident/);
  assert.match(html, /Grounded assessments/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});
