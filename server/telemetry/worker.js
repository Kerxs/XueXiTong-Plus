// 学习通 PLUS 匿名统计的接收端和管理后台（Cloudflare Worker + D1）。
//
//   POST /v1/report        客户端上报（api/telemetry.py）。不需要密钥；只接受白名单里的数字。
//   GET  /                 管理后台页面（数据要用管理密码才能读取）。
//   GET  /api/summary      后台用的汇总数据。   Authorization: Bearer <ADMIN_TOKEN>
//   GET  /api/export.csv   导出聚合数据。       同上
//   每天定时：删除超过 RETENTION_DAYS（默认 90）天的数据。
//
// 不读取也不保存请求的 IP 地址；报文里出现白名单以外的字段或名字，整条丢弃。

const MAX_BODY = 16000;
const MAX_KEYS = 200;
const REPORTS_PER_HOUR = 30;
const KEY = /^(runs|video|audio|live|workid|work|document|other|homework|captcha|relogin|chapter|chapters|run|network|net|ai|app|worker|preview|task|perf|cfg)(\.[a-z][a-z0-9_]{0,23}){0,3}$/;
const FRAME = /^[A-Za-z0-9_./]{1,80}:[A-Za-z0-9_<>]{1,60}:\d{1,6}$/;

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
});

function today(offsetDays = 0) {
  return new Date(Date.now() + offsetDays * 86400000).toISOString().slice(0, 10);
}

/** The report with only what is allowed, or null when anything about it is off. */
export function clean(report) {
  if (!report || typeof report !== "object" || Array.isArray(report)) return null;
  const allowed = ["v", "kind", "id", "app", "os", "proc", "day", "counts", "timings", "gauges", "crash"];
  if (Object.keys(report).some((k) => !allowed.includes(k))) return null;
  if (report.v !== 1) return null;
  if (!["run", "app", "crash"].includes(report.kind)) return null;
  if (typeof report.id !== "string" || !/^[0-9a-f]{32}$/.test(report.id)) return null;
  const app = typeof report.app === "string" && /^[0-9]{1,3}(\.[0-9]{1,3}){1,3}$/.test(report.app) ? report.app : "unknown";
  const os = typeof report.os === "string" && /^[A-Za-z0-9 ._-]{1,40}$/.test(report.os) ? report.os : "unknown";
  const proc = report.proc === "gui" ? "gui" : "worker";
  const out = { kind: report.kind, id: report.id, app, os, proc, counts: {}, timings: {}, gauges: {} };

  const section = (value) => (value && typeof value === "object" && !Array.isArray(value) ? Object.entries(value) : []);
  const counts = section(report.counts), timings = section(report.timings), gauges = section(report.gauges);
  if (counts.length + timings.length + gauges.length > MAX_KEYS) return null;
  for (const [key, value] of counts) {
    if (!KEY.test(key) || !Number.isInteger(value) || value < 0 || value > 1e7) return null;
    out.counts[key] = value;
  }
  for (const [key, value] of timings) {
    if (!KEY.test(key) || !Array.isArray(value) || value.length !== 2) return null;
    const [ms, n] = value;
    if (!Number.isFinite(ms) || !Number.isInteger(n) || ms < 0 || ms > 1e11 || n < 1 || n > 1e7) return null;
    out.timings[key] = [Math.round(ms), n];
  }
  for (const [key, value] of gauges) {
    if (!KEY.test(key) || !Number.isFinite(value) || Math.abs(value) > 1e9) return null;
    out.gauges[key] = value;
  }
  if (report.crash !== undefined) {
    const crash = report.crash;
    if (!crash || typeof crash !== "object") return null;
    if (typeof crash.type !== "string" || !/^[A-Za-z_][A-Za-z0-9_.]{0,59}$/.test(crash.type)) return null;
    if (!Array.isArray(crash.frames) || crash.frames.length > 12 || crash.frames.some((f) => typeof f !== "string" || !FRAME.test(f))) return null;
    out.crash = { type: crash.type, message: String(crash.message ?? "").slice(0, 200), frames: crash.frames };
  }
  return out;
}

