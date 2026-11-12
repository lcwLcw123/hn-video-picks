# HN 片单 — 被 Hacker News 反复推荐的 YouTube 知识视频

一个静态网站：从 Hacker News 自 2007 年以来所有带 YouTube 链接的评论中，找出**被不同的人、在不同年份、不同话题下反复推荐**的视频，并展示每一条推荐原话。

- 排序不看播放量、发布时间、标题封面
- 区分“推荐”与“只是贴链接”（引用、新闻片段、玩笑、自我推广、批评）
- 每个视频都有可分享的链接：`#/v/<YouTube ID>`

## 结构

```
pipeline/
  crawl_hn.py        HN Algolia 抓取（按时间窗口二分，绕过 1000 条上限，可断点续跑）
  extract.py         从评论 HTML 中提取 YouTube ID 和链接附近的文字
  classify.py        规则打分：这条提及是不是“推荐”，并给出命中的理由
  topics.py          讨论串标题 → 话题标签
  score.py           每个视频的综合分（一人一票 / 同串打折 / 跨年份 / 跨话题）
  build_dataset.py   原始评论 → mentions → 视频聚合
  enrich_youtube.py  YouTube oEmbed + 页面元数据（无需 API Key，带缓存）
  evaluate.py        对照盲标样本评估分类器
  export_site.py     输出网站 JSON
site/                纯静态前端（无构建步骤）
tests/               单元测试
docs/DEVLOG.md       开发日志：决策、问题、解决办法
```

## 重新生成数据

```bash
python3 pipeline/crawl_hn.py youtube.com youtu.be   # 首次约 30–40 分钟；之后增量
python3 pipeline/build_dataset.py
python3 pipeline/enrich_youtube.py data/candidates.json   # 有 YOUTUBE_API_KEY 时走官方 API（推荐）
python3 pipeline/evaluate.py test --save
python3 pipeline/export_site.py
python3 -m unittest discover tests
```

本地预览：`python3 -m http.server -d site 8000`，打开 http://localhost:8000 。

推送到 `main` 后，GitHub Actions 会先跑测试，再把 `site/` 发布到 GitHub Pages。

## YouTube Data API Key（推荐）

没有 Key 时会抓 YouTube 网页 / noembed，容易被限流。有 Key 时：

```bash
export YOUTUBE_API_KEY=你的key
python3 pipeline/enrich_youtube.py data/candidates.json && python3 pipeline/export_site.py
```

约 2,400 个视频只需 ~48 次请求（每次 50 个，每次 1 配额单位；免费额度每天 10,000）。Key 只从环境变量读取，不写入仓库。
