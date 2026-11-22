// Record the Blindgrasp UI (localhost:3000) with headless Chrome via CDP screencast -> JPEG frames + timestamps.
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const OUT = process.argv[2]; mkdirSync(OUT, { recursive: true });
const prof = mkdtempSync(join(tmpdir(), "bgchrome-"));
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ["--headless=new", "--remote-debugging-port=9333", `--user-data-dir=${prof}`, "--window-size=1920,1080",
   "--force-device-scale-factor=1", "--hide-scrollbars", "--no-first-run", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws;
for (let i = 0; i < 50; i++) {
  try { const t = await (await fetch("http://127.0.0.1:9333/json")).json(); const p = t.find((x) => x.type === "page"); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch {}
  await sleep(200);
}
await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pending = new Map(); const frames = [];
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); }
  if (d.method === "Page.screencastFrame") {
    const n = frames.length; writeFileSync(join(OUT, `f${String(n).padStart(5, "0")}.jpg`), Buffer.from(d.params.data, "base64"));
    frames.push(d.params.metadata.timestamp);
    send("Page.screencastFrameAck", { sessionId: d.params.sessionId });
  }
});
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const js = (expression) => send("Runtime.evaluate", { expression, awaitPromise: true });
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: "http://localhost:3000/" }); await sleep(2500);
await js(`localStorage.setItem("bg-intro-seen-v2","1"); localStorage.setItem("bg-panels", JSON.stringify({left:false,right:false,bottom:false}))`);
await send("Page.navigate", { url: "http://localhost:3000/" }); await sleep(5000);
await send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
const click = (label) => js(`(() => { const el = [...document.querySelectorAll("button,[role=button]")].find(b => (b.innerText||b.getAttribute("aria-label")||"").replace(/\\s+/g," ").toLowerCase().includes(${JSON.stringify(label)})); if (el) { el.click(); return "ok " + el.innerText.slice(0,30); } return "missing"; })()`);
await sleep(4000);
console.log("controls", (await click("controls")).result?.value); await sleep(4000);
console.log("readouts", (await click("readouts")).result?.value); await sleep(4000);
console.log("charts", (await click("charts")).result?.value); await sleep(8000);
await send("Page.stopScreencast");
writeFileSync(join(OUT, "times.json"), JSON.stringify(frames));
console.log("frames", frames.length, "span", (frames.at(-1) - frames[0]).toFixed(1), "s");
ws.close(); chrome.kill();
