// node --test test/   (Node 22.5+: uses the built-in node:sqlite as a stand-in for D1)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";

import worker, { clean, prune } from "../worker.js";

/** The part of the D1 API the worker uses, on an in-memory SQLite database. */
function fakeD1() {
  const db = new DatabaseSync(":memory:");
  db.exec(readFileSync(new URL("../schema.sql", import.meta.url), "utf8"));
  const statement = (sql, args = []) => ({
    bind: (...values) => statement(sql, values),
    run: async () => { db.prepare(sql).run(...args); return { success: true }; },
    all: async () => ({ results: db.prepare(sql).all(...args) }),
    first: async () => db.prepare(sql).get(...args) ?? null,
  });
  return {
    raw: db,
    prepare: (sql) => statement(sql),
    batch: async (list) => { for (const s of list) await s.run(); return []; },
  };
}

const ID = "0123456789abcdef0123456789abcdef";
const report = (extra = {}) => ({
  v: 1, kind: "run", id: ID, app: "1.3.0", os: "Windows 11", proc: "worker", day: "2026-11-10",
  counts: { runs: 1, "video.ok": 4, "video.fail": 1, "captcha.seen": 2 },
  timings: { "task.video": [600000, 5] }, gauges: { "perf.mem_peak_mb": 180.5 }, ...extra,
});
const env = () => ({ DB: fakeD1(), ADMIN_TOKEN: "a-long-admin-password" });
const post = (e, body, headers = {}) => worker.fetch(new Request("https://t.example/v1/report", {
  method: "POST", body: typeof body === "string" ? body : JSON.stringify(body), headers,
}), e);
const get = (e, path, token) => worker.fetch(new Request("https://t.example" + path, {
  headers: token ? { authorization: "Bearer " + token } : {},
}), e);

test("a valid report is stored as aggregates", async () => {
  const e = env();
  assert.equal((await post(e, report())).status, 200);
  assert.equal((await post(e, report({ id: "f".repeat(32), os: "Android 14" }))).status, 200);
  const rows = e.DB.raw.prepare("SELECT key, kind, SUM(value) AS v FROM metrics GROUP BY key, kind").all();
  const value = (key, kind) => rows.find((r) => r.key === key && r.kind === kind)?.v;
  assert.equal(value("video.ok", "count"), 8);
  assert.equal(value("task.video", "ms"), 1200000);
  assert.equal(value("task.video", "n"), 10);
  assert.equal(value("perf.mem_peak_mb", "gn"), 2);
  assert.equal(e.DB.raw.prepare("SELECT COUNT(*) AS n FROM installs").get().n, 2);
});

test("nothing but the whitelisted fields gets in", async () => {
  const bad = [
    report({ username: "13800138000" }),                          // an extra field
    report({ counts: { "高等数学": 1 } }),                          // a name that is not a category
    report({ counts: { "video.13800138000": 1 } }),
    report({ counts: { "video.ok": "many" } }),
    report({ counts: { "video.ok": -1 } }),
    report({ id: "not-an-id" }),
    report({ v: 2 }),
    report({ kind: "debug" }),
    report({ timings: { "task.video": [1, 0] } }),
    report({ crash: { type: "ValueError", message: "x", frames: ["C:\\Users\\zhangsan\\a.py:f:1"] } }),
    report({ crash: { type: "Value Error; DROP", message: "x", frames: [] } }),
    [report()], "not json", "null",
  ];
  const e = env();
  for (const body of bad) assert.equal((await post(e, body)).status, 400, JSON.stringify(body).slice(0, 80));
  assert.equal(e.DB.raw.prepare("SELECT COUNT(*) AS n FROM metrics").get().n, 0);
  assert.equal(clean(report({ app: "<script>", os: "x".repeat(99) })).app, "unknown");   // odd labels are replaced
});

test("a body that is too large is refused", async () => {
  assert.equal((await post(env(), "x".repeat(20000))).status, 413);
});

