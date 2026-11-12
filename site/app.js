"use strict";
/* HN 片单 — static client. Data: data/index.json (list), data/v/<id>.json (detail), data/meta.json */

const $app = document.getElementById("app");
const state = { index: null, meta: null, shown: 40 };
const FIRST_YEAR = 2007, LAST_YEAR = new Date().getFullYear();

const SORTS = {
  score: { label: "综合评分", fn: (a, b) => b.s - a.s },
  people: { label: "推荐人数", fn: (a, b) => b.r - a.r || b.s - a.s },
  span: { label: "跨越年份", fn: (a, b) => span(b) - span(a) || b.s - a.s },
  oldest: { label: "最早被推荐", fn: (a, b) => a.y[0] - b.y[0] || b.s - a.s },
  latest: { label: "最近仍被推荐", fn: (a, b) => last(b) - last(a) || b.s - a.s },
};
const LENS = {
  any: { label: "任意时长", ok: () => true },
  short: { label: "< 20 分钟", ok: (d) => d && d < 1200 },
  mid: { label: "20–60 分钟", ok: (d) => d && d >= 1200 && d <= 3600 },
  long: { label: "> 1 小时", ok: (d) => d && d > 3600 },
};

function span(v) { return v.y[v.y.length - 1] - v.y[0]; }
function last(v) { return v.y[v.y.length - 1]; }
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function fmtDur(d) {
  if (!d) return "";
  const h = Math.floor(d / 3600), m = Math.round((d % 3600) / 60);
  return h ? `${h} 小时 ${m} 分` : `${m} 分钟`;
}
function hnItem(id) { return `https://news.ycombinator.com/item?id=${encodeURIComponent(id)}`; }
function quoteHtml(x) {
  return esc(x).replace(/\[link\]/g, '<span class="lk" title="原文此处是一个链接">↗</span>').replace(/\n{2,}/g, "</p><p>");
}
function yearOf(t) { return new Date(t * 1000).getUTCFullYear(); }

function parseHash() {
  const h = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = h.split("?");
  return { path, params: new URLSearchParams(qs || "") };
}
function setParams(params) {
  const qs = params.toString();
  history.replaceState(null, "", "#/" + (qs ? "?" + qs : ""));
}

async function loadJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

async function boot() {
  try {
    [state.index, state.meta] = await Promise.all([loadJSON("data/index.json"), loadJSON("data/meta.json")]);
  } catch (e) {
    $app.innerHTML = `<p class="err">数据加载失败：${esc(e.message)}</p>`;
    return;
  }
  const b = document.getElementById("built");
  if (state.meta.exported_at) b.textContent = "数据更新于 " + new Date(state.meta.exported_at * 1000).toISOString().slice(0, 10);
  window.addEventListener("hashchange", route);
  route();
}

function route() {
  const { path, params } = parseHash();
  const m = path.match(/^\/v\/([A-Za-z0-9_-]{11})/);
  if (m) return renderDetail(m[1]);
  if (path.startsWith("/about")) return renderAbout();
  state.shown = 40;
  renderList(params);
}

/* ---------- list ---------- */

function filtered(params) {
  const q = (params.get("q") || "").trim().toLowerCase();
  const topic = params.get("topic") || "";
  const len = LENS[params.get("len")] ? params.get("len") : "any";
  const min = parseInt(params.get("min") || "2", 10);
  const all = params.get("all") === "1";
  const sort = SORTS[params.get("sort")] ? params.get("sort") : "score";
  const durable = params.get("durable") === "1";
  let list = state.index.filter((v) =>
    (all || (v.a && v.k === "knowledge")) &&
    v.r >= min &&
    (!topic || v.tp.includes(topic)) &&
    LENS[len].ok(v.d) &&
    (!durable || span(v) >= 5) &&
    (!q || `${v.t || ""} ${v.c || ""} ${v.q ? v.q.x : ""}`.toLowerCase().includes(q)));
  list = list.slice().sort(SORTS[sort].fn);
  return { list, q, topic, len, min, all, sort, durable };
}

