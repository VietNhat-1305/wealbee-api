// Web tra cứu BCTC (cùng 1 mã nguồn cho 2 web, khác gói API): CAU_HINH = {goi:'free'|'dn', ma_hoa:bool}
const CH = window.CAU_HINH;
const DUOI = CH.ma_hoa ? '.enc' : '';
const NHAN = {revenue: 'Doanh thu', gross_profit: 'Lợi nhuận gộp', net_profit: 'Lợi nhuận sau thuế', cost_of_sales: 'Giá vốn',
  operating_profit: 'Lợi nhuận hoạt động', profit_before_tax: 'Lợi nhuận trước thuế', total_assets: 'Tổng tài sản',
  total_liabilities: 'Nợ phải trả', equity: 'Vốn chủ sở hữu', owners_equity: 'Vốn chủ sở hữu', cash: 'Tiền', cash_and_equivalents: 'Tiền và tương đương tiền',
  inventories: 'Hàng tồn kho', receivables: 'Phải thu', operating_cash_flow: 'LCTT hoạt động kinh doanh', investing_cash_flow: 'LCTT đầu tư',
  financing_cash_flow: 'LCTT tài chính', operating: 'LCTT từ hoạt động kinh doanh', investing: 'LCTT từ hoạt động đầu tư',
  financing: 'LCTT từ hoạt động tài chính', net_change: 'Lưu chuyển tiền thuần trong kỳ', borrowings: 'Vay nợ', net_interest_income: 'Thu nhập lãi thuần', operating_expenses: 'Chi phí hoạt động',
  net_profit_parent: 'LNST của cổ đông công ty mẹ', eps: 'EPS', short_term_debt: 'Vay ngắn hạn', long_term_debt: 'Vay dài hạn'};
const NGANH = {corporate: 'Doanh nghiệp', bank: 'Ngân hàng', securities: 'Chứng khoán', insurance: 'Bảo hiểm'};
const nhanKhoa = k => NHAN[k] || k.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
let D = {idx: null, cty: {}, mk: null, ma: {}, chon: null, loc: '', nganh: ''};

async function tai(ten) {
  const r = await fetch(`data/${ten}.json${DUOI}`, {cache: 'no-store'});
  if (!r.ok) return null;
  const j = await r.json();
  return CH.ma_hoa ? moGoi(j, D.mk) : j;
}
// chỉ tiêu Wealbee: KQKD {quarter, quarter_prior_year, ytd, ytd_prior_year}; CĐKT {end_of_period, start_of_year}; LCTT {ytd, ytd_prior_year}
const gt = m => m == null ? null : typeof m === 'number' ? m : typeof m === 'object' ?
  (m.quarter ?? m.end_of_period ?? m.ytd ?? m.end ?? m.value ?? null) : null;
const ssanh = m => !(m && typeof m === 'object') ? null : m.quarter != null ? (m.quarter_prior_year ?? null)
  : m.end_of_period != null ? (m.start_of_year ?? null) : m.ytd != null ? (m.ytd_prior_year ?? null) : null;
const diem = st => Object.entries(st || {}).find(([k, v]) => /score|health/.test(k) && (typeof v === 'number' || (v && typeof v === 'object')))?.[1];

async function main() {
  const khung = $('#app');
  const tt = await fetch('data/trang_thai.json', {cache: 'no-store'}).then(r => r.ok ? r.json() : null).catch(() => null);
  if (CH.ma_hoa) {
    const r = await fetch('data/index.json.enc', {cache: 'no-store'});
    if (!r.ok) return chuaCo(khung, tt);
    const g = await congMatKhau('data/index.json.enc', khung, 'Tra cứu BCTC · Gói Free');
    D.mk = g.mk; D.idx = g.du_lieu;
  } else {
    D.idx = await tai('index');
    if (!D.idx) return chuaCo(khung, tt);
  }
  const ct = await tai('cong_ty').catch(() => null);
  for (const c of (ct?.ds || [])) D.cty[c.ticker || c.code || c.symbol] = c;
  D.tt = tt;
  ve();
  window.AI?.gan();                                // trợ lý AI (ai.js): nút nổi góc phải
  window.onhashchange = () => chonMa(location.hash.slice(1));
  if (location.hash.length > 1) chonMa(location.hash.slice(1));
}