test("the client's IP address is never stored", async () => {
  const e = env();
  await post(e, report(), { "cf-connecting-ip": "203.0.113.77", "x-forwarded-for": "203.0.113.77" });
  const dump = ["installs", "metrics", "crashes", "rate"]
    .map((t) => JSON.stringify(e.DB.raw.prepare(`SELECT * FROM ${t}`).all())).join("");
  assert.ok(!dump.includes("203.0.113"));
});

test("an install that sends too often is limited", async () => {
  const e = env();
  let last;
  for (let i = 0; i < 31; i++) last = await post(e, report());
  assert.equal(last.status, 429);
  assert.equal(e.DB.raw.prepare("SELECT SUM(value) AS v FROM metrics WHERE key = 'runs'").get().v, 30);
});

test("crashes are kept with type and code location only", async () => {
  const e = env();
  const crash = { type: "KeyError", message: "<文> <n>", frames: ["api/base.py:study_video:1234", "main.py:main:900"] };
  assert.equal((await post(e, report({ kind: "crash", counts: { "worker.crash": 1 }, timings: {}, gauges: {}, crash }))).status, 200);
  const row = e.DB.raw.prepare("SELECT * FROM crashes").get();
  assert.equal(row.type, "KeyError");
  assert.deepEqual(JSON.parse(row.frames), crash.frames);
});

test("the dashboard data needs the admin password", async () => {
  const e = env();
  await post(e, report());
  assert.equal((await get(e, "/api/summary")).status, 401);
  assert.equal((await get(e, "/api/summary", "wrong-password-here")).status, 401);
  assert.equal((await get(e, "/api/export.csv", "wrong")).status, 401);
  const ok = await get(e, "/api/summary", "a-long-admin-password");
  assert.equal(ok.status, 200);
  const data = await ok.json();
  assert.equal(data.active, 1);
  assert.equal(data.totals.find((r) => r.key === "video.ok").value, 4);
  assert.deepEqual(data.versions, [{ name: "1.3.0", installs: 1 }]);
  const csv = await (await get(e, "/api/export.csv", "a-long-admin-password")).text();
  assert.match(csv, /^day,app,os,key,kind,value\n/);
});

test("no password configured means the data stays closed", async () => {
  const e = { DB: fakeD1(), ADMIN_TOKEN: "" };
  assert.equal((await get(e, "/api/summary", "")).status, 401);
  assert.equal((await get(e, "/api/summary", "anything")).status, 401);
  assert.equal((await get({ DB: fakeD1(), ADMIN_TOKEN: "short" }, "/api/summary", "short")).status, 401);
});

test("filters by version and platform", async () => {
  const e = env();
  await post(e, report());
  await post(e, report({ id: "a".repeat(32), app: "1.2.9", os: "Android 14" }));
  const data = await (await get(e, "/api/summary?app=1.2.9&os=Android%2014", "a-long-admin-password")).json();
  assert.equal(data.active, 1);
  assert.equal(data.totals.find((r) => r.key === "video.ok").value, 4);
  const injected = await get(e, "/api/summary?app=1.3.0'%20OR%201=1--", "a-long-admin-password");
  assert.equal((await injected.json()).active, 0);              // bound as a value, not SQL
});

test("data older than the retention period is deleted", async () => {
  const e = env();
  await post(e, report());
  e.DB.raw.exec("UPDATE metrics SET day = '2020-01-01'; UPDATE installs SET day = '2020-01-01'");
  await post(e, report({ id: "b".repeat(32) }));
  await prune(e);
  assert.equal(e.DB.raw.prepare("SELECT COUNT(*) AS n FROM installs").get().n, 1);
  assert.equal(e.DB.raw.prepare("SELECT COUNT(*) AS n FROM metrics WHERE day = '2020-01-01'").get().n, 0);
});

test("the dashboard page holds no data and other paths are 404", async () => {
  const e = env();
  const page = await get(e, "/");
  assert.equal(page.status, 200);
  assert.match(await page.text(), /匿名统计/);
  assert.equal((await get(e, "/v1/report")).status, 405);
  assert.equal((await get(e, "/admin")).status, 404);
});
