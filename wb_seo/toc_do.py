"""Đo tốc độ trang như Lighthouse bản di động (Chrome thật, CPU chậm 4 lần, mạng 4G chậm), lấy trung vị 3 lần.

LCP, CLS đo trực tiếp bằng PerformanceObserver; TBT (tổng thời gian chặn luồng chính) là chỉ số phòng thí nghiệm
đại diện cho INP (độ trễ tương tác) vì không có người dùng thật bấm vào trang.
"""
from __future__ import annotations

import time

UA_DI_DONG = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
_QUAN_SAT = """(() => { window.__m = {lcp: 0, cls: 0, tbt: 0};
 new PerformanceObserver(l => { for (const e of l.getEntries()) window.__m.lcp = e.startTime; }).observe({type: 'largest-contentful-paint', buffered: true});
 new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__m.cls += e.value; }).observe({type: 'layout-shift', buffered: true});
 new PerformanceObserver(l => { for (const e of l.getEntries()) window.__m.tbt += Math.max(0, e.duration - 50); }).observe({type: 'longtask', buffered: true}); })()"""
_DOC = """() => { const n = performance.getEntriesByType('navigation')[0], f = performance.getEntriesByName('first-contentful-paint')[0];
  const res = performance.getEntriesByType('resource'), sum = g => res.filter(g).reduce((s, r) => s + (r.transferSize || 0), 0);
  return {ttfb: n.responseStart, fcp: f ? f.startTime : null, lcp: window.__m.lcp, cls: window.__m.cls, tbt: window.__m.tbt,
          kb: (sum(() => true) + n.transferSize) / 1024, so_request: res.length + 1,
          font_kb: sum(r => /\\.(woff2?|ttf)(\\?|$)/.test(r.name)) / 1024, js_kb: sum(r => /\\.js(\\?|$)/.test(r.name)) / 1024}; }"""


def do(urls: dict[str, str], lan: int = 3) -> dict:
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:  # noqa: BLE001 - máy không có Chrome cài sẵn: dùng Chromium của Playwright
            b = p.chromium.launch()
        for ten, url in urls.items():
            vals = []
            for _ in range(lan):
                ctx = b.new_context(viewport={"width": 412, "height": 823}, user_agent=UA_DI_DONG, device_scale_factor=2.6, is_mobile=True, has_touch=True)
                pg = ctx.new_page()
                cdp = ctx.new_cdp_session(pg)
                cdp.send("Network.enable")
                cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150, "downloadThroughput": 1.6 * 1024 * 1024 / 8,
                                                             "uploadThroughput": 750 * 1024 / 8})
                cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                pg.add_init_script(_QUAN_SAT)
                try:
                    pg.goto(url, wait_until="load", timeout=90000)
                    time.sleep(6)
                    vals.append(pg.evaluate(_DOC))
                except Exception as e:  # noqa: BLE001
                    out.setdefault(ten + "_loi", str(e)[:120])
                ctx.close()
            if vals:
                out[ten] = {k: round(sorted(v[k] or 0 for v in vals)[len(vals) // 2], 3 if k == "cls" else 0) for k in vals[0]}
                out[ten]["url"] = url
        b.close()
    return out
