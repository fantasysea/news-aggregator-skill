# News Aggregator Skill

通用多源新闻聚合 Skill，面向 AI / 技术 / 开源 / 财经场景。

## 功能特性

- 多源聚合：覆盖科技、开源、财经、社交热榜与扩展 RSS。
- 结果增强：去重、规则排序、可选二次重排。
- 深度解读：支持正文抓取与结构化摘要。
- 对话优先：默认使用自然语言，不需要记参数。

## 支持信源

- Core：Hacker News、GitHub Trending、Product Hunt、36Kr、腾讯新闻、华尔街见闻、微博、V2EX。
- Trend 扩展：头条、百度、知乎、抖音、微博等热榜渠道。
- RSS+ 扩展：技术与 AI 站点（可按需扩展）。

## 安装

### 0) NPM 一键安装（推荐）

无需手动复制文件：

```bash
npx @fantasysea/news-aggregator-skill install
```

只安装到 Claude Code：

```bash
npx @fantasysea/news-aggregator-skill install --target claude
```

只安装到 OpenCode：

```bash
npx @fantasysea/news-aggregator-skill install --target opencode
```

安装到自定义目录：

```bash
npx @fantasysea/news-aggregator-skill install --dir ~/.claude/skills/news-aggregator-skill
```

可选全局安装：

```bash
npm i -g @fantasysea/news-aggregator-skill
news-aggregator-skill install
```

### 1) 安装到 Claude Code

将本目录复制到：

- `~/.claude/skills/news-aggregator-skill`

### 2) 安装到 OpenCode

将本目录复制到：

- `~/.config/opencode/skills/news-aggregator-skill`

### 3) 安装依赖

进入 skill 目录执行：

```bash
pip install -r requirements.txt
```

## 使用

### 对话方式（推荐）

- 直接说：`news-aggregator-skill 如意如意`（打开菜单）
- 或直接提需求：
  - `帮我看今天的 AI 新闻`
  - `全网扫描今天科技热点`
  - `给我国内科技和市场的重点新闻`
  - `只看最重要的 5 条并说明原因`

### 输出内容（默认）

每条新闻通常包含：

- 标题（链接）
- 来源、时间、热度/评分
- 简要摘要
- 自动生成主题标签（3-5 个）

## 目录结构

- `package.json`：npm 包与 CLI 入口定义
- `bin/cli.mjs`：安装命令行（copy 到 Claude/OpenCode）
- `SKILL.md`：交互规则与执行策略
- `templates.md`：菜单模板
- `scripts/fetch_news.py`：抓取与处理逻辑
- `requirements.txt`：Python 依赖

## 说明

- 开源版为通用配置，不依赖个人记忆文件。
- 主题标签自动生成，不绑定固定白名单。