function chuaCo(khung, tt) {
  khung.innerHTML = `<div class="card empty"><h2>Chưa có dữ liệu</h2><div>Hệ thống đang chờ khoá API ${CH.goi === 'dn' ? 'gói Doanh nghiệp' : 'gói Free'}
    hoặc đang đồng bộ lần đầu (mỗi giờ lấy thêm một phần).</div>${tt ? `<div class="sm mut2" style="margin-top:8px">Kiểm lần cuối: ${tg(tt.lan_kiem)}</div>` : ''}</div>`;
}

function quyenHtml(q) {
  if (!q) return '';
  const o = [];
  if (q.name) o.push(`Gói <b>${esc(q.name)}</b>`);
  if (q.rate_limit_per_minute) o.push(`${so(q.rate_limit_per_minute)} request/phút`);
  if (q.delay_minutes != null) o.push(q.delay_minutes ? `trễ ${q.delay_minutes} phút` : 'thời gian thực');
  if (q.include_score != null) o.push(q.include_score ? 'có điểm sức khoẻ' : 'không có điểm sức khoẻ');
  const hien = Object.entries(q).find(([k]) => /display|redistribution/.test(k));
  if (hien) o.push(hien[1] ? 'được hiển thị lại cho khách' : 'chỉ dùng nội bộ');
  return o.join(' · ');
}

function ve() {
  const k = $('#app'), ds = Object.entries(D.idx.cong_ty || {});
  const nganh = [...new Set(ds.map(([, v]) => v.nganh).filter(Boolean))];
  k.innerHTML = `<div class="grid g4" style="margin-bottom:16px">
      <div class="card kpi"><div class="l">Số mã có dữ liệu</div><div class="v">${so(ds.length)}</div></div>
      <div class="card kpi"><div class="l">Dữ liệu đổi lần cuối</div><div class="v" style="font-size:17px">${tg(D.idx.cap_nhat)}</div></div>
      <div class="card kpi"><div class="l">Kiểm cập nhật lần cuối</div><div class="v" style="font-size:17px">${tg(D.tt?.lan_kiem)}</div></div>
      <div class="card kpi"><div class="l">Quyền của gói (từ /v1/me)</div><div class="sm" style="margin-top:4px">${quyenHtml(D.idx.quyen) || '—'}</div></div></div>
    ${D.tt?.dang_dong_bo_lan_dau ? '<div class="card sm" style="margin-bottom:16px">⏳ Đang đồng bộ lần đầu: mỗi giờ lấy thêm một phần, danh sách sẽ dần đầy đủ.</div>' : ''}
    <div class="split"><div class="card"><div class="grid" style="grid-template-columns:1fr auto;gap:10px;margin-bottom:12px">
        <input class="search" id="q" placeholder="Tìm mã hoặc tên công ty (gõ không dấu được)" value="${esc(D.loc)}">
        <select id="ng"><option value="">Mọi ngành</option>${nganh.map(n => `<option value="${esc(n)}" ${D.nganh === n ? 'selected' : ''}>${esc(NGANH[n] || n)}</option>`).join('')}</select></div>
      <div class="xs mut2" style="margin:-4px 0 6px">DT, LNST: quý gần nhất, tỷ đồng${CH.goi === 'dn' ? ' · Điểm: điểm sức khoẻ tài chính /10' : ''}</div>
      <div class="list" id="ds"></div></div>
      <div id="ct"></div></div>`;
  $('#q').oninput = e => { D.loc = e.target.value; veDs(); };
  $('#ng').onchange = e => { D.nganh = e.target.value; veDs(); };
  veDs();
  if (D.chon) veCt(D.chon); else veTinChung();
}

