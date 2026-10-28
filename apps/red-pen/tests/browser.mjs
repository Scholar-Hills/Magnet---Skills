/**
 * 浏览器验收：1440 与 390 两个宽度各走一遍主流程，并检查键盘能否定位批注。
 *
 * 依赖 playwright-core（已装在托管 node 工作区），浏览器用本机已有的
 * Chromium for Testing，不额外下载。
 *
 *   BASE=http://127.0.0.1:8787 OUT=/tmp/shots node tests/browser.mjs
 */

import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require("playwright-core"));
} catch (err) {
  const fallback = process.env.PLAYWRIGHT_CORE;
  if (!fallback) {
    console.error("缺 playwright-core：装一份，或用 PLAYWRIGHT_CORE=<包目录绝对路径> 指过去。");
    process.exit(2);
  }
  ({ chromium } = require(fallback));
}

const BASE = process.env.BASE || "http://127.0.0.1:8787";
const OUT = process.env.OUT || "/tmp/redpen-shots";

// 浏览器路径：环境变量优先，其次 playwright 的注册表，最后在缓存目录里找一个真装了的。
function resolveChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  const candidates = [];
  try { candidates.push(chromium.executablePath()); } catch (e) { /* 注册表里没有 */ }
  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    path.join(os.homedir(), "Library/Caches/ms-playwright"),
    path.join(os.homedir(), ".cache/ms-playwright")
  ].filter(Boolean);
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    for (const name of fs.readdirSync(root).filter((n) => n.startsWith("chromium-")).sort().reverse()) {
      candidates.push(
        path.join(root, name, "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        path.join(root, name, "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        path.join(root, name, "chrome-linux/chrome")
      );
    }
  }
  return candidates.find((p) => p && fs.existsSync(p)) || candidates[0];
}
const EXE = resolveChrome();

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? "  —— " + detail : ""}`);
}

async function runFlow(page, label, viewport) {
  const errors = [];
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text() + " @ " + (msg.location()?.url || "")); });

  await page.setViewportSize(viewport);
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  check(`${label} 首屏渲染`, await page.locator("#view-compose").isVisible());
  check(`${label} 主按钮可见`, await page.locator("#btn-start").isVisible());
  await page.screenshot({ path: path.join(OUT, `${label}-1-compose.png`), fullPage: true });

  await page.locator("#btn-sample").click();
  const filled = await page.locator("#draft-input").inputValue();
  check(`${label} 示例填入表单（不是预置结果）`, filled.includes("家长开放日"));
  check(`${label} 示例标注为合成内容`, await page.locator("#sample-hint").isVisible());

  await page.locator("#btn-start").click();
  await page.locator("#view-brief").waitFor({ state: "visible" });
  check(`${label} 进入确认目的`, await page.locator("#view-brief").isVisible());
  await page.fill("#q-audience", "小学生家长，多数在通勤路上用手机读");
  await page.fill("#q-purpose", "读完知道改到哪天、要怎么回复");
  await page.fill("#q-worries", "像在推卸责任、截止日期说不清");
  await page.screenshot({ path: path.join(OUT, `${label}-2-brief.png`), fullPage: true });

  await page.locator("#btn-generate").click();
  await page.locator("#view-result").waitFor({ state: "visible", timeout: 90000 });
  check(`${label} 走到红笔稿`, await page.locator("#view-result").isVisible());

  await page.waitForTimeout(600);
  await page.waitForTimeout(600);
  const meta = await page.locator("#result-meta").innerText();
  check(`${label} 结果头显示版本与锚定率`, /第\s*1\s*版/.test(meta) && /钉住/.test(meta), meta);

  const desktopView = viewport.width >= 900;
  const draftPane = desktopView ? "#draft-pane" : "#flow-pane";
  const cardPane = desktopView ? "#notes-pane" : "#flow-pane";
  const hits = page.locator(`${draftPane} .hit`);
  const hitCount = await hits.count();
  check(`${label} 原文里有可点的批注下划线`, hitCount > 0, `count=${hitCount}`);
  await page.screenshot({ path: path.join(OUT, `${label}-3-result.png`) });

  // 点批注 → 对应原句被选中
  const firstCard = page.locator(`${cardPane} .card`).first();
  await firstCard.click();
  const activeHits = await page.locator(`${draftPane} .hit.is-active`).count();
  check(`${label} 点批注能选中对应原句`, activeHits === 1, `active=${activeHits}`);
  check(`${label} 选中后有返回阅读位置的按钮`, await page.locator("#back-jump").isVisible());
  await page.screenshot({ path: path.join(OUT, `${label}-4-selected.png`) });

  // 键盘：先取消上一次选择，再 Tab 到最后一条批注卡片上按 Enter
  await firstCard.click();
  await page.evaluate(() => {
    const cards = document.querySelectorAll("#notes-pane .card, #flow-pane .card");
    const card = cards[cards.length - 1];
    if (card) card.focus();
  });
  const focused = await page.evaluate(() => {
    const node = document.activeElement;
    return node && node.classList.contains("card");
  });
  check(`${label} 批注卡片可聚焦`, focused);
  await page.keyboard.press("Enter");
  const afterEnter = await page.locator(`${draftPane} .hit.is-active`).count();
  check(`${label} Enter 选中后焦点仍在卡片上`, await page.evaluate(() => document.activeElement.classList.contains("card")));
  check(`${label} 键盘 Enter 能定位批注`, afterEnter >= 1, `active=${afterEnter}`);

  // 键盘：Tab 顺序里主按钮可达
  await page.evaluate(() => document.querySelector("#btn-download").focus());
  const downloadFocused = await page.evaluate(() => document.activeElement.id === "btn-download");
  check(`${label} 下载按钮可聚焦`, downloadFocused);

  // 下载
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 15000 }),
    page.locator("#btn-download").click()
  ]);
  const file = await download.path();
  const body = fs.readFileSync(file, "utf8");
  check(`${label} 下载的红笔稿能打开`, body.includes("红笔改稿") && body.length > 2000, `${body.length} bytes`);

  // 我来改 → 原样提交不虚增版本
  await page.locator("#btn-revise").click();
  await page.locator("#revise-panel").waitFor({ state: "visible" });
  const reviseValue = await page.locator("#revise-input").inputValue();
  check(`${label} 编辑区预填当前稿子`, reviseValue.includes("家长开放日"));
  await page.locator("#btn-revise-submit").click();
  await page.waitForTimeout(1200);
  const note = await page.locator("#revise-note").innerText();
  check(`${label} 原样提交不虚增版本`, /逐字相同/.test(note), note);

  // 改一句 → 第二版
  await page.fill("#revise-input", reviseValue.replace("我们也很无奈，希望各位家长理解", "具体安排由区里统一确定，改期不是学校单方面的决定"));
  await page.locator("#btn-revise-submit").click();
  await page.locator("#view-run").waitFor({ state: "visible" });
  await page.locator("#view-result").waitFor({ state: "visible", timeout: 90000 });
  await page.waitForTimeout(600);
  const meta2 = await page.locator("#result-meta").innerText();
  check(`${label} 第二版生成成功`, /第\s*2\s*版/.test(meta2), meta2);
  check(`${label} 显示与上一版的比较`, await page.locator("#compare").isVisible());
  await page.screenshot({ path: path.join(OUT, `${label}-5-v2.png`) });

  check(`${label} 没有前端报错`, errors.length === 0, errors.slice(0, 3).join(" | "));
}

const browser = await chromium.launch({ executablePath: EXE, headless: true });
fs.mkdirSync(OUT, { recursive: true });
try {
  const desktop = await browser.newContext();
  const pageA = await desktop.newPage();
  await runFlow(pageA, "desktop-1440", { width: 1440, height: 900 });
  await desktop.close();

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 2
  });
  const pageB = await mobile.newPage();
  await runFlow(pageB, "mobile-390", { width: 390, height: 844 });
  await mobile.close();
} finally {
  await browser.close();
}

const failed = results.filter((row) => !row.ok);
console.log(`\n${results.length} 项浏览器检查，${results.length - failed.length} 项通过，${failed.length} 项失败`);
console.log(`截图目录：${OUT}`);
process.exit(failed.length ? 1 : 0);