function renderList(params) {
  const f = filtered(params);
  const base = state.index.filter((v) => f.all || (v.a && v.k === "knowledge"));
  const topicCounts = {};
  base.forEach((v) => v.tp.forEach((t) => (topicCounts[t] = (topicCounts[t] || 0) + 1)));
  const topics = Object.entries(topicCounts).sort((a, b) => b[1] - a[1]);
  const meta = state.meta;

  $app.innerHTML = `
  <section class="intro">
    <h1>被反复推荐的 YouTube 知识视频</h1>
    <p class="lede">我们读了 Hacker News 自 2007 年以来 <b>${(meta.comments || 0).toLocaleString()}</b> 条带 YouTube 链接的评论，
    区分出哪些是真正的<em>推荐</em>，而不只是贴个链接。下面的视频，都被<b>不同的人</b>、在<b>不同年份</b>、
    <b>不同话题</b>的讨论里反复推荐过。排序不看播放量、发布时间和标题封面。<a href="#/about">怎么算的？</a></p>
  </section>
  <section class="controls" aria-label="筛选">
    <input id="q" type="search" placeholder="搜索标题、频道或推荐语…" value="${esc(f.q)}" aria-label="搜索">
    <div class="row">
      <label>排序 <select id="sort">${Object.entries(SORTS).map(([k, s]) => `<option value="${k}" ${k === f.sort ? "selected" : ""}>${s.label}</option>`).join("")}</select></label>
      <label>时长 <select id="len">${Object.entries(LENS).map(([k, s]) => `<option value="${k}" ${k === f.len ? "selected" : ""}>${s.label}</option>`).join("")}</select></label>
      <label>至少 <select id="min">${[2, 3, 5, 8].map((n) => `<option value="${n}" ${n === f.min ? "selected" : ""}>${n} 人推荐</option>`).join("")}</select></label>
      <label class="chk"><input id="durable" type="checkbox" ${f.durable ? "checked" : ""}> 推荐跨越 ≥5 年</label>
      <label class="chk"><input id="all" type="checkbox" ${f.all ? "checked" : ""}> 含非知识类 / 已失效</label>
    </div>
    <div class="chips" role="group" aria-label="话题">
      <button class="chip ${!f.topic ? "on" : ""}" data-topic="">全部话题</button>
      ${topics.map(([t, n]) => `<button class="chip ${t === f.topic ? "on" : ""}" data-topic="${esc(t)}">${esc(t)} <small>${n}</small></button>`).join("")}
    </div>
  </section>
  <p class="count">${f.list.length.toLocaleString()} 个视频</p>
  <ol class="list" id="list"></ol>
  <div class="more-wrap"><button id="more" class="more">显示更多</button></div>`;

  const update = (k, v) => {
    const p = parseHash().params;
    if (v === "" || v === null || v === false) p.delete(k); else p.set(k, v === true ? "1" : v);
    setParams(p);
    route();
  };
  let timer;
  const qEl = document.getElementById("q");
  qEl.addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const p = parseHash().params;
      if (e.target.value) p.set("q", e.target.value); else p.delete("q");
      setParams(p);
      const pos = e.target.selectionStart;
      route();
      const n = document.getElementById("q"); n.focus(); n.setSelectionRange(pos, pos);
    }, 220);
  });
  document.getElementById("sort").onchange = (e) => update("sort", e.target.value === "score" ? "" : e.target.value);
  document.getElementById("len").onchange = (e) => update("len", e.target.value === "any" ? "" : e.target.value);
  document.getElementById("min").onchange = (e) => update("min", e.target.value === "2" ? "" : e.target.value);
  document.getElementById("all").onchange = (e) => update("all", e.target.checked);
  document.getElementById("durable").onchange = (e) => update("durable", e.target.checked);
  $app.querySelectorAll(".chip").forEach((b) => (b.onclick = () => update("topic", b.dataset.topic)));

  const draw = () => {
    const ol = document.getElementById("list");
    ol.innerHTML = f.list.slice(0, state.shown).map(cardHtml).join("");
    document.getElementById("more").style.display = f.list.length > state.shown ? "" : "none";
  };
  document.getElementById("more").onclick = () => { state.shown += 40; draw(); };
  draw();
}

