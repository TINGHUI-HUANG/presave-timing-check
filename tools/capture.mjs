// Render the system diagram and capture storyboard screens from the running prototype, using
// headless Microsoft Edge through the Chrome DevTools Protocol. Node 22+ (built-in fetch and
// WebSocket); no packages.
//
//   node tools/capture.mjs --diagram          docs/system_diagram.svg -> docs/system_diagram.png
//   node tools/capture.mjs --stories          app must run on http://localhost:8020 -> docs/screens/*.png
//   node tools/capture.mjs --stories s2       one story only
//
// The clicks are scripted; every request sends "X-Driver: capture-script", so the session log
// tells these runs apart from a person's. The system's responses on screen are real.

import { spawn } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EDGE = process.env.EDGE_PATH || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const APP = process.env.APP_URL || "http://localhost:8020";
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Each story is a list of steps: an action, then the cards to capture together as one frame.
const STORIES = {
  s1: [
    { act: ["example", "B"], frame: ["compose"] },
    { act: ["create"], frame: ["request", "question"] },
    { act: ["choice", "question", "yes"], frame: ["done-1", "question"] },
    { act: ["choice", "question", "yes"], frame: ["done-2", "repair"] },
    { act: ["choice", "repair", "add"], frame: ["confirm"] },
    { act: ["choice", "confirm", "save"], frame: ["saved"] },
  ],
};

async function launch(width, height) {
  const profile = join(os.tmpdir(), `iis-capture-${process.pid}`);
  const edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    "--no-first-run", "--disable-gpu", "--hide-scrollbars", "--remote-allow-origins=*",
    `--window-size=${width},${height}`, "about:blank"], { stdio: "ignore" });
  let target;
  for (let i = 0; i < 60 && !target; i++) {
    await sleep(250);
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      target = list.find((t) => t.type === "page");
    } catch { /* not up yet */ }
  }
  if (!target) throw new Error("Edge did not start (set EDGE_PATH if it is installed elsewhere)");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  let next = 0;
  const pending = new Map();
  const events = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    else events.forEach((f) => f(msg));
  };
  const send = (method, params = {}) => new Promise((ok, fail) => {
    const id = ++next;
    pending.set(id, (msg) => (msg.error ? fail(new Error(`${method}: ${msg.error.message}`)) : ok(msg.result)));
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 2, mobile: false });
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || expression);
    return r.result.value;
  };
  const navigate = async (url) => {
    const loaded = new Promise((ok) => {
      const f = (msg) => { if (msg.method === "Page.loadEventFired") { events.splice(events.indexOf(f), 1); ok(); } };
      events.push(f);
    });
    await send("Page.navigate", { url });
    await loaded;
    await sleep(500);
  };
  const shot = async (file, clip) => {
    const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      ...(clip ? { clip: { ...clip, scale: 1 } } : {}) });
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, Buffer.from(r.data, "base64"));
    console.log("wrote", file.slice(ROOT.length + 1));
  };
  const close = async () => {
    try { await send("Browser.close"); } catch { /* already closed */ }
    ws.close();
    edge.kill();
    await sleep(500);
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* left for the OS to clean */ }
  };
  return { evaluate, navigate, shot, close };
}

async function diagram() {
  const b = await launch(940, 1030);
  try {
    await b.navigate(pathToFileURL(join(ROOT, "docs", "system_diagram.svg")).href);
    await b.shot(join(ROOT, "docs", "system_diagram.png"), { x: 0, y: 0, width: 940, height: 1030 });
  } finally { await b.close(); }
}

const ACT = {
  example: (id) => `document.querySelector('[data-example="${id}"]').click()`,
  type: (text) => `document.querySelector('#req').value = ${JSON.stringify(text)}`,
  create: () => `document.querySelector('#create').click()`,
  choice: (card, value) => `document.querySelector('[data-test="${card}"] button[data-choice="${value}"]').click()`,
};

async function story(b, name, steps) {
  await b.navigate(APP);
  // Mark every request from this page as scripted, for the session log.
  await b.evaluate(`(() => { const f = window.fetch; window.fetch = (u, o = {}) =>
    f(u, { ...o, headers: { ...(o.headers || {}), "X-Driver": "capture-script" } }); return true; })()`);
  for (const [n, step] of steps.entries()) {
    const [kind, ...args] = step.act;
    const before = await b.evaluate(`document.querySelector('#thread').innerHTML.length`);
    await b.evaluate(ACT[kind](...args));
    if (kind !== "example" && kind !== "type") {
      for (let i = 0; i < 120; i++) {   // wait for the response to render (a live call can take seconds)
        await sleep(250);
        const ready = await b.evaluate(`!document.querySelector('.spin') && document.querySelector('#thread').innerHTML.length !== ${before}`);
        if (ready) break;
      }
      await sleep(300);
    }
    const clip = await b.evaluate(`(() => {
      window.scrollTo(0, 0);
      const els = ${JSON.stringify(step.frame)}.map((t) => document.querySelector('[data-test="' + t + '"]')).filter(Boolean);
      if (!els.length) return null;
      const rs = els.map((e) => e.getBoundingClientRect());
      const top = Math.min(...rs.map((r) => r.top)) - 8, bottom = Math.max(...rs.map((r) => r.bottom)) + 8;
      const left = Math.min(...rs.map((r) => r.left)) - 8, right = Math.max(...rs.map((r) => r.right)) + 8;
      return { x: left + scrollX, y: top + scrollY, width: right - left, height: bottom - top };
    })()`);
    if (!clip) throw new Error(`${name} step ${n + 1}: none of ${step.frame.join(", ")} is on screen`);
    await b.shot(join(ROOT, "docs", "screens", `${name}_${n + 1}.png`), clip);
  }
}

async function stories(only) {
  const b = await launch(820, 1400);
  try {
    for (const [name, steps] of Object.entries(STORIES)) {
      if (!only || only === name) await story(b, name, steps);
    }
  } finally { await b.close(); }
}

const [flag, arg] = process.argv.slice(2);
if (flag === "--diagram") await diagram();
else if (flag === "--stories") await stories(arg);
else console.log("usage: node tools/capture.mjs --diagram | --stories [name]");
