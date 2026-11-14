// Phân tích đầu tư chủ động: luồng tín hiệu + bộ lọc đa yếu tố + danh mục theo dõi + thẻ quyết định từng mã.
// Dữ liệu dựng mỗi giờ bởi wb_api/dau_tu.py (docs/dau-tu/data). Các biến toàn cục CH, D, NGANH, nhanKhoa, tai, taiJson
// trùng tên với tra-cuu.js vì trợ lý AI (ai.js) dùng chúng để đọc BCTC / tin của web Doanh nghiệp.
const CH = window.CAU_HINH;
const NGANH = {corporate: 'Doanh nghiệp', bank: 'Ngân hàng', securities: 'Chứng khoán', insurance: 'Bảo hiểm'};
const NHAN = {revenue: 'Doanh thu', gross_profit: 'Lợi nhuận gộp', net_profit: 'Lợi nhuận sau thuế', cost_of_sales: 'Giá vốn',
  total_assets: 'Tổng tài sản', total_liabilities: 'Nợ phải trả', equity: 'Vốn chủ sở hữu', borrowings: 'Vay nợ',
  operating: 'LCTT từ hoạt động kinh doanh', investing: 'LCTT từ hoạt động đầu tư', financing: 'LCTT từ hoạt động tài chính',
  net_change: 'Lưu chuyển tiền thuần trong kỳ', net_profit_parent: 'LNST của cổ đông công ty mẹ'};
const nhanKhoa = k => NHAN[k] || k.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
let D = {idx: null, cty: {}, mk: null, ma: {}, chon: null};
const DL = '../doanh-nghiep/data/';
async function tai(ten) { const r = await fetch(`${DL}${ten}.json`, {cache: 'no-store'}); return r.ok ? r.json() : null; }
const taiJson = u => fetch(u, {cache: 'no-store'}).then(r => r.ok ? r.json() : null).catch(() => null);

const YT = [['tang_truong', 'Tăng trưởng'], ['hieu_qua', 'Hiệu quả'], ['an_toan', 'An toàn tài chính'], ['chat_luong', 'Chất lượng lợi nhuận'], ['tin_tuc', 'Tin tức']];
const CS = {dt_q: ['DT quý so cùng kỳ', '%'], ln_q: ['LNST quý so cùng kỳ', '%'], dt_lk: ['DT luỹ kế so cùng kỳ', '%'], ln_lk: ['LNST luỹ kế so cùng kỳ', '%'],
  roe: ['ROE năm hoá', '%'], roa: ['ROA năm hoá', '%'], bien_gop: ['Biên LN gộp quý', '%'], bien_rong: ['Biên LNST quý', '%'],
  no_vcsh: ['Nợ phải trả / VCSH', ' lần'], vay_vcsh: ['Vay / VCSH', ' lần'], suc_khoe: ['Điểm sức khoẻ Wealbee', '/10'],
  cfo_ln: ['LCTT kinh doanh / LNST luỹ kế', ' lần'], tin: ['Sắc thái tin 30 ngày', '']};
const LOAI = {ln_tang: 'Lợi nhuận tăng mạnh', ln_giam: 'Lợi nhuận giảm mạnh', lo_sang_lai: 'Có lãi trở lại', lai_sang_lo: 'Chuyển sang lỗ',
  suc_khoe_tang: 'Sức khoẻ tài chính tăng', suc_khoe_giam: 'Sức khoẻ tài chính giảm', cfo_am: 'Dòng tiền KD âm', no_vay_tang: 'Nợ vay tăng mạnh',
  tin_tich_cuc: 'Tin tích cực', tin_tieu_cuc: 'Tin tiêu cực'};
const MUC = {tich_cuc: ['Tích cực', 'up'], tieu_cuc: ['Tiêu cực', 'down'], canh_bao: ['Cảnh báo', 'warn']};
const S = {diem: null, th: null, tab: 'tin_hieu', loc: {muc: '', loai: '', nguon: '', q: '', chiTheoDoi: false, ngay: 30, gioiHan: 60},
  bl: {preset: 'tat_ca', min: {tong: 0, tang_truong: 0, hieu_qua: 0, an_toan: 0, chat_luong: 0, tin_tuc: 0}, nganh: '', san: '', verified: false,
    sap: 'd', giam: true, trang: 0}, gia: {}};