function yearStrip(years) {
  const set = new Set(years);
  let cells = "";
  for (let y = FIRST_YEAR; y <= LAST_YEAR; y++) cells += `<i class="${set.has(y) ? "on" : ""}" title="${y}${set.has(y) ? " 有人推荐" : ""}"></i>`;
  return `<span class="years" aria-label="被推荐的年份：${years.join("、")}">${cells}</span>`;
}

function cardHtml(v) {
  const title = v.t || "（视频已不可用）";
  const y0 = v.y[0], y1 = last(v);
  return `<li class="card ${v.a ? "" : "gone"}">
    <a class="thumb" href="#/v/${v.id}" tabindex="-1" aria-hidden="true"><img loading="lazy" src="https://i.ytimg.com/vi/${v.id}/mqdefault.jpg" alt=""></a>
    <div class="body">
      <h2><a href="#/v/${v.id}">${esc(title)}</a></h2>
      <div class="sub">${esc(v.c || "")}${v.d ? ` · ${fmtDur(v.d)}` : ""}${v.cat ? ` · ${esc(v.cat)}` : ""}</div>
      <div class="sig">
        <span class="big"><b>${v.r}</b> 人推荐</span>
        <span><b>${v.th}</b> 个讨论串</span>
        <span>${y0 === y1 ? y0 : `${y0}–${y1}`}</span>
        ${yearStrip(v.y)}
      </div>
      ${v.q ? `<blockquote><p>${quoteHtml(v.q.x)}</p><cite>— <a href="${hnItem(v.q.id)}" rel="noopener" target="_blank">${esc(v.q.u)}</a>, ${v.q.yr}</cite></blockquote>` : ""}
      <div class="foot-row">
        ${v.tp.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}
        <a class="why" href="#/v/${v.id}">看全部 ${v.r} 条推荐理由 →</a>
      </div>
    </div>
  </li>`;
}

/* ---------- detail ---------- */