async function receive(request, env) {
  const text = await request.text();
  if (text.length > MAX_BODY) return json({ error: "too large" }, 413);
  let report;
  try { report = clean(JSON.parse(text)); } catch { report = null; }
  if (!report) return json({ error: "invalid report" }, 400);

  const day = today();                       // the server's date: a client clock cannot move a report
  const hour = new Date().toISOString().slice(0, 13);
  const rate = await env.DB.prepare(
    "INSERT INTO rate (install, hour, n) VALUES (?1, ?2, 1) ON CONFLICT (install, hour) DO UPDATE SET n = n + 1 RETURNING n",
  ).bind(report.id, hour).first();
  if (rate && rate.n > REPORTS_PER_HOUR) return json({ error: "too many reports" }, 429);

  const add = (key, kind, value, max = false) => env.DB.prepare(
    "INSERT INTO metrics (day, app, os, key, kind, value) VALUES (?1, ?2, ?3, ?4, ?5, ?6) ON CONFLICT (day, app, os, key, kind) DO UPDATE SET value = "
      + (max ? "MAX(value, excluded.value)" : "value + excluded.value"),
  ).bind(day, report.app, report.os, key, kind, value);

  const statements = [env.DB.prepare(
    "INSERT INTO installs (day, install, app, os, reports) VALUES (?1, ?2, ?3, ?4, 1) ON CONFLICT (day, install) DO UPDATE SET reports = reports + 1, app = excluded.app, os = excluded.os",
  ).bind(day, report.id, report.app, report.os)];
  for (const [key, value] of Object.entries(report.counts)) statements.push(add(key, "count", value));
  for (const [key, [ms, n]] of Object.entries(report.timings)) statements.push(add(key, "ms", ms), add(key, "n", n));
  for (const [key, value] of Object.entries(report.gauges)) {
    statements.push(add(key, "gsum", value), add(key, "gn", 1), add(key, "gmax", value, true));
  }
  if (report.crash) {
    statements.push(env.DB.prepare(
      "INSERT INTO crashes (day, app, os, proc, type, message, frames) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
    ).bind(day, report.app, report.os, report.proc, report.crash.type, report.crash.message, JSON.stringify(report.crash.frames)));
  }
  await env.DB.batch(statements);
  return json({ ok: true });
}

/** Constant-time comparison of the admin password. */
async function authorized(request, env) {
  const token = env.ADMIN_TOKEN || "";
  const given = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (token.length < 12 || !given) return false;        // no or a too short password configured: closed
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([crypto.subtle.digest("SHA-256", enc.encode(token)), crypto.subtle.digest("SHA-256", enc.encode(given))]);
  const x = new Uint8Array(a), y = new Uint8Array(b);
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

function filters(url) {
  const date = (value, fallback) => (/^\d{4}-\d{2}-\d{2}$/.test(value || "") ? value : fallback);
  const from = date(url.searchParams.get("from"), today(-29));
  const to = date(url.searchParams.get("to"), today());
  const where = ["day >= ?1", "day <= ?2"], args = [from, to];
  for (const name of ["app", "os"]) {
    const value = url.searchParams.get(name);
    if (value) { args.push(value); where.push(`${name} = ?${args.length}`); }
  }
  return { from, to, where: where.join(" AND "), args };
}

async function summary(url, env) {
  const f = filters(url);
  const all = (sql) => env.DB.prepare(sql).bind(...f.args).all().then((r) => r.results);
  const [totals, daily, installs, versions, systems, crashes, options] = await Promise.all([
    all(`SELECT key, kind, SUM(value) AS value, MAX(value) AS top FROM metrics WHERE ${f.where} GROUP BY key, kind`),
    all(`SELECT day, key, SUM(value) AS value FROM metrics WHERE ${f.where} AND kind = 'count' GROUP BY day, key ORDER BY day`),
    all(`SELECT day, COUNT(*) AS installs, SUM(reports) AS reports FROM installs WHERE ${f.where} GROUP BY day ORDER BY day`),
    all(`SELECT app AS name, COUNT(DISTINCT install) AS installs FROM installs WHERE ${f.where} GROUP BY app ORDER BY installs DESC`),
    all(`SELECT os AS name, COUNT(DISTINCT install) AS installs FROM installs WHERE ${f.where} GROUP BY os ORDER BY installs DESC`),
    all(`SELECT type, frames, MAX(message) AS message, COUNT(*) AS n, MAX(day) AS last, MAX(app) AS app FROM crashes WHERE ${f.where} GROUP BY type, frames ORDER BY n DESC LIMIT 30`),
    env.DB.prepare("SELECT DISTINCT app, os FROM installs ORDER BY app DESC").all().then((r) => r.results),
  ]);
  const active = await env.DB.prepare(`SELECT COUNT(DISTINCT install) AS n FROM installs WHERE ${f.where}`).bind(...f.args).first();
  return json({ from: f.from, to: f.to, active: active?.n ?? 0, totals, daily, installs, versions, systems, crashes, options });
}

async function exportCsv(url, env) {
  const f = filters(url);
  const rows = (await env.DB.prepare(
    `SELECT day, app, os, key, kind, value FROM metrics WHERE ${f.where} ORDER BY day, app, os, key, kind`,
  ).bind(...f.args).all()).results;
  const csv = ["day,app,os,key,kind,value", ...rows.map((r) => [r.day, r.app, r.os, r.key, r.kind, r.value].join(","))].join("\n");
  return new Response(csv, { headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": "attachment; filename=xxtplus-telemetry.csv" } });
}

export async function prune(env, days = Number(env.RETENTION_DAYS) || 90) {
  const limit = today(-days);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM metrics WHERE day < ?1").bind(limit),
    env.DB.prepare("DELETE FROM installs WHERE day < ?1").bind(limit),
    env.DB.prepare("DELETE FROM crashes WHERE day < ?1").bind(limit),
    env.DB.prepare("DELETE FROM rate WHERE hour < ?1").bind(today(-2)),
  ]);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/v1/report") {
        return request.method === "POST" ? await receive(request, env) : json({ error: "POST only" }, 405);
      }
      if (url.pathname === "/" && request.method === "GET") {
        return new Response(DASHBOARD, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "x-frame-options": "DENY", "referrer-policy": "no-referrer", "x-content-type-options": "nosniff",
          "content-security-policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" } });
      }
      if (url.pathname.startsWith("/api/")) {
        if (!(await authorized(request, env))) return json({ error: "unauthorized" }, 401);
        if (url.pathname === "/api/summary") return await summary(url, env);
        if (url.pathname === "/api/export.csv") return await exportCsv(url, env);
      }
      return json({ error: "not found" }, 404);
    } catch (error) {
      return json({ error: "server error" }, 500);       // no details: nothing about the data leaks
    }
  },
  async scheduled(_event, env) {
    await prune(env);
  },
};

