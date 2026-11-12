// A local preview of the worker without Cloudflare: node test/dev-server.js [port]
// Uses an in-memory database with a few made-up reports. Admin password: local-preview-password
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { DatabaseSync } from "node:sqlite";

import worker from "../worker.js";

const db = new DatabaseSync(":memory:");
db.exec(readFileSync(new URL("../schema.sql", import.meta.url), "utf8"));
const statement = (sql, args = []) => ({
  bind: (...values) => statement(sql, values),
  run: async () => { db.prepare(sql).run(...args); return { success: true }; },
  all: async () => ({ results: db.prepare(sql).all(...args) }),
  first: async () => db.prepare(sql).get(...args) ?? null,
});
const env = {
  ADMIN_TOKEN: "local-preview-password",
  DB: { prepare: (sql) => statement(sql), batch: async (list) => { for (const s of list) await s.run(); return []; } },
};

if (process.argv.includes("--sample")) {
  const hex = (n) => n.toString(16).padStart(32, "0");
  for (let i = 1; i <= 24; i++) {
    const body = {
      v: 1, kind: "run", id: hex(i), app: i % 4 ? "1.3.0" : "1.2.9", os: i % 3 ? "Windows 11" : "Android 14", proc: "worker",
      counts: { runs: 1 + (i % 3), "video.ok": 6 + i, "video.fail": i % 3, "video.unconfirmed": i % 2, "workid.ok": 4, "workid.fail": i % 5 === 0 ? 1 : 0,
        "document.ok": 3, "captcha.seen": i % 4, "chapter.retry": i % 3, "chapters.done": 20 + i, "chapters.total": 30 + i,
        "net.requests": 400 + i * 10, "net.fail": i % 6, "net.timeout": i % 7 === 0 ? 1 : 0, "ai.requests": 5, "ai.questions": 22 },
      timings: { "task.video": [540000 * 6, 6], "task.workid": [42000 * 4, 4], "net.cx": [180 * 400, 400] },
      gauges: { "perf.mem_peak_mb": 150 + i * 3, "perf.cpu_s": 40 + i, "perf.run_s": 3600 + i * 60, "cfg.jobs": 1 + (i % 3) },
    };
    await worker.fetch(new Request("http://local/v1/report", { method: "POST", body: JSON.stringify(body) }), env);
  }
  await worker.fetch(new Request("http://local/v1/report", { method: "POST", body: JSON.stringify({
    v: 1, kind: "crash", id: hex(3), app: "1.3.0", os: "Windows 11", proc: "worker", counts: { "worker.crash": 1 },
    crash: { type: "KeyError", message: "<文>", frames: ["main.py:main:900", "api/base.py:study_video:1234"] } }) }), env);
  // spread the sample over the last days so the trend chart has something to draw
  const days = [...Array(6)].map((_, k) => new Date(Date.now() - k * 86400000).toISOString().slice(0, 10));
  db.exec("UPDATE installs SET day = CASE " + days.map((d, k) => `WHEN rowid % 6 = ${k} THEN '${d}'`).join(" ") + " END");
  for (const d of days.slice(1)) db.exec(`INSERT OR IGNORE INTO metrics SELECT '${d}', app, os, key, kind, value * 0.8 FROM metrics WHERE day = '${days[0]}'`);
}

const port = Number(process.argv.find((a) => /^\d+$/.test(a))) || 8787;
createServer(async (req, res) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const request = new Request(`http://127.0.0.1:${port}${req.url}`, {
    method: req.method, headers: req.headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : Buffer.concat(chunks),
  });
  const response = await worker.fetch(request, env);
  res.writeHead(response.status, Object.fromEntries(response.headers));
  res.end(Buffer.from(await response.arrayBuffer()));
}).listen(port, "127.0.0.1", () => console.log(`http://127.0.0.1:${port}  (管理密码 local-preview-password)`));