async function renderDetail(id) {
  window.scrollTo(0, 0);
  $app.innerHTML = `<p class="loading">载入中…</p>`;
  let v;
  try { v = await loadJSON(`data/v/${id}.json`); } catch (e) {
    $app.innerHTML = `<p class="err">没有找到这个视频（${esc(id)}）。<a href="#/">回到片单</a></p>`;
    return;
  }
  document.title = `${v.t || id} · HN 片单`;
  const rank = state.index.findIndex((x) => x.id === id) + 1;
  const byYear = {};
  v.recs.forEach((r) => (byYear[yearOf(r.t)] = (byYear[yearOf(r.t)] || 0) + 1));
  const maxY = Math.max(1, ...Object.values(byYear));
  let bars = "";
  for (let y = FIRST_YEAR; y <= LAST_YEAR; y++) {
    const n = byYear[y] || 0;
    bars += `<div class="bar" title="${y}：${n} 人"><span style="height:${(n / maxY) * 100}%"></span><em>${String(y).slice(2)}</em></div>`;
  }
  const threads = new Set(v.recs.map((r) => r.st)).size;
  $app.innerHTML = `
  <p class="crumb"><a href="#/">← 回到片单</a></p>
  <article class="detail">
    <div class="player" id="player" data-id="${esc(id)}">
      <img src="https://i.ytimg.com/vi/${esc(id)}/hqdefault.jpg" alt="">
      <button class="play" aria-label="播放">▶ 在此播放</button>
    </div>
    <div class="dmeta">
      <h1>${esc(v.t || "（视频已不可用）")}</h1>
      <div class="sub">${esc(v.c || "")}${v.d ? ` · ${fmtDur(v.d)}` : ""}${v.cat ? ` · ${esc(v.cat)}` : ""}${v.pub ? ` · ${v.pub} 年上传` : ""}
        · <a href="https://www.youtube.com/watch?v=${esc(id)}" target="_blank" rel="noopener">在 YouTube 打开</a></div>
      ${v.desc ? `<p class="desc">${esc(v.desc)}</p>` : ""}
      <button class="share" id="share">复制分享链接</button>
    </div>
  </article>
  <section class="why-box">
    <h2>为什么它在这里</h2>
    <ul class="facts">
      <li><b>${v.r}</b><span>位不同的 HN 用户推荐</span></li>
      <li><b>${threads}</b><span>个互不相关的讨论串</span></li>
      <li><b>${v.y.length}</b><span>个不同年份（${v.y[0]}–${last(v)}）</span></li>
      <li><b>${v.tp.length}</b><span>类话题：${v.tp.map(esc).join("、") || "—"}</span></li>
      ${rank ? `<li><b>#${rank}</b><span>综合排名（共 ${state.index.length}）</span></li>` : ""}
    </ul>
    <div class="bars" aria-label="每年推荐人数">${bars}</div>
    ${v.ci ? `<p class="note">另外还有 ${v.ci} 次只是贴出链接（引用、出处、玩笑等），没有计入推荐。</p>` : ""}
  </section>
  <section>
    <h2>他们是怎么说的 <small>按时间排序</small></h2>
    <ol class="recs">
      ${v.recs.map((r) => `<li>
        <div class="rhead"><a href="${hnItem(r.id)}" target="_blank" rel="noopener"><b>${esc(r.u)}</b></a>
          <span>${new Date(r.t * 1000).toISOString().slice(0, 10)}</span>
          <span class="in">在「<a href="${hnItem(r.st)}" target="_blank" rel="noopener">${esc(r.stt || "讨论")}</a>」中</span></div>
        <blockquote><p>${quoteHtml(r.x)}</p></blockquote>
        <div class="cues">${r.cues.filter((c) => c !== "知识型内容").map((c) => `<span>${esc(c)}</span>`).join("")}</div>
      </li>`).join("")}
    </ol>
  </section>
  ${v.cites.length ? `<details class="cites"><summary>只是提到、未计为推荐的 ${v.ci} 条评论</summary><ul>
    ${v.cites.map((c) => `<li><a href="${hnItem(c.id)}" target="_blank" rel="noopener">${esc(c.u)}</a> · ${yearOf(c.t)} · ${esc(c.stt)}<br><span>${quoteHtml(c.x)}</span>${c.neg.length ? ` <em>${c.neg.map(esc).join(" / ")}</em>` : ""}</li>`).join("")}
  </ul></details>` : ""}`;

  document.querySelector("#player .play").onclick = () => {
    document.getElementById("player").innerHTML =
      `<iframe src="https://www.youtube-nocookie.com/embed/${esc(id)}?autoplay=1" title="${esc(v.t || "")}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>`;
  };
  document.getElementById("share").onclick = async (e) => {
    const url = location.href;
    try { await navigator.clipboard.writeText(url); e.target.textContent = "已复制 ✓"; } catch { prompt("复制这个链接：", url); }
  };
}

/* ---------- about ---------- */