const kho = {get: k => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }};
let THEO_DOI = new Set(kho.get('dau_tu_theo_doi') || []);
const luuTD = () => kho.set('dau_tu_theo_doi', [...THEO_DOI]);
const pt = x => x == null ? '—' : (Math.round(x * 10) / 10).toLocaleString('vi-VN');
const dau = x => x == null ? '—' : (x > 0 ? '+' : '') + pt(x) + '%';
const lnq = m => m.ln_dao === 1 ? 'lỗ → lãi' : m.ln_dao === -1 ? 'lãi → lỗ' : m.ln_q >= 300 ? '> +300%' : dau(m.ln_q);   // 300 = mức trần khi xếp hạng
const lopD = d => d == null ? 'mut2' : d >= 70 ? 'dt-cao' : d >= 40 ? 'dt-vua' : 'dt-thap';
const ngayVN = s => { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleDateString('vi-VN', {day: '2-digit', month: '2-digit', timeZone: 'Asia/Ho_Chi_Minh'}); };
const gioVN = s => { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleString('vi-VN', {hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', hour12: false, timeZone: 'Asia/Ho_Chi_Minh'}); };
const sao = m => `<button class="dt-sao ${THEO_DOI.has(m) ? 'on' : ''}" data-sao="${esc(m)}" title="${THEO_DOI.has(m) ? 'Bỏ theo dõi' : 'Theo dõi mã này'}">${THEO_DOI.has(m) ? '★' : '☆'}</button>`;

async function main() {
  const [diem, th, idx, ct] = await Promise.all([taiJson('data/diem.json'), taiJson('data/tin_hieu.json'), tai('index'), tai('cong_ty')]);
  if (!diem || !th) { $('#app').innerHTML = '<div class="card empty">Chưa có dữ liệu phân tích. Hệ thống dựng lại mỗi giờ.</div>'; return; }
  S.diem = diem; S.th = th.ds || []; D.idx = idx; for (const c of (ct?.ds || [])) D.cty[c.ticker] = c;
  ve();
  window.AI?.gan();
  document.addEventListener('click', e => {
    const s = e.target.closest('[data-sao]'); if (s) { e.stopPropagation(); doiSao(s.dataset.sao); return; }
    const m = e.target.closest('[data-ma]'); if (m && !e.target.closest('a')) moThe(m.dataset.ma);
  });
  window.onhashchange = () => { const m = location.hash.slice(1).toUpperCase(); if (S.diem.ds[m]) moThe(m); };
  window.onhashchange();
}

function doiSao(m) {
  THEO_DOI.has(m) ? THEO_DOI.delete(m) : THEO_DOI.add(m); luuTD();
  for (const b of document.querySelectorAll(`[data-sao="${m}"]`)) { const on = THEO_DOI.has(m); b.classList.toggle('on', on); b.textContent = on ? '★' : '☆'; }
  const n = $('#dt-n-td'); if (n) n.textContent = THEO_DOI.size;
  if (S.tab === 'theo_doi') veTab();
}

function ve() {
  const ds = S.diem.ds, n = Object.keys(ds).length, tuan = S.th.filter(x => Date.now() - new Date(x.luc) < 30 * 864e5);
  const dem = k => tuan.filter(x => x.muc === k).length;
  $('#app').innerHTML = `<section class="hero dt-hero"><span class="pill">Cập nhật ${tg(S.diem.cap_nhat)}</span>
      <h1 style="margin-top:12px">Phân tích đầu tư chủ động</h1>
      <p class="mut">Mỗi giờ hệ thống đọc BCTC và tin tức từ Wealbee Data API, chấm điểm ${so(n)} mã theo 5 yếu tố so với các công ty cùng ngành,
      và báo ngay những gì vừa thay đổi: lợi nhuận đột biến, dòng tiền xấu, nợ vay tăng, tin tích cực hay tiêu cực.</p>
      <p class="xs mut2">Thông tin tham khảo, tính tự động từ số liệu công bố, không phải khuyến nghị đầu tư.</p></section>
    <div class="grid g4 dt-kpi"><div class="card kpi"><div class="l">Tín hiệu 30 ngày</div><div class="v">${so(tuan.length)}</div>
        <div class="sm"><span class="up">${dem('tich_cuc')} tích cực</span> · <span class="down">${dem('tieu_cuc')} tiêu cực</span> · <span class="dt-warn">${dem('canh_bao')} cảnh báo</span></div></div>
      <div class="card kpi"><div class="l">Mã được chấm điểm</div><div class="v">${so(n)}</div><div class="sm mut">so sánh trong cùng nhóm ngành</div></div>
      <div class="card kpi"><div class="l">Tin đã phân tích (30 ngày)</div><div class="v">${so(S.diem.so_tin)}</div><div class="sm mut">tin có gắn mã, từ /news</div></div>
      <div class="card kpi"><div class="l">Danh mục theo dõi</div><div class="v" id="dt-n-td">${THEO_DOI.size}</div><div class="sm mut">lưu trên trình duyệt này</div></div></div>
    <div class="tabs dt-tabs" style="margin:22px 0 14px">${[['tin_hieu', 'Tín hiệu'], ['bo_loc', 'Bộ lọc cổ phiếu'], ['theo_doi', 'Danh mục theo dõi']]
      .map(([k, t]) => `<button class="tab ${S.tab === k ? 'on' : ''}" data-tab="${k}">${t}</button>`).join('')}</div>
    <div id="dt-than"></div>`;
  for (const b of document.querySelectorAll('[data-tab]')) b.onclick = () => { S.tab = b.dataset.tab; for (const x of document.querySelectorAll('[data-tab]')) x.classList.toggle('on', x === b); veTab(); };
  veTab();
}
function veTab() { ({tin_hieu: veTinHieu, bo_loc: veBoLoc, theo_doi: veTheoDoi})[S.tab](); }

// ---------------- tín hiệu
function locTH() {
  const L = S.loc, q = khoBo(L.q.trim());
  return S.th.filter(x => (!L.muc || x.muc === L.muc) && (!L.loai || x.loai === L.loai) && (!L.chiTheoDoi || THEO_DOI.has(x.ma))
    && (!L.nguon || (L.nguon === 'tin') === x.loai.startsWith('tin_'))
    && Date.now() - new Date(x.luc) < L.ngay * 864e5 && (!q || khoBo(`${x.ma} ${x.ten || ''}`).includes(q)));
}
function theTH(x, coMa = true) {
  const [mt, lop] = MUC[x.muc] || ['', ''];
  return `<div class="dt-th ${lop}" ${coMa ? `data-ma="${esc(x.ma)}"` : ''}><div class="dt-th-dau">${coMa ? `<b class="dt-ma">${esc(x.ma)}</b>${sao(x.ma)}` : ''}
      <span class="dt-tag ${lop}">${mt}</span><span class="xs mut2">${esc(LOAI[x.loai] || x.loai)}</span>${x.can_soat ? '<span class="tag needs_review">BCTC cần soát</span>' : ''}
      <div class="sp"></div><span class="xs mut2">${gioVN(x.luc)}</span></div>
    <div class="dt-th-td">${esc(x.tieu_de)}${coMa && x.ten ? ` <span class="mut sm">· ${esc(x.ten)}</span>` : ''}</div>
    <div class="sm mut">${esc(x.chi_tiet)}${x.link ? ` <a href="${esc(x.link)}" target="_blank" rel="noopener">${esc(x.nguon || 'nguồn')} ↗</a>` : ''}</div></div>`;
}
function veTinHieu() {
  const L = S.loc, ds = locTH(), loais = [...new Set(S.th.map(x => x.loai))];
  const nhom = {}; for (const x of ds.slice(0, L.gioiHan)) (nhom[ngayVN(x.luc)] ||= []).push(x);
  const homNay = ngayVN(new Date()), homQua = ngayVN(new Date(Date.now() - 864e5));
  $('#dt-than').innerHTML = `<div class="card"><div class="dt-loc">
      <input class="search" id="th-q" placeholder="Lọc theo mã" value="${esc(L.q)}" style="max-width:170px">
      <div class="tabs">${[['', 'Tất cả'], ['tich_cuc', 'Tích cực'], ['tieu_cuc', 'Tiêu cực'], ['canh_bao', 'Cảnh báo']].map(([k, t]) => `<button class="tab ${L.muc === k ? 'on' : ''}" data-muc="${k}">${t}</button>`).join('')}</div>
      <select id="th-nguon">${[['', 'BCTC và tin tức'], ['bctc', 'Chỉ BCTC'], ['tin', 'Chỉ tin tức']].map(([k, t]) => `<option value="${k}" ${L.nguon === k ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <select id="th-loai"><option value="">Mọi loại tín hiệu</option>${loais.map(k => `<option value="${k}" ${L.loai === k ? 'selected' : ''}>${esc(LOAI[k] || k)}</option>`).join('')}</select>
      <select id="th-ngay">${[[1, '24 giờ'], [3, '3 ngày'], [7, '7 ngày'], [30, '30 ngày']].map(([k, t]) => `<option value="${k}" ${L.ngay === k ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <label class="sm dt-chk"><input type="checkbox" id="th-td" ${L.chiTheoDoi ? 'checked' : ''}> Chỉ mã đang theo dõi</label></div>
    <div class="xs mut2" style="margin:8px 0 2px">${so(ds.length)} tín hiệu. Tín hiệu BCTC ghi theo ngày BCTC lên API; tín hiệu tin gộp các tin của cùng mã trong 3 ngày gần nhất.</div>
    ${ds.length ? Object.entries(nhom).map(([n, xs]) => `<div class="dt-ngay">${n === homNay ? 'Hôm nay' : n === homQua ? 'Hôm qua' : 'Ngày ' + n}</div>${xs.map(x => theTH(x)).join('')}`).join('')
      : `<div class="empty">${L.chiTheoDoi && !THEO_DOI.size ? 'Chưa theo dõi mã nào. Bấm ☆ cạnh một mã để thêm vào danh mục.' : 'Không có tín hiệu khớp bộ lọc.'}</div>`}
    ${ds.length > L.gioiHan ? `<div style="text-align:center;margin-top:12px"><button class="btn sec" id="th-them">Xem thêm ${so(Math.min(60, ds.length - L.gioiHan))} tín hiệu</button></div>` : ''}</div>`;
  $('#th-q').oninput = e => { L.q = e.target.value; L.gioiHan = 60; giuTieuDiem('th-q', veTinHieu); };
  for (const b of document.querySelectorAll('[data-muc]')) b.onclick = () => { L.muc = b.dataset.muc; L.gioiHan = 60; veTinHieu(); };
  $('#th-loai').onchange = e => { L.loai = e.target.value; veTinHieu(); };
  $('#th-nguon').onchange = e => { L.nguon = e.target.value; L.gioiHan = 60; veTinHieu(); };
  $('#th-ngay').onchange = e => { L.ngay = +e.target.value; veTinHieu(); };
  $('#th-td').onchange = e => { L.chiTheoDoi = e.target.checked; veTinHieu(); };
  if ($('#th-them')) $('#th-them').onclick = () => { L.gioiHan += 60; veTinHieu(); };
}
function giuTieuDiem(id, f) { const el = $('#' + id), p = el.selectionStart; f(); const n = $('#' + id); n.focus(); n.setSelectionRange(p, p); }

// ---------------- bộ lọc
const PRESET = {
  tat_ca: ['Tất cả', {}, 'Không đặt điều kiện'],
  tang_truong: ['Tăng trưởng mạnh', {tang_truong: 75}, 'Điểm tăng trưởng ≥ 75: doanh thu và lợi nhuận tăng nhanh hơn 3/4 công ty cùng ngành'],
  chat_luong: ['Chất lượng cao', {hieu_qua: 65, chat_luong: 60, an_toan: 50}, 'ROE, biên lợi nhuận cao, dòng tiền khớp lợi nhuận, nợ không quá cao'],
  an_toan: ['An toàn tài chính', {an_toan: 75}, 'Nợ và vay thấp so với vốn chủ, điểm sức khoẻ Wealbee cao'],
  tin_tot: ['Tin tức tích cực', {tin_tuc: 80}, 'Tin 30 ngày nghiêng tích cực rõ so với toàn thị trường'],
};
function locBL() {
  const B = S.bl, ds = Object.entries(S.diem.ds);
  return ds.filter(([m, v]) => (!B.nganh || v.n === B.nganh) && (!B.san || v.s === B.san) && (!B.verified || v.tt === 'verified')
    && (v.d ?? -1) >= B.min.tong && YT.every(([k], i) => !B.min[k] || (v.f[i] != null && v.f[i] >= B.min[k])));
}
const NGAN = {tang_truong: 'Tăng trưởng', hieu_qua: 'Hiệu quả', an_toan: 'An toàn', chat_luong: 'Chất lượng LN', tin_tuc: 'Tin tức'};
function giaTri(v, k) { if (k === 'd') return v.d; const i = YT.findIndex(([y]) => y === k); return i >= 0 ? v.f[i] : v.m[k]; }
function veBoLoc() {
  const B = S.bl, ds = locBL();
  if (B.sap === 'ma') ds.sort((a, b) => (B.giam ? -1 : 1) * a[0].localeCompare(b[0]));
  else ds.sort((a, b) => { const x = giaTri(a[1], B.sap), y = giaTri(b[1], B.sap); return (x == null) - (y == null) || (B.giam ? (y ?? 0) - (x ?? 0) : (x ?? 0) - (y ?? 0)); });
  const trang = ds.slice(B.trang * 50, B.trang * 50 + 50), soTrang = Math.ceil(ds.length / 50);
  const cot = (k, t, cls = 'n') => `<th class="${cls} dt-sap ${B.sap === k ? 'on' : ''}" data-sap="${k}">${t}${B.sap === k ? (B.giam ? ' ▾' : ' ▴') : ''}</th>`;
  const tb = YT.map(([k, t]) => `<label class="dt-tr"><span class="sm">${t} ≥ <b id="v-${k}">${B.min[k]}</b></span><input type="range" min="0" max="95" step="5" value="${B.min[k]}" data-min="${k}"></label>`).join('');
  $('#dt-than').innerHTML = `<div class="card"><div class="dt-preset">${Object.entries(PRESET).map(([k, [t]]) => `<button class="tab ${B.preset === k ? 'on' : ''}" data-preset="${k}">${t}</button>`).join('')}</div>
      <div class="xs mut2" style="margin:6px 0 12px">${esc(PRESET[B.preset]?.[2] || 'Điều kiện tuỳ chỉnh')}</div>
      <details class="dt-tuy" ${B.preset === 'tuy_chinh' ? 'open' : ''}><summary class="sm">Tuỳ chỉnh điều kiện</summary><div class="dt-sliders">
        <label class="dt-tr"><span class="sm">Điểm tổng ≥ <b id="v-tong">${B.min.tong}</b></span><input type="range" min="0" max="95" step="5" value="${B.min.tong}" data-min="tong"></label>${tb}</div></details>
      <div class="dt-loc" style="margin-top:10px"><select id="bl-nganh"><option value="">Mọi ngành</option>${Object.entries(NGANH).map(([k, t]) => `<option value="${k}" ${B.nganh === k ? 'selected' : ''}>${t}</option>`).join('')}</select>
        <select id="bl-san"><option value="">Mọi sàn</option>${['HOSE', 'HNX', 'UPCOM'].map(k => `<option ${B.san === k ? 'selected' : ''}>${k}</option>`).join('')}</select>
        <label class="sm dt-chk"><input type="checkbox" id="bl-ver" ${B.verified ? 'checked' : ''}> Chỉ BCTC đã kiểm chứng</label><div class="sp"></div>
        <span class="sm"><b>${so(ds.length)}</b> mã khớp</span></div></div>
    <div class="card" style="margin-top:14px;padding:0"><div style="overflow-x:auto"><table class="dt-bang">
      <tr><th></th>${cot('ma', 'Mã', '')}${cot('d', 'Điểm tổng')}${YT.map(([k]) => cot(k, NGAN[k])).join('')}
        ${cot('ln_q', 'LNST quý')}${cot('roe', 'ROE')}<th class="n">Giá 3 tháng</th></tr>
      ${trang.map(([m, v]) => `<tr class="row" data-ma="${esc(m)}"><td>${sao(m)}</td><td><b>${esc(m)}</b><div class="xs mut2">${esc((v.t || '').slice(0, 26))} · ${esc(NGANH[v.n] || '')}</div></td>
        <td class="n"><span class="dt-diem ${lopD(v.d)}">${v.d ?? '—'}</span></td>${v.f.map(x => `<td class="n ${lopD(x)}">${x ?? '—'}</td>`).join('')}
        <td class="n ${v.m.ln_q > 0 ? 'up' : v.m.ln_q < 0 ? 'down' : ''}">${lnq(v.m)}</td><td class="n">${v.m.roe == null ? '—' : pt(v.m.roe) + '%'}</td>
        <td class="n" data-gia="${esc(m)}">…</td></tr>`).join('')}</table></div>
      ${!trang.length ? '<div class="empty">Không có mã nào khớp. Thử nới điều kiện.</div>' : ''}
      ${soTrang > 1 ? `<div class="dt-trang">${B.trang ? '<button class="btn sec" id="bl-truoc">← Trước</button>' : ''}<span class="sm mut">Trang ${B.trang + 1}/${soTrang}</span>${B.trang < soTrang - 1 ? '<button class="btn sec" id="bl-sau">Sau →</button>' : ''}</div>` : ''}
      <div class="xs mut2" style="padding:0 16px 14px">Điểm 0-100 = phân vị trong cùng nhóm ngành (50 = ngang trung vị). LNST quý so với cùng kỳ năm trước. Giá 3 tháng tải từ VNDirect cho các mã đang hiện.</div></div>`;
  for (const b of document.querySelectorAll('[data-preset]')) b.onclick = () => { B.preset = b.dataset.preset; B.min = {tong: 0, tang_truong: 0, hieu_qua: 0, an_toan: 0, chat_luong: 0, tin_tuc: 0, ...PRESET[B.preset][1]}; B.trang = 0;
    if (B.preset !== 'tat_ca') { B.sap = Object.keys(PRESET[B.preset][1])[0]; B.giam = true; } veBoLoc(); };
  for (const r of document.querySelectorAll('[data-min]')) { r.oninput = () => { $('#v-' + r.dataset.min).textContent = r.value; };
    r.onchange = () => { B.min[r.dataset.min] = +r.value; B.preset = 'tuy_chinh'; B.trang = 0; veBoLoc(); }; }
  for (const th of document.querySelectorAll('[data-sap]')) th.onclick = () => { const k = th.dataset.sap; if (B.sap === k) B.giam = !B.giam; else { B.sap = k; B.giam = k !== 'ma'; } veBoLoc(); };
  $('#bl-nganh').onchange = e => { B.nganh = e.target.value; B.trang = 0; veBoLoc(); };
  $('#bl-san').onchange = e => { B.san = e.target.value; B.trang = 0; veBoLoc(); };
  $('#bl-ver').onchange = e => { B.verified = e.target.checked; B.trang = 0; veBoLoc(); };
  if ($('#bl-truoc')) $('#bl-truoc').onclick = () => { B.trang--; veBoLoc(); };
  if ($('#bl-sau')) $('#bl-sau').onclick = () => { B.trang++; veBoLoc(); };
  taiGiaHang(trang.map(([m]) => m), 63, el => el.dataset.gia);
}

// ---------------- giá (VNDirect, gọi thẳng từ trình duyệt)
async function layGia(m) {
  if (S.gia[m] !== undefined) return S.gia[m];
  const to = Math.floor(Date.now() / 1000), fr = to - 380 * 86400;
  S.gia[m] = fetch(`https://dchart-api.vndirect.com.vn/dchart/history?resolution=D&symbol=${m}&from=${fr}&to=${to}`).then(r => r.json())
    .then(j => j?.t?.length ? j : null).catch(() => null);
  return S.gia[m];
}
const doiGia = (j, phien) => { if (!j) return null; const c = j.c, n = c.length; return n > phien ? (c[n - 1] - c[n - 1 - phien]) / c[n - 1 - phien] * 100 : (c[n - 1] - c[0]) / c[0] * 100; };
async function taiGiaHang(ms, phien, khoa) {
  const hang = [...ms];
  const chay = async () => { while (hang.length) { const m = hang.shift(); const j = await layGia(m); const d = doiGia(j, phien);
    for (const el of document.querySelectorAll(`[data-gia="${m}"]`)) { el.textContent = d == null ? '—' : dau(d); el.className = 'n ' + (d == null ? 'mut2' : d >= 0 ? 'up' : 'down'); } } };
  await Promise.all([chay(), chay(), chay(), chay()]);
}

// ---------------- danh mục theo dõi
function veTheoDoi() {
  const ds = [...THEO_DOI].filter(m => S.diem.ds[m]);
  const goiY = Object.entries(S.diem.ds).filter(([, v]) => v.d != null).sort((a, b) => b[1].d - a[1].d).slice(0, 6).map(([m]) => m);
  $('#dt-than').innerHTML = `<div class="card dt-loc"><input class="search" id="td-them" list="td-ds" placeholder="Thêm mã vào danh mục, VD FPT" style="max-width:260px">
      <datalist id="td-ds">${Object.entries(S.diem.ds).map(([m, v]) => `<option value="${m}">${esc(v.t || '')}</option>`).join('')}</datalist>
      <button class="btn" id="td-nut">Thêm</button><div class="sp"></div><span class="xs mut2">Danh mục lưu trên trình duyệt này. Tín hiệu mới của các mã ở đây hiện ở tab Tín hiệu khi bật "Chỉ mã đang theo dõi".</span></div>
    ${ds.length ? `<div class="grid dt-the-td" style="margin-top:14px">${ds.map(m => theTD(m)).join('')}</div>`
      : `<div class="card empty" style="margin-top:14px">Chưa theo dõi mã nào. Gợi ý các mã điểm tổng cao nhất:
        <div class="dt-goi-y">${goiY.map(m => `<button class="tab" data-them="${m}">+ ${m}</button>`).join('')}</div></div>`}`;
  const them = () => { const m = $('#td-them').value.trim().toUpperCase(); if (S.diem.ds[m]) { THEO_DOI.add(m); luuTD(); $('#dt-n-td').textContent = THEO_DOI.size; veTheoDoi(); } else if (m) $('#td-them').classList.add('dt-sai'); };
  $('#td-nut').onclick = them; $('#td-them').onkeydown = e => { if (e.key === 'Enter') them(); };
  for (const b of document.querySelectorAll('[data-them]')) b.onclick = () => { THEO_DOI.add(b.dataset.them); luuTD(); $('#dt-n-td').textContent = THEO_DOI.size; veTheoDoi(); };
  taiGiaHang(ds, 250, el => el.dataset.gia);
}
function thanhYT(v, nhom, gon) {
  const tv = S.diem.trung_vi[v.n] || {};
  return YT.map(([k, t], i) => { const x = v.f[i]; if (x == null && gon) return '';
    return `<div class="dt-yt"><span class="sm">${t}</span><div class="dt-bar"><i class="${lopD(x)}" style="width:${x ?? 0}%"></i>${tv[k] != null ? `<b style="left:${tv[k]}%" title="Trung vị ngành: ${tv[k]}"></b>` : ''}</div>
      <span class="sm n ${lopD(x)}">${x ?? '—'}</span></div>`; }).join('');
}
function theTD(m) {
  const v = S.diem.ds[m], th = S.th.filter(x => x.ma === m).slice(0, 3);
  return `<div class="card dt-td" data-ma="${esc(m)}"><div style="display:flex;align-items:flex-start;gap:10px"><div style="flex:1"><div class="dt-ma-lon">${esc(m)} ${sao(m)}</div>
      <div class="xs mut2">${esc(v.t || '')} · ${esc(v.s || '')} · ${esc(NGANH[v.n] || '')} · ${esc(v.k)}</div></div>
      <div style="text-align:right"><div class="dt-diem-lon ${lopD(v.d)}">${v.d ?? '—'}</div><div class="xs mut2">điểm tổng</div></div></div>
    <div class="sm" style="margin:8px 0">Giá 12 tháng: <b data-gia="${esc(m)}">…</b></div>${thanhYT(v, v.n, true)}
    <div style="margin-top:10px">${th.length ? th.map(x => `<div class="xs dt-mini ${(MUC[x.muc] || [])[1]}">● ${esc(x.tieu_de)} <span class="mut2">${ngayVN(x.luc)}</span></div>`).join('') : '<div class="xs mut2">Không có tín hiệu 30 ngày qua.</div>'}</div></div>`;
}

// ---------------- thẻ quyết định
function nhanXet(m, v, st) {
  const tv = S.diem.trung_vi[v.n] || {}, x = v.m, manh = [], yeu = [];
  const i = st?.income_statement || {}, b = st?.balance_sheet || {}, c = st?.cash_flow || {};
  const ty = n => n == null ? '—' : so(n / 1e9, Math.abs(n) >= 1e12 ? 0 : 1) + ' tỷ';
  if (x.ln_dao === 1) manh.push(`Có lãi trở lại: LNST quý ${ty(i.net_profit?.quarter)}, cùng kỳ năm trước lỗ ${ty(Math.abs(i.net_profit?.quarter_prior_year || 0))}.`);
  else if (x.ln_dao === -1) yeu.push(`Chuyển sang lỗ: LNST quý âm ${ty(Math.abs(i.net_profit?.quarter || 0))}, cùng kỳ năm trước lãi ${ty(i.net_profit?.quarter_prior_year)}.`);
  else if (x.ln_q >= 30) manh.push(`LNST quý tăng ${x.ln_q >= 300 ? 'hơn 300' : pt(x.ln_q)}% so với cùng kỳ (${ty(i.net_profit?.quarter)}).`);
  else if (x.ln_q <= -30) yeu.push(`LNST quý giảm ${pt(-x.ln_q)}% so với cùng kỳ (còn ${ty(i.net_profit?.quarter)}).`);
  if (x.dt_q <= -20) yeu.push(`${v.n === 'bank' ? 'Thu nhập hoạt động' : 'Doanh thu'} quý giảm ${pt(-x.dt_q)}% so với cùng kỳ.`);
  if (x.roe != null && tv.roe != null && x.roe >= Math.max(15, tv.roe * 1.3)) manh.push(`ROE năm hoá ${pt(x.roe)}%, cao hơn trung vị ngành ${pt(tv.roe)}%.`);
  if (x.roe != null && x.roe < 5) yeu.push(`ROE năm hoá chỉ ${pt(x.roe)}% (trung vị ngành ${pt(tv.roe)}%).`);
  if (v.n === 'corporate' && x.no_vcsh != null && tv.no_vcsh != null) {
    if (x.no_vcsh <= tv.no_vcsh * 0.6) manh.push(`Nợ phải trả chỉ bằng ${pt(x.no_vcsh)} lần vốn chủ (ngành ${pt(tv.no_vcsh)} lần).`);
    if (x.no_vcsh >= Math.max(2, tv.no_vcsh * 1.8)) yeu.push(`Nợ phải trả gấp ${pt(x.no_vcsh)} lần vốn chủ (ngành ${pt(tv.no_vcsh)} lần).`); }
  if (x.cfo_ln >= 1) manh.push(`Dòng tiền kinh doanh luỹ kế bằng ${pt(x.cfo_ln)} lần LNST: lợi nhuận có tiền thật.`);
  if (x.cfo_ln != null && x.cfo_ln < 0) yeu.push(`Có lãi nhưng dòng tiền kinh doanh luỹ kế âm ${ty(Math.abs(c.operating?.ytd || 0))}.`);
  if (x.suc_khoe >= 8) manh.push(`Điểm sức khoẻ tài chính Wealbee ${x.suc_khoe}/10.`);
  if (x.suc_khoe != null && x.suc_khoe <= 3) yeu.push(`Điểm sức khoẻ tài chính Wealbee chỉ ${x.suc_khoe}/10.`);
  if (x.tin >= 0.3 && x.tin_n >= 3) manh.push(`Tin 30 ngày nghiêng tích cực (${x.tin_n} tin).`);
  if (x.tin <= -0.2 && x.tin_n >= 3) yeu.push(`Tin 30 ngày nghiêng tiêu cực (${x.tin_n} tin).`);
  if (v.tt === 'needs_review') yeu.push('BCTC kỳ này đang ở trạng thái cần soát: đối chiếu file gốc trước khi dùng số.');
  return {manh, yeu};
}
async function moThe(m) {
  const v = S.diem.ds[m]; if (!v) return;
  D.chon = m; if (location.hash.slice(1) !== m) history.replaceState(null, '', '#' + m);
  let k = $('#dt-the'); if (!k) { document.body.insertAdjacentHTML('beforeend', '<div class="dt-nen" id="dt-nen"></div><div class="dt-the" id="dt-the" role="dialog" aria-modal="true"></div>'); k = $('#dt-the');
    $('#dt-nen').onclick = dongThe; document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#dt-the')?.classList.contains('mo')) dongThe(); }); }
  k.classList.add('mo'); $('#dt-nen').classList.add('mo'); document.body.classList.add('dt-khoa');
  const tv = S.diem.trung_vi[v.n] || {}, th = S.th.filter(x => x.ma === m).slice(0, 6);
  k.innerHTML = `<div class="dt-the-dau"><div style="flex:1;min-width:0"><div class="dt-ma-lon">${esc(m)} ${sao(m)}</div>
      <div class="sm mut">${esc(v.t || '')}</div><div class="xs mut2">${esc(v.s || '')} · ${esc(NGANH[v.n] || '')} · BCTC ${esc(v.k)} <span class="tag ${esc(v.tt)}">${v.tt === 'verified' ? 'đã kiểm chứng' : 'cần soát'}</span></div></div>
      <div style="text-align:right"><div class="dt-diem-lon ${lopD(v.d)}">${v.d ?? '—'}</div><div class="xs mut2">điểm tổng · trung vị ngành ${tv.tong ?? '—'}</div></div>
      <button class="ai-icon" id="dt-dong" title="Đóng">✕</button></div>
    <div class="dt-nut"><a class="btn sec" href="../doanh-nghiep/#${esc(m)}">Xem BCTC chi tiết</a>${window.AI ? `<button class="btn" id="dt-ai">✦ AI phân tích ${esc(m)}</button>` : ''}</div>
    <div class="dt-the-than"><h3>5 yếu tố so với ${esc(NGANH[v.n] || 'ngành').toLowerCase()} <span class="xs mut2">(vạch trắng = trung vị ngành)</span></h3>${thanhYT(v, v.n, false)}
      <details class="dt-cs"><summary class="sm">Chỉ số dùng để chấm</summary><table>${Object.entries(CS).filter(([c]) => v.m[c] != null).map(([c, [t, dv]]) =>
        `<tr><td class="sm">${t}</td><td class="n sm"><b>${c === 'tin' ? pt(v.m[c] * 100) + ' (' + v.m.tin_n + ' tin)' : c === 'ln_q' ? lnq(v.m) : c.endsWith('_q') || c.endsWith('_lk') ? (v.m[c] >= 300 ? '> +300%' : dau(v.m[c])) : pt(v.m[c]) + dv}</b></td><td class="n xs mut2">ngành ${tv[c] == null ? '—' : c === 'tin' ? '—' : pt(tv[c]) + dv}</td></tr>`).join('')}</table></details>
      <div class="grid g2" style="margin-top:14px" id="dt-nx"><div class="card"><h3>Điểm mạnh</h3><div class="sm mut">Đang đọc BCTC…</div></div><div class="card"><h3>Rủi ro cần xem</h3></div></div>
      <h3 style="margin-top:16px">Giá 12 tháng · VNDirect</h3><div id="dt-gia" class="sm mut">Đang tải giá…</div>
      <h3 style="margin-top:16px">Tín hiệu 30 ngày</h3>${th.length ? th.map(x => theTH(x, false)).join('') : '<div class="sm mut">Không có tín hiệu.</div>'}
      <h3 style="margin-top:16px">Tin 30 ngày qua /news</h3><div id="dt-tin" class="sm mut">Đang tải tin…</div>
      <p class="xs mut2" style="margin-top:16px">Điểm và nhận xét được tính tự động từ số liệu công bố, chỉ để tham khảo, không phải khuyến nghị đầu tư.</p></div>`;
  $('#dt-dong').onclick = dongThe;
  if ($('#dt-ai')) $('#dt-ai').onclick = () => { dongThe(); D.chon = m; AI.phanTich(m); };
  if (!D.ma[m]) D.ma[m] = await tai(`ma/${m}`).catch(() => null);
  if (D.chon !== m) return;
  const kys = Object.keys(D.ma[m]?.ky || {}).sort(), st = D.ma[m]?.ky?.[kys.at(-1)];
  const {manh, yeu} = nhanXet(m, v, st);
  const li = (xs, rong) => xs.length ? `<ul class="dt-ul">${xs.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : `<div class="sm mut">${rong}</div>`;
  $('#dt-nx').innerHTML = `<div class="card"><h3 class="up">Điểm mạnh</h3>${li(manh, 'Chưa có điểm nổi bật so với ngành.')}</div><div class="card"><h3 class="down">Rủi ro cần xem</h3>${li(yeu, 'Chưa thấy rủi ro nổi bật trong số liệu.')}</div>`;
  layGia(m).then(j => { if (D.chon !== m || !$('#dt-gia')) return; if (!j) { $('#dt-gia').textContent = 'Không lấy được giá.'; return; }
    const kq = Math.max(...j.c) < 1000 ? 1000 : 1, d = doiGia(j, 250);
    $('#dt-gia').className = ''; $('#dt-gia').innerHTML = `<div class="sm">Giá đóng cửa <b>${so(j.c.at(-1) * kq)}</b> đồng · <span class="${d >= 0 ? 'up' : 'down'}">${dau(d)}</span> trong 12 tháng</div>
      ${bieuDoDuong([{ten: m, mau: '#7c5cff', diem: j.t.map((t, i) => [t * 1000, j.c[i] * kq / 1000])}], {donVi: 'k', cao: 180})}`; });
  taiJson(`data/tin/${m}.json`).then(ds => { if (D.chon !== m || !$('#dt-tin')) return;
    $('#dt-tin').className = ''; $('#dt-tin').innerHTML = ds?.length ? ds.slice(0, 8).map(x => `<div class="dt-tin"><span class="dt-cham ${x.s === 'pos' ? 'up' : x.s === 'neg' ? 'down' : 'mut2'}">●</span>
      <div>${x.u ? `<a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.t)}</a>` : esc(x.t)}<div class="xs mut2">${gioVN(x.d)}${x.o ? ' · ' + esc(x.o) : ''}${x.n > 1 ? ` · ${x.n} nguồn` : ''}</div></div></div>`).join('')
      : '<div class="sm mut">Không có tin gắn mã này trong 30 ngày.</div>'; });
}
function dongThe() { $('#dt-the')?.classList.remove('mo'); $('#dt-nen')?.classList.remove('mo'); document.body.classList.remove('dt-khoa'); D.chon = null;
  if (location.hash) history.replaceState(null, '', location.pathname + location.search); }

main();
