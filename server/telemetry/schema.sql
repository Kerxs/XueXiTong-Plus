-- 学习通 PLUS 匿名统计：Cloudflare D1 (SQLite)。
-- 没有任何一列保存 IP、账号、课程或题目。install 是客户端随机生成的编号。

-- 每天每个安装一行：活跃安装数、版本和系统分布。
CREATE TABLE IF NOT EXISTS installs (
  day     TEXT NOT NULL,
  install TEXT NOT NULL,
  app     TEXT NOT NULL,
  os      TEXT NOT NULL,
  reports INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, install)
);

-- 按 天 / 版本 / 系统 / 项目 聚合的数值。
--   kind = count    value = 次数
--   kind = ms / n   耗时合计（毫秒）和次数（平均 = ms / n）
--   kind = gsum / gn / gmax   数值类（内存、启动时间）的合计、份数和最大值
CREATE TABLE IF NOT EXISTS metrics (
  day   TEXT NOT NULL,
  app   TEXT NOT NULL,
  os    TEXT NOT NULL,
  key   TEXT NOT NULL,
  kind  TEXT NOT NULL,
  value REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (day, app, os, key, kind)
);
CREATE INDEX IF NOT EXISTS metrics_day ON metrics (day);

-- 崩溃：异常类型、脱敏后的消息、程序内的代码位置。
CREATE TABLE IF NOT EXISTS crashes (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  day     TEXT NOT NULL,
  app     TEXT NOT NULL,
  os      TEXT NOT NULL,
  proc    TEXT NOT NULL,
  type    TEXT NOT NULL,
  message TEXT NOT NULL,
  frames  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS crashes_day ON crashes (day);

-- 限速：每个安装每小时的上报次数（只保留两天）。
CREATE TABLE IF NOT EXISTS rate (
  install TEXT NOT NULL,
  hour    TEXT NOT NULL,
  n       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (install, hour)
);