// The dashboard is one page without external scripts. It holds no data: everything comes from
// /api/summary with the password typed in (kept in sessionStorage for this tab only).
const DASHBOARD = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>学习通 PLUS · 匿名统计</title>
<style>
:root{--bg:#f3f5f9;--card:#fff;--text:#1a1f2b;--muted:#6b7385;--line:#e3e7ef;--accent:#2563eb;--ok:#13865a;--bad:#c2372b;--warn:#a86200}
@media (prefers-color-scheme:dark){:root{--bg:#0f131b;--card:#181d28;--text:#e8ecf4;--muted:#98a2b6;--line:#2a3142;--accent:#6ea0ff;--ok:#5fd39b;--bad:#ff8a7d;--warn:#f2c45f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:20px 16px 60px}h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:0 0 10px}
.sub{color:var(--muted);font-size:12px}.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:end;margin:16px 0}
label{display:flex;flex-direction:column;font-size:12px;color:var(--muted);gap:3px}
input,select,button{font:inherit;padding:7px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--text)}
button{background:var(--accent);border-color:var(--accent);color:#fff;cursor:pointer}button.ghost{background:transparent;color:var(--text);border-color:var(--line)}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}.two{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}.tile b{display:block;font-size:24px;line-height:1.2}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line)}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.meter{height:6px;border-radius:3px;background:var(--line);overflow:hidden;min-width:70px}.meter i{display:block;height:100%;background:var(--ok)}
svg{width:100%;height:120px;display:block}code{font-size:12px;word-break:break-all}.err{color:var(--bad)}.hide{display:none}
</style></head><body><main>
<h1>学习通 PLUS · 匿名统计</h1><div class="sub">只有次数、耗时和大小；没有账号、课程、题目和 IP。数据保留 90 天。</div>
<div class="bar" id="login"><label>管理密码<input id="token" type="password" autocomplete="off"></label><button id="enter">进入</button><span class="err" id="loginErr"></span></div>
<div id="app" class="hide">
<div class="bar"><label>开始<input id="from" type="date"></label><label>结束<input id="to" type="date"></label>
<label>版本<select id="appSel"><option value="">全部</option></select></label><label>平台<select id="osSel"><option value="">全部</option></select></label>
<button id="load">查询</button><button class="ghost" id="csv">导出 CSV</button><button class="ghost" id="out">退出</button><span class="err" id="err"></span></div>
<div class="grid" id="tiles"></div>
<div class="two"><div class="card"><h2>每天的活跃安装和运行次数</h2><svg id="chart" viewBox="0 0 600 120" preserveAspectRatio="none"></svg><div class="sub" id="chartNote"></div></div>
<div class="card"><h2>各功能成功率</h2><table id="rates"></table></div></div>
<div class="two"><div class="card"><h2>稳定性</h2><table id="stability"></table></div><div class="card"><h2>网络</h2><table id="network"></table></div></div>
<div class="two"><div class="card"><h2>性能与资源</h2><table id="perf"></table></div><div class="card"><h2>版本与平台</h2><table id="dist"></table></div></div>
<div class="card" style="margin-top:12px"><h2>崩溃（按类型和位置归并）</h2><table id="crashes"></table></div>
</div></main><script>
const $=(id)=>document.getElementById(id);const esc=(s)=>String(s??"").replace(/[&<>"]/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let token=sessionStorage.getItem("t")||"";const fmt=(n)=>Number(n||0).toLocaleString("zh-CN",{maximumFractionDigits:1});
function query(){const p=new URLSearchParams();for(const [k,id] of [["from","from"],["to","to"],["app","appSel"],["os","osSel"]]){if($(id).value)p.set(k,$(id).value)}return p.toString()}
async function api(path){const r=await fetch(path,{headers:{authorization:"Bearer "+token}});if(r.status===401)throw new Error("密码不对");if(!r.ok)throw new Error("读取失败（"+r.status+"）");return r}
function row(cells){return "<tr>"+cells.map((c,i)=>i?'<td class="n">'+c+"</td>":"<td>"+c+"</td>").join("")+"</tr>"}
function head(names){return "<tr>"+names.map((c,i)=>i?'<th class="n">'+c+"</th>":"<th>"+c+"</th>").join("")+"</tr>"}
async function load(){$("err").textContent="";try{const d=await(await api("/api/summary?"+query())).json();render(d)}catch(e){$("err").textContent=e.message;if(e.message==="密码不对")logout()}}
function render(d){const t={};for(const r of d.totals){(t[r.key]??={})[r.kind]=r.value;if(r.kind==="gmax")t[r.key].top=r.top}
const c=(k)=>t[k]?.count||0,avgMs=(k)=>t[k]?.n?t[k].ms/t[k].n:0,avgG=(k)=>t[k]?.gn?t[k].gsum/t[k].gn:0;
if(!$("from").value){$("from").value=d.from;$("to").value=d.to}
for(const [id,name] of [["appSel","app"],["osSel","os"]]){const cur=$(id).value;const vals=[...new Set(d.options.map((o)=>o[name]))];$(id).innerHTML='<option value="">全部</option>'+vals.map((v)=>"<option>"+esc(v)+"</option>").join("");$(id).value=cur}
const pct=(a,b)=>b?Math.round(a*100/b)+"%":"—";
$("tiles").innerHTML=[["活跃安装",fmt(d.active)],["运行次数",fmt(c("runs"))],["章节完成率",pct(c("chapters.done"),c("chapters.total"))],["遇到验证码",fmt(c("captcha.seen"))],["崩溃",fmt(c("app.crash")+c("worker.crash"))],["应用启动",fmt(c("app.start"))]].map(([k,v])=>'<div class="card tile"><span class="sub">'+k+"</span><b>"+v+"</b></div>").join("");
const feats=[["视频","video.ok","video.fail","video.unconfirmed"],["章节检测","workid.ok","workid.fail"],["课件","document.ok","document.fail"],["直播","live.ok","live.fail"],["作业","homework.submitted","homework.failed","homework.saved"]];
$("rates").innerHTML=head(["功能","成功","失败","其他","成功率",""])+feats.map(([n,ok,bad,o])=>{const a=c(ok),b=c(bad),x=o?c(o):0,tot=a+b+x;return row([n,fmt(a),fmt(b),fmt(x),pct(a,tot),'<div class="meter"><i style="width:'+(tot?a*100/tot:0)+'%"></i></div>'])}).join("");
$("stability").innerHTML=head(["项目","次数","每次运行"])+[["遇到验证码","captcha.seen"],["因验证码重新开始","captcha.restart"],["重新登录","relogin"],["章节重试","chapter.retry"],["任务进程异常退出","worker.crash"],["任务卡住","worker.hang"],["自动重新开始","worker.restart"],["运行被停止","run.stopped"],["视频预览失败","preview.fail"],["需要手动完成","other.manual"]].map(([n,k])=>row([n,fmt(c(k)),c("runs")?fmt(c(k)/c("runs")):"—"])).join("");
$("network").innerHTML=head(["项目","数值"])+[["请求次数",fmt(c("net.requests"))],["失败",fmt(c("net.fail"))+"（"+pct(c("net.fail"),c("net.requests"))+"）"],["超时",fmt(c("net.timeout"))],["学习通接口平均耗时",fmt(avgMs("net.cx"))+" ms"],["等待网络恢复",fmt(c("network.wait"))+" 次"],["AI 请求",fmt(c("ai.requests"))+" 次 / "+fmt(c("ai.questions"))+" 题"]].map(row).join("");
$("perf").innerHTML=head(["项目","平均","最大"])+[["内存峰值（MB）","perf.mem_peak_mb"],["CPU 时间（秒）","perf.cpu_s"],["运行时长（秒）","perf.run_s"],["启动时间（秒）","perf.startup_s"],["并行章节数","cfg.jobs"]].map(([n,k])=>row([n,fmt(avgG(k)),fmt(t[k]?.top)])).join("")+[["视频任务平均耗时","task.video"],["章节检测平均耗时","task.workid"],["课件平均耗时","task.document"]].map(([n,k])=>row([n,fmt(avgMs(k)/1000)+" 秒",""])).join("");
$("dist").innerHTML=head(["版本","安装数"])+d.versions.map((v)=>row([esc(v.name),fmt(v.installs)])).join("")+head(["平台","安装数"])+d.systems.map((v)=>row([esc(v.name),fmt(v.installs)])).join("");
$("crashes").innerHTML=d.crashes.length?head(["类型 / 位置","版本","最近","次数"])+d.crashes.map((x)=>{let fr=[];try{fr=JSON.parse(x.frames)}catch{}return row(["<b>"+esc(x.type)+"</b> "+esc(x.message)+"<br><code>"+esc(fr.slice(-3).join(" ← "))+"</code>",esc(x.app),esc(x.last),fmt(x.n)])}).join(""):"<tr><td>这段时间没有崩溃</td></tr>";
const runs={};for(const r of d.daily)if(r.key==="runs")runs[r.day]=r.value;const days=d.installs.map((x)=>x.day);const max=Math.max(1,...d.installs.map((x)=>x.installs),...Object.values(runs));
const line=(vals,color)=>days.length<2?"":'<polyline fill="none" stroke="'+color+'" stroke-width="2" points="'+vals.map((v,i)=>(i*600/(days.length-1)).toFixed(1)+","+(114-v*104/max).toFixed(1)).join(" ")+'"/>';
$("chart").innerHTML=line(d.installs.map((x)=>x.installs),"var(--accent)")+line(days.map((x)=>runs[x]||0),"var(--ok)");
$("chartNote").innerHTML=days.length<2?"不足两天的数据，暂时画不出趋势":'<span style="color:var(--accent)">■</span> 活跃安装　<span style="color:var(--ok)">■</span> 运行次数　'+esc(days[0])+" 至 "+esc(days[days.length-1])+"，最高 "+fmt(max)}
function logout(){token="";sessionStorage.removeItem("t");$("app").classList.add("hide");$("login").classList.remove("hide")}
async function enter(){token=$("token").value.trim();$("loginErr").textContent="";try{await api("/api/summary");sessionStorage.setItem("t",token);$("token").value="";$("login").classList.add("hide");$("app").classList.remove("hide");load()}catch(e){$("loginErr").textContent=e.message}}
$("enter").onclick=enter;$("token").onkeydown=(e)=>{if(e.key==="Enter")enter()};$("load").onclick=load;$("out").onclick=logout;
$("csv").onclick=async()=>{try{const b=await(await api("/api/export.csv?"+query())).blob();const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="xxtplus-telemetry.csv";a.click()}catch(e){$("err").textContent=e.message}};
if(token){$("login").classList.add("hide");$("app").classList.remove("hide");load()}
</script></body></html>`;