function renderAbout() {
  window.scrollTo(0, 0);
  const m = state.meta, ev = m.eval;
  $app.innerHTML = `<article class="about">
  <h1>方法说明</h1>
  <p>一个视频如果被<b>不同的人</b>、在<b>不同的年份</b>、在<b>不同话题</b>的讨论中反复推荐，大概率有长期价值。这个网站就是把这个直觉做成一个可检查的流程。</p>

  <h2>1. 数据</h2>
  <p>通过 HN Algolia 公开 API 抓取了所有包含 <code>youtube.com</code> 或 <code>youtu.be</code> 的评论：共 <b>${(m.comments || 0).toLocaleString()}</b> 条评论、
  <b>${(m.mentions || 0).toLocaleString()}</b> 次视频提及，涉及 <b>${(m.videos || 0).toLocaleString()}</b> 个不同视频。</p>

  <h2>2. “贴链接”不等于“推荐”</h2>
  <p>大多数 YouTube 链接都不是推荐：它们是新闻片段、出处引用、玩笑、音乐、提问，或者作者在推广自己的视频。我们对每一次提及，读取链接附近的文字，用一组透明的规则打分：</p>
  <ul>
    <li><b>加分</b>：明确推荐（“highly recommend”“must watch”“worth your time”）、高度评价（“great talk”“best explanation”“one of my favorites”）、长期影响（“changed how I think”“rewatch every year”）、号召观看（“if you haven't seen it…”）。</li>
    <li><b>减分</b>：自我推广（“I made this video”“my channel”，直接排除）、负面评价（“misleading”“debunked”）、出处/片段（“source:”“footage”）、玩笑梗、提问、音乐娱乐。</li>
  </ul>
  <p>只有得分超过阈值的提及才算作“推荐”。最终只有 <b>${(m.rec_mentions || 0).toLocaleString()}</b> 次提及（约 ${m.mentions ? ((m.rec_mentions / m.mentions) * 100).toFixed(1) : "?"}%）被认定为推荐。</p>
  ${ev && ev.strata ? (() => {
    const P = ev.strata.P, N = ev.strata.N;
    const pp = P.pred_pos + N.pred_pos, ppt = P.pred_pos_true + N.pred_pos_true, pps = P.pred_pos_strong + N.pred_pos_strong;
    return `<p><b>准确性检验</b>：我们分层抽样了 ${ev.n_total_labeled} 条评论，交给一个<b>看不到规则结果</b>的独立标注者（AI 子代理，盲标）逐条判断：强推荐 / 温和推荐 / 不是推荐。
    一半用来调规则，另一半（${ev.n} 条）留作测试，调规则时不看。</p>
    <ul>
      <li><b>精确率</b>：测试集中被规则判为“推荐”的 ${pp} 条里，<b>${ppt} 条（${pct(ppt / pp)}）</b>确实是推荐，其中 ${pps} 条是明确的强推荐。</li>
      <li><b>召回率偏低（有意为之）</b>：随机抽取的“未判为推荐”的评论中，仍有约 ${pct(N.true / N.n)} 被标注者认为是（多为温和的）推荐。
      也就是说规则会漏掉不少语气平淡的推荐，例如 “here's a video about it”。</li>
      <li>这是一个取舍：一个视频要上榜，需要多人独立推荐，漏掉一些不影响“被反复推荐”的视频浮上来；但如果把“只是贴链接”误算成推荐，排名就会被热门新闻片段、梗视频污染。所以我们优先保证精确率。</li>
    </ul>`;
  })() : ""}

  <h2>3. 排序：数人，不数评论</h2>
  <ul>
    <li><b>一人一票</b>：同一个账号多次推荐同一个视频只算一次（取最强的那次）。</li>
    <li><b>同一讨论串打折</b>：同一个讨论串里的第 1、2、3… 位推荐者权重依次为 1、1/2、1/3…——同一串里的人会互相影响，不算完全独立。</li>
    <li><b>跨年份加成</b>：× (1 + 0.35·ln(不同年份数))。十年里一直有人推荐，比某一年突然爆火更说明问题。</li>
    <li><b>跨话题加成</b>：× (1 + 0.15·ln(1 + 话题数))。在编程帖和历史帖里都被人想起，说明它的价值不局限于一时一地。</li>
    <li><b>不参与排序</b>：播放量、发布时间、点赞、标题和封面。</li>
  </ul>
  <p>至少要有 2 个不同的人推荐才会出现在片单中。默认隐藏音乐、喜剧、游戏等非知识类视频，以及已被删除或设为私密的视频（可以在筛选中打开）。</p>

  <h2>4. 局限</h2>
  <ul>
    <li>HN 用户群偏向程序员和创业者，所以片单天然偏技术；“长期价值”在这里是“对 HN 人群的长期价值”。</li>
    <li>规则分类器会漏掉语气含蓄的推荐，也偶尔会把带讽刺的“great video”算进来。每条推荐都附原文链接，欢迎自行判断。</li>
    <li>话题标签来自讨论串标题的关键词匹配，比较粗糙。</li>
    <li>只统计了评论里的链接，没有统计“直接把视频提交为帖子”的情况。</li>
  </ul>
  <p>源代码和完整开发日志：<a href="https://github.com/${esc(m.repo || "")}" target="_blank" rel="noopener">GitHub</a>。</p>
  </article>`;
}
function pct(x) { return x == null ? "?" : Math.round(x * 100) + "%"; }

boot();
