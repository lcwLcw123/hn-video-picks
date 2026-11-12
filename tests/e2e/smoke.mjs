// Headless smoke test for the static site. Usage: node tests/e2e/smoke.mjs [baseURL] [outDir]
// Needs playwright-core (NODE_PATH) and a local Chrome.
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");
const base = process.argv[2] || "http://localhost:8765/";
const out = process.argv[3] || "/tmp";
const exe = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ executablePath: exe, headless: true });
const fail = (m) => { console.error("FAIL:", m); process.exitCode = 1; };
const errors = [];
for (const vp of [{ name: "desktop", width: 1280, height: 900 }, { name: "mobile", width: 390, height: 844 }]) {
  const page = await browser.newPage({ viewport: vp });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/i\.ytimg|youtube/.test(m.text()) && errors.push(m.text()));
  await page.goto(base, { waitUntil: "networkidle" });
  const n = await page.locator(".card").count();
  if (n < 10) fail(`${vp.name}: only ${n} cards`);
  await page.screenshot({ path: `${out}/list-${vp.name}.png` });
  if (vp.name === "desktop") {
    // filter by topic chip, search, sort; state must go into the URL (shareable)
    await page.locator(".chip").nth(1).click();
    if (!/topic=/.test(page.url())) fail("topic not in URL");
    await page.selectOption("#sort", "span");
    if (!/sort=span/.test(page.url())) fail("sort not in URL");
    await page.goto(base + "#/?q=hickey", { waitUntil: "networkidle" });
    const titles = await page.locator(".card h2").allTextContents();
    if (!titles.some((t) => /hickey/i.test(t))) fail("search hickey: " + titles.slice(0, 3));
    console.log("search hickey ->", titles.slice(0, 3));
    // detail page
    await page.locator(".card h2 a").first().click();
    await page.waitForSelector(".recs li");
    const recs = await page.locator(".recs li").count();
    const facts = await page.locator(".facts li b").first().textContent();
    if (String(recs) !== facts.trim()) fail(`recs ${recs} != recommenders ${facts}`);
    await page.screenshot({ path: `${out}/detail.png`, fullPage: false });
    await page.goto(base + "#/about", { waitUntil: "networkidle" });
    if (!(await page.locator(".about h1").count())) fail("about page");
    await page.screenshot({ path: `${out}/about.png`, fullPage: true });
    page.removeAllListeners("console"); // the next step 404s on purpose
    await page.goto(base + "#/v/zzzzzzzzzzz", { waitUntil: "networkidle" });
    if (!(await page.locator(".err").count())) fail("missing video should show error");
  }
  await page.close();
}
if (errors.length) fail("page errors: " + errors.join(" | "));
await browser.close();
console.log(process.exitCode ? "SMOKE FAILED" : "SMOKE OK");
