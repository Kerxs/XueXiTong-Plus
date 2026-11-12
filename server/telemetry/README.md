# 学习通 PLUS 匿名统计后台

一个 Cloudflare Worker：接收应用上报的匿名统计，存进 D1 数据库，并提供一个带密码的管理页面。免费额度足够（Workers 每天 10 万次请求，D1 每天 10 万次写入）。

| 文件 | 作用 |
|---|---|
| `worker.js` | 接收接口、汇总接口、管理页面、每天清理 |
| `schema.sql` | 数据库表 |
| `wrangler.toml` | 部署配置 |
| `test/worker.test.js` | 自动测试（`node --test test/`，需要 Node 22.5 以上） |
| `test/dev-server.js` | 不用 Cloudflare 的本机预览 |

## 部署（约 10 分钟，用你自己的 Cloudflare 账号）

需要 Node.js。在这个目录里执行：

```bash
npx wrangler login
```

```bash
npx wrangler d1 create xxtplus-telemetry
```

把输出里的 `database_id` 填进 `wrangler.toml`，然后建表：

```bash
npx wrangler d1 execute xxtplus-telemetry --remote --file=schema.sql
```

设置管理密码（至少 12 位，自己记好；不到 12 位时管理页面一律拒绝）：

```bash
npx wrangler secret put ADMIN_TOKEN
```

发布：

```bash
npx wrangler deploy
```

发布后会得到一个地址，例如 `https://xxtplus-telemetry.<你的子域>.workers.dev`。

- 管理页面：打开这个地址，输入管理密码。
- 上报地址：这个地址加上 `/v1/report`。

**建议绑定自己的域名**（Cloudflare 控制台 → Workers → 你的 Worker → Settings → Domains & Routes）：`workers.dev` 在国内经常连不上，连不上时应用不受影响，只是数据传不上来。

## 让应用开始上传

把上报地址填进 `api/telemetry.py` 的 `TELEMETRY_URL`，然后重新构建并发布应用：

```python
TELEMETRY_URL = "https://你的域名/v1/report"
```

这个地址为空时，应用不上传任何东西，统计只留在用户本机。地址必须是 https。

## 本机预览

```bash
node test/dev-server.js 8787 --sample
```

打开 `http://127.0.0.1:8787`，密码 `local-preview-password`。`--sample` 会放入一些假数据。
要让本机运行的应用上报到它，启动应用前设置环境变量 `XXTPLUS_TELEMETRY_URL=http://127.0.0.1:8787/v1/report`。

## 接口

| 接口 | 说明 |
|---|---|
| `POST /v1/report` | 上报。不需要密钥。只接受白名单里的数字，其余整条拒绝；每个安装每小时最多 30 条；单条不超过 16 KB |
| `GET /` | 管理页面（页面本身不含数据） |
| `GET /api/summary?from=&to=&app=&os=` | 汇总数据，需要 `Authorization: Bearer <管理密码>` |
| `GET /api/export.csv?…` | 导出聚合数据，同上 |

## 保存什么

- `installs`：每天每个随机安装编号一行，带版本和系统。
- `metrics`：按 天 / 版本 / 系统 / 项目 聚合的次数、耗时、大小。
- `crashes`：异常类型、脱敏后的消息、程序内的代码位置。
- `rate`：限速用，只留两天。

不读取也不保存 IP 地址；`wrangler.toml` 里关闭了请求日志。超过 90 天（`RETENTION_DAYS`）的数据每天自动删除。

应用端收集和脱敏的规则在 `api/telemetry.py`，对用户的说明在仓库根目录的 `PRIVACY.md`。
