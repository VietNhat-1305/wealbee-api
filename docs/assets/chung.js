// Dùng chung: giải mã gói AES-GCM (khớp wb_api/ma_hoa.py), cổng mật khẩu, định dạng số, biểu đồ SVG nhỏ.
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

const _khoa = {};                               // nhớ khoá đã dẫn theo (muối, mật khẩu): mở nhiều file chỉ chậm lần đầu
async function moGoi(goi, matKhau) {
  const id = goi.salt + '|' + goi.iter + '|' + matKhau;
  if (!_khoa[id]) {
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(matKhau), 'PBKDF2', false, ['deriveKey']);
    _khoa[id] = await crypto.subtle.deriveKey({name: 'PBKDF2', salt: b64(goi.salt), iterations: goi.iter, hash: 'SHA-256'},
      base, {name: 'AES-GCM', length: 256}, false, ['decrypt']);
  }
  const khoa = _khoa[id];
  const pt = await crypto.subtle.decrypt({name: 'AES-GCM', iv: b64(goi.iv)}, khoa, b64(goi.ct));
  return JSON.parse(new TextDecoder().decode(pt));
}

// Cổng mật khẩu: thử mở `url` (gói mã hoá); mật khẩu đúng thì nhớ trong phiên (sessionStorage).
async function congMatKhau(url, khung, tieuDe) {
  const goi = await (await fetch(url, {cache: 'no-store'})).json();
  const thu = async mk => { try { return await moGoi(goi, mk); } catch { return null; } };
  let mk = null; try { mk = sessionStorage.getItem('mk_noi_bo'); } catch {}
  if (mk) { const d = await thu(mk); if (d) return {du_lieu: d, mk}; }
  return new Promise(res => {
    khung.innerHTML = `<div class="gate"><div class="card"><div class="brand" style="justify-content:center"><i>W</i>${esc(tieuDe)}</div>
      <div class="mut sm">Trang nội bộ. Nhập mật khẩu nhóm để xem (dữ liệu được mã hoá, giải mã ngay trên máy bạn).</div>
      <input class="search" id="mk" type="password" placeholder="Mật khẩu" autofocus>
      <button class="btn" id="vao">Mở</button><div class="sm" id="bao" style="color:var(--bad)"></div></div></div>`;
    const vao = async () => { const v = $('#mk').value; $('#bao').textContent = 'Đang giải mã…'; const d = await thu(v);
      if (!d) { $('#bao').textContent = 'Sai mật khẩu'; return; }
      try { sessionStorage.setItem('mk_noi_bo', v); } catch {} res({du_lieu: d, mk: v}); };
    $('#vao').onclick = vao; $('#mk').onkeydown = e => { if (e.key === 'Enter') vao(); };
  });
}

const so = (x, d = 0) => x == null || isNaN(x) ? '—' : Number(x).toLocaleString('vi-VN', {maximumFractionDigits: d, minimumFractionDigits: d});
const ty = x => x == null ? '—' : so(x / 1e9, Math.abs(x) >= 1e12 ? 0 : 1) + ' tỷ';
const pct = (a, b) => (a == null || b == null || b === 0) ? null : (a - b) / Math.abs(b) * 100;
const tg = s => { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? s : d.toLocaleString('vi-VN', {hour12: false}); };
const khoBo = s => String(s ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd');

// Biểu đồ đường: series = [{ten, mau, diem:[[x(ms hoặc số), y]...]}]
function bieuDoDuong(series, {cao = 220, donVi = '', ngay = true} = {}) {
  const W = 760, H = cao, L = 52, R = 12, T = 12, B = 26;
  const all = series.flatMap(s => s.diem.filter(p => p[1] != null));
  if (!all.length) return '<div class="empty sm">Chưa có dữ liệu</div>';
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  let x0 = Math.min(...xs), x1 = Math.max(...xs); if (x0 === x1) { x0 -= 1; x1 += 1; }
  let y0 = Math.min(0, ...ys), y1 = Math.max(...ys) * 1.08 || 1;
  const X = x => L + (x - x0) / (x1 - x0) * (W - L - R), Y = y => T + (1 - (y - y0) / (y1 - y0)) * (H - T - B);
  let g = '';
  for (let i = 0; i <= 4; i++) { const v = y0 + (y1 - y0) * i / 4, y = Y(v);
    g += `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="#1e2a44"/><text x="${L - 6}" y="${y + 4}" text-anchor="end">${so(v, v < 10 ? 1 : 0)}${donVi}</text>`; }
  for (let i = 0; i <= 4; i++) { const v = x0 + (x1 - x0) * i / 4;
    const lab = ngay ? new Date(v).toLocaleDateString('vi-VN', {day: '2-digit', month: '2-digit'}) : so(v);
    g += `<text x="${X(v)}" y="${H - 6}" text-anchor="middle">${lab}</text>`; }
  for (const s of series) {
    const p = s.diem.filter(q => q[1] != null).map(q => `${X(q[0]).toFixed(1)},${Y(q[1]).toFixed(1)}`);
    if (p.length > 1) g += `<polyline fill="none" stroke="${s.mau}" stroke-width="2" stroke-linejoin="round" points="${p.join(' ')}"/>`;
    else if (p.length) g += `<circle cx="${p[0].split(',')[0]}" cy="${p[0].split(',')[1]}" r="3" fill="${s.mau}"/>`;
  }
  return `<svg class="chart" viewBox="0 0 ${W} ${H}">${g}</svg>` +
    (series.length > 1 ? `<div class="legend">${series.map(s => `<span><b style="background:${s.mau}"></b>${esc(s.ten)}</span>`).join('')}</div>` : '');
}

// Biểu đồ cột nhóm: nhan = ['2026Q1',...], nhom = [{ten, mau, gt:[...]}]
function bieuDoCot(nhan, nhom, {cao = 220} = {}) {
  const W = 760, H = cao, L = 58, R = 10, T = 10, B = 26;
  const ys = nhom.flatMap(n => n.gt).filter(v => v != null);
  if (!ys.length) return '<div class="empty sm">Chưa có dữ liệu</div>';
  const y0 = Math.min(0, ...ys), y1 = Math.max(0, ...ys) * 1.1 || 1;
  const Y = y => T + (1 - (y - y0) / (y1 - y0)) * (H - T - B), bw = (W - L - R) / nhan.length;
  let g = '';
  for (let i = 0; i <= 4; i++) { const v = y0 + (y1 - y0) * i / 4;
    g += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#1e2a44"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${so(v / 1e9)}</text>`; }
  nhan.forEach((n, i) => {
    const w = bw * 0.72 / nhom.length;
    nhom.forEach((s, j) => { const v = s.gt[i]; if (v == null) return;
      const x = L + i * bw + bw * 0.14 + j * w, y = Y(Math.max(0, v)), h = Math.abs(Y(v) - Y(0));
      g += `<rect x="${x}" y="${y}" width="${w - 2}" height="${h}" rx="3" fill="${s.mau}"><title>${esc(s.ten)} ${esc(n)}: ${ty(v)}</title></rect>`; });
    g += `<text x="${L + i * bw + bw / 2}" y="${H - 6}" text-anchor="middle">${esc(n)}</text>`;
  });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}">${g}</svg><div class="legend">${nhom.map(s => `<span><b style="background:${s.mau}"></b>${esc(s.ten)} (tỷ đồng)</span>`).join('')}</div>`;
}