// ---- tin tức: Wealbee (app, mục Đề xuất) cho cả 2 web; Vietstock (RSS miễn phí) thêm cho web bản Free
const taiJson = u => fetch(u, {cache: 'no-store'}).then(r => r.ok ? r.json() : null).catch(() => null);
const SAC = {positive: ['Tích cực', 'up'], negative: ['Tiêu cực', 'down'], neutral: ['Trung lập', 'mut']};
function theTin(x) {
  const s = SAC[x.sac_thai];
  const nhan = [x.loai || (x.muc || []).join(', '), x.nganh, s ? `<span class="${s[1]}">${s[0]}</span>` : '', x.so_nguon ? `${x.so_nguon} nguồn` : '']
    .filter(Boolean).join(' · ');
  return `<div class="tin">${x.anh ? `<img src="${esc(x.anh)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : '<div></div>'}
    <div><a class="t" href="${esc(x.link)}" target="_blank" rel="noopener">${esc((x.tieu_de || '').replace(/\*\*/g, ''))}</a>
    <div class="sm mut">${esc((x.tom_tat || '').replace(/\*\*/g, ''))}</div>
    <div class="xs mut2">${tg(x.luc)}${nhan ? ' · ' + nhan : ''}${(x.ma || []).length ? ' · ' + x.ma.slice(0, 6).map(m => `<a href="#${esc(m)}">${esc(m)}</a>`).join(' ') : ''}</div></div></div>`;
}
const NGUON_TIN = () => [['wealbee', 'Tin Wealbee', '../tin/moi.json', m => `../tin/ma/${m}.json`]]
  .concat(CH.vietstock ? [['vietstock', 'Tin Vietstock', '../vietstock/tin_moi.json', m => `../vietstock/tin_ma/${m}.json`]] : []);
async function veTinChung(chon) {
  const ng = NGUON_TIN(), k = chon || ng[0][0], n = ng.find(x => x[0] === k);
  $('#ct').innerHTML = `<div class="card"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px">
      <h2 style="margin:0">Tin mới</h2><div class="tabs">${ng.map(x => `<button class="tab ${x[0] === k ? 'on' : ''}" onclick="veTinChung('${x[0]}')">${x[1]}</button>`).join('')}</div>
      <div class="sp"></div><span class="xs mut2">Chọn một mã bên trái để xem BCTC</span></div><div id="tinds" class="mut sm">Đang tải…</div></div>`;
  const j = await taiJson(n[2]);
  if (D.chon) return;
  $('#tinds').innerHTML = j?.ds?.length ? j.ds.slice(0, 40).map(theTin).join('') : '<div class="empty">Chưa có tin.</div>';
}
async function veTinMa(m) {
  const ng = NGUON_TIN(), ds = [];
  for (const [ten, nhan, , f] of ng) { const j = await taiJson(f(m)); for (const x of (j?.ds || [])) ds.push({...x, _nguon: nhan}); }
  if (D.chon !== m || !$('#tinma')) return;
  ds.sort((a, b) => (b.luc || '').localeCompare(a.luc || ''));
  $('#tinma').innerHTML = ds.length ? ds.slice(0, 15).map(x => theTin({...x, loai: (x.loai || (x.muc || []).join(', ')) + ` · ${x._nguon}`})).join('')
    : `<div class="mut sm">Chưa có tin nào nhắc tới ${esc(m)} trong 30 ngày gần đây${CH.vietstock ? ' (Wealbee, Vietstock)' : ''}.</div>`;
}

function veDs() {
  const q = khoBo(D.loc.trim());
  const ds = Object.entries(D.idx.cong_ty || {}).filter(([m, v]) => (!D.nganh || v.nganh === D.nganh) &&
    (!q || khoBo(m + ' ' + (D.cty[m]?.name || '')).includes(q))).sort((a, b) => a[0].localeCompare(b[0]));
  const co = ds.some(([, v]) => v.diem != null);
  $('#ds').innerHTML = ds.length ? `<table><tr><th>Mã</th><th>Kỳ</th><th class="n" title="tỷ đồng">DT</th><th class="n" title="tỷ đồng">LNST</th>${co ? '<th class="n">Điểm</th>' : ''}<th></th></tr>
    ${ds.slice(0, 800).map(([m, v]) => `<tr class="row" onclick="location.hash='${m}'"><td><b>${m}</b><div class="xs mut2">${esc((D.cty[m]?.name || '').slice(0, 34))}</div></td>
      <td class="sm">${esc(v.ky)}</td><td class="n">${so(v.dt / 1e9)}</td><td class="n ${v.ln < 0 ? 'down' : ''}">${so(v.ln / 1e9)}</td>
      ${co ? `<td class="n">${v.diem == null ? '—' : `<b>${so(v.diem)}</b><span class="xs mut2">/${v.diem_max || 10}</span>`}</td>` : ''}<td><span class="tag ${esc(v.tt)}">${esc(v.tt === 'verified' ? '✓' : v.tt === 'needs_review' ? 'soát' : v.tt || '')}</span></td></tr>`).join('')}</table>`
    : '<div class="empty">Không có mã khớp.</div>';
}

async function chonMa(m) {
  m = (m || '').toUpperCase();
  if (!m || !D.idx.cong_ty[m]) return;
  D.chon = m;
  $('#ct').innerHTML = '<div class="card empty">Đang tải…</div>';
  if (!D.ma[m]) D.ma[m] = await tai(`ma/${m}`);
  veCt(m);
  if (innerWidth < 900) $('#ct').scrollIntoView({behavior: 'smooth'});
}

function bangChiTieu(ten, bang) {
  if (!bang || typeof bang !== 'object') return '';
  const dong = Object.entries(bang).filter(([, v]) => gt(v) != null);
  if (!dong.length) return '';
  return `<div class="card"><h3>${ten}</h3><table><tr><th>Chỉ tiêu</th><th class="n">Kỳ này</th><th class="n">So sánh</th><th class="n">±</th></tr>
    ${dong.map(([k, v]) => { const a = gt(v), b = ssanh(v), d = pct(a, b);
      return `<tr><td class="sm">${esc(nhanKhoa(k))}</td><td class="n">${ty(a)}</td><td class="n mut">${ty(b)}</td>
        <td class="n ${d == null ? '' : d >= 0 ? 'up' : 'down'}">${d == null ? '' : (d >= 0 ? '+' : '') + so(d, 1) + '%'}</td></tr>`; }).join('')}</table></div>`;
}

function veCt(m) {
  const du = D.ma[m]; if (!du) return;
  const kys = Object.keys(du.ky).sort(), st = du.ky[kys[kys.length - 1]], c = D.cty[m] || {};
  const inc = st.income_statement || {}, bs = st.balance_sheet || {}, cf = st.cash_flow || {};
  const dt = gt(inc.revenue), ln = gt(inc.net_profit), dtS = ssanh(inc.revenue), lnS = ssanh(inc.net_profit), sk = diem(st);
  const ng = st.nguon_goc || {};
  const kpi = (l, v, s) => { const d = pct(v, s); return `<div class="card kpi"><div class="l">${l}</div><div class="v">${ty(v)}</div>
    ${d == null ? '' : `<div class="sm ${d >= 0 ? 'up' : 'down'}">${d >= 0 ? '▲' : '▼'} ${so(Math.abs(d), 1)}% so cùng kỳ</div>`}</div>`; };
  $('#ct').innerHTML = `<div class="grid">
    <div class="card"><div style="display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap"><div style="flex:1;min-width:200px">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><h1>${m}</h1>${window.AI ? `<button class="btn" style="padding:8px 14px;font-size:13.5px" onclick="AI.phanTich('${m}')">✦ AI phân tích ${m}</button>` : ''}</div><div class="mut">${esc(c.name || '')}</div>
      <div class="sm mut2">${esc(c.exchange || '')} · ${esc(NGANH[st.industry_type] || st.industry_type || '')} · ${esc(st.period_label || kys[kys.length - 1])} · ${esc(st.scope === 'consolidated' ? 'hợp nhất' : st.scope === 'single_entity' ? 'riêng' : st.scope || '')}</div></div>
      <div style="text-align:right"><span class="tag ${esc(st.status)}">${esc(st.status || '')}</span>
      <div class="sm mut" style="margin-top:6px">Phép kiểm: <b>${st.kiem?.dat ?? '—'}/${st.kiem?.tong ?? '—'}</b> đạt${st.kiem?.loi?.length ? ` · lỗi: ${esc(st.kiem.loi.join(', '))}` : ''}</div>
      ${sk != null ? `<div class="sm" style="margin-top:4px">Điểm sức khoẻ tài chính: <b style="font-size:18px">${so(typeof sk === 'object' ? sk.value : sk)}</b>/${typeof sk === 'object' ? sk.max || 10 : 10}${typeof sk === 'object' && sk.missing_points ? ` <span class="xs mut2">(thiếu ${sk.missing_points} tiêu chí)</span>` : ''}</div>` :
        `<div class="xs mut2" style="margin-top:4px">${CH.goi === 'free' ? 'Gói Free không có điểm sức khoẻ' : 'Chưa có điểm sức khoẻ'}</div>`}</div></div></div>
    <div class="grid g4">${kpi('Doanh thu quý', dt, dtS)}${kpi('LNST quý', ln, lnS)}${kpi('Tổng tài sản', gt(bs.total_assets), ssanh(bs.total_assets))}</div>
    <div class="card"><h3>Giá cổ phiếu 12 tháng · nguồn <span id="nguon_gia">${CH.vietstock ? 'Vietstock' : 'VNDirect'}</span> (API miễn phí)</h3><div id="gia" class="empty sm">Đang tải giá…</div></div>
    <div class="card"><h3>Tin tức về ${m} · ${CH.vietstock ? 'Wealbee + Vietstock' : 'Wealbee'}</h3><div id="tinma" class="mut sm">Đang tải tin…</div></div>
    <div class="card"><h3>Doanh thu và lợi nhuận theo quý</h3>${bieuDoCot(kys, [
      {ten: 'Doanh thu', mau: '#4f8cff', gt: kys.map(k => gt((du.ky[k].income_statement || {}).revenue))},
      {ten: 'LNST', mau: '#22c55e', gt: kys.map(k => gt((du.ky[k].income_statement || {}).net_profit))}])}</div>
    ${bangChiTieu('Kết quả kinh doanh (quý, so với cùng quý năm trước)', inc)}${bangChiTieu('Cân đối kế toán (cuối kỳ so với đầu năm)', bs)}${bangChiTieu(`Lưu chuyển tiền tệ (luỹ kế ${st.months_ytd || ''} tháng, so với cùng kỳ)`, cf)}
    <div class="card sm"><h3>Nguồn gốc số liệu</h3>
      ${ng.document_url ? `<div>File gốc: <a href="${esc(ng.document_url)}" target="_blank" rel="noopener">${esc(ng.document_url.slice(0, 80))}</a></div>` : ''}
      ${ng.pages ? `<div class="mut">Trang: ${esc(Object.entries(ng.pages).map(([k, v]) => `${nhanKhoa(k)} tr.${v}`).join(' · '))}</div>` : ''}
      ${ng.source ? `<div class="mut">Nguồn file: ${esc(ng.source)}${ng.model ? ` · chép số bằng ${esc(ng.model)}` : ''}</div>` : ''}
      ${[['detected_at', 'Wealbee thấy file'], ['extracted_at', 'Chép xong số'], ['first_published_at', 'Công bố trên API']].filter(([k]) => ng[k])
        .map(([k, t]) => `<div class="mut">${t}: ${tg(ng[k])}</div>`).join('')}
      ${ng.detected_at && ng.first_published_at ? `<div>Độ trễ thấy file → có số: <b>${so((new Date(ng.first_published_at) - new Date(ng.detected_at)) / 36e5, 1)} giờ</b></div>` : ''}
      ${st.review_reasons?.length ? `<div style="color:var(--warn)">Cần soát: ${esc(st.review_reasons.join('; '))}</div>` : ''}</div></div>`;
  veGia(m); veTinMa(m);
}

async function veGia(m) {
  const to = Math.floor(Date.now() / 1000), fr = to - 366 * 86400;
  try {
    let j = CH.vietstock ? await taiJson(`../vietstock/gia/${m}.json`) : null;
    if (!j?.t?.length) { j = await (await fetch(`https://dchart-api.vndirect.com.vn/dchart/history?resolution=D&symbol=${m}&from=${fr}&to=${to}`)).json();
      if ($('#nguon_gia')) $('#nguon_gia').textContent = 'VNDirect'; }
    if (!j.t?.length) throw 0;
    const k = Math.max(...j.c) < 1000 ? 1000 : 1, c = j.c.map(v => v * k), dau = c[0], cuoi = c[c.length - 1], d = pct(cuoi, dau);
    if (D.chon !== m) return;
    $('#gia').className = '';
    $('#gia').innerHTML = `<div style="display:flex;gap:16px;align-items:baseline;flex-wrap:wrap"><div class="big">${so(cuoi)}</div>
      <div class="${d >= 0 ? 'up' : 'down'}">${d >= 0 ? '▲' : '▼'} ${so(Math.abs(d), 1)}% trong 12 tháng</div><div class="sm mut2">đồng · phiên ${new Date(j.t[j.t.length - 1] * 1000).toLocaleDateString('vi-VN')}</div></div>
      ${bieuDoDuong([{ten: m, mau: '#7c5cff', diem: j.t.map((t, i) => [t * 1000, c[i] / 1000])}], {donVi: 'k'})}`;
  } catch { if (D.chon === m) $('#gia').innerHTML = 'Không lấy được giá.'; }
}

main();
