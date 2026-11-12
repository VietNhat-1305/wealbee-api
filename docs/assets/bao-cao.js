// Trang báo cáo đánh giá Wealbee Data API (giải mã bằng mật khẩu nội bộ). Số liệu do wb_api/bao_cao.py dựng mỗi giờ.
// Bố cục: kết luận → vấn đề cần trao đổi → điểm mạnh / đã cải thiện → bảng chấm → biểu đồ → chi tiết → gói Free → phương pháp.
const XEP = {dat: 'Đạt', kha: 'Khá', chua_dat: 'Chưa đạt', chua_du: 'Chưa đủ dữ liệu'};
const MUC = {cao: 'Cao', trung_binh: 'Trung bình', thap: 'Thấp'};
const TEN_NGUON = {github: 'Mỹ (GitHub Actions)', 'may-vn': 'Việt Nam'};
const MAU_NGUON = {github: '#7c5cff', 'may-vn': '#22c55e'};
const TEN_EP = {me: 'Thông tin gói', companies: 'Danh sách công ty', company: 'Chi tiết công ty', latest: 'BCTC mới nhất của 1 mã',
  statements_list: 'Danh sách BCTC', statements_page2: 'Danh sách BCTC, trang 2', statement_full: 'BCTC đầy đủ', versions: 'Lịch sử phiên bản',
  filings: 'Danh sách file BCTC', events: 'Sự kiện', news: 'Tin tức', news_detail: 'Chi tiết tin', news_ma: 'Tin theo mã'};
const Y_NGHIA = {
  kha_dung: 'Tỷ lệ request trả kết quả đúng. Lỗi do máy đo mất mạng không tính.',
  do_tre: '95% request xong trong khoảng thời gian này (đo từ Việt Nam, kết nối đã mở).',
  ttfb: 'Thời gian chờ tới byte đầu tiên của phản hồi, trung vị.',
  loi_may_chu: 'Lỗi 5xx, quá thời gian hoặc rớt kết nối khi mạng của máy đo vẫn bình thường.',
  on_dinh: 'Tỷ lệ request mất hơn 1 giây. Càng thấp thì tốc độ càng đều.',
  chuan_loi: 'Lỗi 400 / 401 / 404 có đúng mã HTTP và đúng định dạng RFC 9457 không.',
  rate_limit: 'Có báo hạn mức còn lại (header RateLimit) và chặn bằng 429 kèm Retry-After đúng lúc không.',
  do_tuoi: 'Từ lúc Wealbee thấy file BCTC tới lúc có số trên API, trung vị. Wealbee cam kết 15 phút.',
  chat_luong: 'Tỷ lệ BCTC đã qua kiểm tra (verified), trên toàn bộ BCTC đã đồng bộ.',
  do_phu: 'Số công ty đã có BCTC của quý mới nhất.',
  bao_mat: 'TLS ≥ 1.2, HSTS, tự chuyển http → https, từ chối khoá API gửi qua URL.',
};
const pt = x => x == null ? '—' : (Math.round(x * 100) / 100).toLocaleString('vi-VN');
const ngay = s => s ? new Date(s).toLocaleDateString('vi-VN', {day: '2-digit', month: '2-digit', timeZone: 'Asia/Ho_Chi_Minh'}) : '—';
function gtTc(t) {
  const v = t.gia_tri;
  if (v == null) return '—';
  if (t.don_vi === '%') return pt(v) + '%';
  if (t.don_vi === '% có header') return pt(v) + '% có header';
  if (t.don_vi === '/4') return v + '/4';
  if (t.don_vi === 'ms') return so(v) + ' ms';
  if (t.don_vi === 'phút') return so(v) + ' phút';
  return so(v) + (t.don_vi ? ' ' + t.don_vi : '');
}
const the = (tieuDe, noiDung, them = '') => `<div class="card" ${them}><h2>${tieuDe}</h2>${noiDung}</div>`;

function hero(bc) {
  return `<section class="hero"><span class="pill">Cập nhật ${tg(bc.tao_luc)}</span>
    <h1 style="margin-top:12px">Đánh giá Wealbee Data API</h1>
    <p class="mut">Đo tự động mỗi giờ từ ${bc.nguon.map(n => TEN_NGUON[n] || n).join(' và ')}, chấm theo 11 tiêu chí của một API dữ liệu
    cho doanh nghiệp. Số liệu từ ${tg(bc.tu)} đến ${tg(bc.den)}.</p></section>`;
}

function ketLuan(bc) {
  const g = bc.goi.dn, nd = bc.nhan_dinh, t = g.tong;
  return `<div class="grid bc-dau">
    <div class="card"><h3>Gói Doanh nghiệp</h3><div style="display:flex;align-items:baseline;gap:10px">
      <div class="big">${g.diem == null ? '—' : so(g.diem, 1)}</div><div class="mut">/100</div><span class="tag ${g.xep}">${XEP[g.xep]}</span></div>
      <div class="bar" style="margin:10px 0 8px"><i style="width:${g.diem || 0}%"></i></div>
      <div class="sm mut">${so(t.so_luot)} lượt đo hợp lệ · ${so(t.so_request_cham)} request được chấm</div></div>
    <div class="card"><h3>Kết luận</h3><p style="margin:0;font-size:16px;line-height:1.65">${esc(nd.ket_luan)}</p></div></div>`;
}

function kpis(bc) {
  const g = bc.goi.dn, tc = Object.fromEntries(g.tieu_chi.map(x => [x.ma, x]));
  const o = (ma, nhan, phu) => { const x = tc[ma]; return `<div class="card kpi"><div class="l">${nhan}</div><div class="v">${gtTc(x)}</div>
    <div class="sm"><span class="tag ${x.xep}">${XEP[x.xep]}</span> <span class="mut2 xs">mục tiêu ${esc(x.nguong)}</span></div>${phu ? `<div class="xs mut2" style="margin-top:4px">${phu}</div>` : ''}</div>`; };
  const tu = bc.web?.tuoi || {};
  return `<div class="grid g5" style="margin-top:16px">${o('kha_dung', 'Request thành công')}${o('do_tre', 'Độ trễ p95 (từ Việt Nam)')}
    ${o('do_tuoi', 'Độ tươi BCTC', tu.n ? `${pt(tu.trong_15p)}% trong 15 phút · ${pt(tu.trong_60p)}% trong 1 giờ` : '')}
    ${o('chat_luong', 'BCTC đã kiểm chứng')}${o('do_phu', 'Công ty có BCTC quý mới')}</div>`;
}

function vanDe(bc) {
  const ds = bc.nhan_dinh.van_de || [];
  if (!ds.length) return the('Vấn đề cần trao đổi với Wealbee', '<div class="sm mut">Không có vấn đề nào đáng kể.</div>');
  return the(`Vấn đề cần trao đổi với Wealbee <span class="pill" style="vertical-align:3px">${ds.length}</span>`,
    ds.map(x => `<div class="bc-vd"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span class="bc-muc ${x.muc}">${MUC[x.muc] || x.muc}</span>
      <b>${esc(x.tieu_de)}</b></div><div class="sm" style="margin-top:6px">${esc(x.chi_tiet)}</div>
      <div class="sm mut" style="margin-top:4px">→ ${esc(x.de_xuat)}</div></div>`).join(''));
}

function manhVaSua(bc) {
  const nd = bc.nhan_dinh;
  const ds = (xs, dau, lop) => xs.length ? `<ul class="bc-ds">${xs.map(x => `<li><span class="${lop}">${dau}</span><span class="sm">${esc(x)}</span></li>`).join('')}</ul>`
    : '<div class="sm mut">Chưa có.</div>';
  return `<div class="grid g2">${the('Điểm mạnh', ds(nd.diem_manh, '✓', 'up'))}
    ${the('Wealbee đã cải thiện trong thời gian theo dõi', ds(nd.da_sua, '▲', 'up'))}</div>`;
}

function bangTieuChi(bc) {
  const g = bc.goi.dn;
  return the('Bảng chấm 11 tiêu chí (gói Doanh nghiệp)', `<div style="overflow-x:auto"><table>
    <tr><th>Tiêu chí</th><th class="n">Kết quả</th><th class="n">Mục tiêu</th><th class="n">Xếp hạng</th><th class="n">Trọng số</th></tr>
    ${g.tieu_chi.map(t => `<tr><td><b>${esc(t.ten)}</b><div class="xs mut2">${esc(Y_NGHIA[t.ma] || '')}</div></td>
      <td class="n">${gtTc(t)}</td><td class="n sm mut">${esc(t.nguong)}</td><td class="n"><span class="tag ${t.xep}">${XEP[t.xep]}</span></td>
      <td class="n">${t.trong_so}</td></tr>`).join('')}</table></div>
    <div class="xs mut2" style="margin-top:8px">Điểm tổng = trung bình có trọng số: Đạt tính 100%, Khá 60%, Chưa đạt 15%; tiêu chí chưa đủ dữ liệu không tính.
    Xếp hạng tổng: từ 85 điểm là Đạt, từ 65 là Khá.</div>`);
}

function bieuDo(bc) {
  const tn = bc.goi.dn.theo_nguon || {};
  const tre = Object.entries(tn).map(([n, t]) => ({ten: `Đo từ ${TEN_NGUON[n] || n}`, mau: MAU_NGUON[n] || '#4f8cff',
    diem: (t.chuoi || []).map(c => [new Date(c.luc).getTime(), c.p50])}));
  const kd = Object.entries(tn).map(([n, t]) => ({ten: `Đo từ ${TEN_NGUON[n] || n}`, mau: MAU_NGUON[n] || '#4f8cff',
    diem: (t.chuoi || []).map(c => [new Date(c.luc).getTime(), c.n ? 100 * c.ok / c.n : null])}));
  return `<div class="grid g2">${the('Độ trễ trung vị mỗi lượt đo (ms)', bieuDoDuong(tre, {donVi: ''}))}
    ${the('Tỷ lệ request thành công mỗi lượt đo (%)', bieuDoDuong(kd, {donVi: '%'}) +
      `<div class="xs mut2" style="margin-top:6px">Khoảng trống là lúc máy đo tắt hoặc mất mạng, không phải API ngừng hoạt động.</div>`)}</div>`;
}

function bangEp(bc) {
  const tn = bc.goi.dn.theo_nguon || {}, ng = Object.keys(tn);
  const eps = [...new Set(ng.flatMap(n => Object.keys(tn[n].theo_ep || {})))];
  if (!eps.length) return '';
  const o = (n, e) => { const t = tn[n].theo_ep?.[e]; return t?.n ? `${so(t.p50)} / <b class="${t.p95 > 1000 ? 'down' : ''}">${so(t.p95)}</b>` : '—'; };
  return the('Độ trễ theo endpoint (trung vị / p95, ms)', `<div style="overflow-x:auto"><table>
    <tr><th>Endpoint</th>${ng.map(n => `<th class="n">Đo từ ${TEN_NGUON[n] || n}</th>`).join('')}</tr>
    ${eps.map(e => `<tr><td class="sm">${esc(TEN_EP[e] || e)} <span class="xs mut2">${esc(e)}</span></td>${ng.map(n => `<td class="n">${o(n, e)}</td>`).join('')}</tr>`).join('')}
    </table></div><div class="xs mut2" style="margin-top:6px">Không tính lượt đầu của mỗi kết nối (có bắt tay TLS). p95 trên 1 giây tô đỏ.
    Đo từ Mỹ chậm hơn vì máy chủ Wealbee đặt ở châu Á.</div>`);
}

function duLieu(bc) {
  const w = bc.web || {}, tu = w.tuoi || {};
  if (!w.so_bctc) return '';
  const chia = [[tu.trong_15p, '≤ 15 phút', '#22c55e'], [tu.trong_60p - tu.trong_15p, '15–60 phút', '#86efac'],
    [tu.trong_24h - tu.trong_60p, '1–24 giờ', '#f59e0b'], [100 - tu.trong_24h, 'trên 24 giờ', '#f43f5e']];
  const tuoi = `<div class="bc-chia">${chia.map(([v, , m]) => `<i style="width:${Math.max(0, v || 0)}%;background:${m}"></i>`).join('')}</div>
    <div class="legend" style="margin-top:8px">${chia.map(([v, t, m]) => `<span><b style="background:${m}"></b>${t}: ${pt(v)}%</span>`).join('')}</div>
    <table style="margin-top:10px"><tr><td class="sm">Trung vị (thấy file → có số)</td><td class="n"><b>${so(tu.p50)} phút</b></td></tr>
    <tr><td class="sm">10% BCTC chậm nhất mất hơn</td><td class="n">${so(tu.p90 / 60, 1)} giờ</td></tr>
    <tr><td class="sm">Thấy file → chép xong số (trung vị)</td><td class="n">${so(tu.chep_p50)} phút</td></tr>
    <tr><td class="sm">BCTC tính được</td><td class="n">${so(tu.n)}${tu.bat_thuong ? ` <span class="xs mut2">(${tu.bat_thuong} mốc bất thường không tính)</span>` : ''}</td></tr></table>`;
  const tt = w.trang_thai || {};
  const cl = `<table><tr><td class="sm">Đã kiểm chứng (verified)</td><td class="n"><b>${so(tt.verified || 0)}</b> · ${pt(w.verified)}%</td></tr>
    <tr><td class="sm">Cần soát (needs_review)</td><td class="n">${so(tt.needs_review || 0)}</td></tr>
    <tr><td class="sm">Phép kiểm tự động đạt</td><td class="n">${so(w.kiem[0])}/${so(w.kiem[1])} · ${pt(w.kiem_dat)}%</td></tr></table>
    ${w.ly_do?.length ? `<div class="sm" style="margin-top:10px"><b>Lý do cần soát hay gặp</b><ul style="margin:6px 0 0;padding-left:18px">
      ${w.ly_do.map(([a, b]) => `<li>${esc(a)}: ${so(b)}</li>`).join('')}</ul></div>` : ''}`;
  return `<div class="grid g2">${the(`Độ tươi BCTC <span class="xs mut2">(${so(w.so_bctc)} BCTC đã đồng bộ)</span>`, tuoi)}${the('Chất lượng BCTC', cl)}</div>`;
}

function tinTuc(bc) {
  const tin = bc.goi.dn.tin || {}, m = tin.mau || {};
  if (!tin.n && !m.n) return '';
  const vn = bc.goi.dn.theo_nguon?.['may-vn']?.theo_ep || bc.goi.dn.tong.theo_ep || {};
  const ep = ['news', 'news_detail', 'news_ma'].filter(e => vn[e]?.n).map(e => `${TEN_EP[e]} ${so(vn[e].p50)} / ${so(vn[e].p95)} ms`).join(' · ');
  return the('Tin tức qua Data API (/news)', `<table>
    <tr><td class="sm">Số tin đã theo dõi</td><td class="n">${so(tin.n)}</td></tr>
    <tr><td class="sm">Bài gốc đầu tiên → Wealbee có tin (trung vị)</td><td class="n"><b>${so(tin.tre?.p50)} phút</b></td></tr>
    <tr><td class="sm">Có tin trong 15 phút / 1 giờ</td><td class="n">${pt(tin.trong_15p)}% / ${pt(tin.trong_60p)}%</td></tr>
    ${m.n ? `<tr><td class="sm">Trong ${m.n} tin mới nhất: có tóm tắt / có bài phân tích / gắn mã</td><td class="n">${m.co_tom_tat} / ${m.co_phan_tich} / ${m.co_ma}</td></tr>` : ''}
    ${ep ? `<tr><td class="sm">Độ trễ (trung vị / p95, đo từ Việt Nam)</td><td class="n sm">${ep}</td></tr>` : ''}</table>
    <div class="xs mut2" style="margin-top:8px">Endpoint mới của Data API (11/2026): lọc theo mã, kèm nguồn bài gốc, sắc thái, phân loại tin.</div>`);
}

function rlBaoMat(bc) {
  const t = bc.goi.dn.tong, d = bc.goi.dn.ban_don, b = bc.bao_mat || {}, ml = t.ma_la || {};
  const cs = t.chinh_sach_rl;
  const rl = `<table>
    <tr><td class="sm">Hạn mức (header RateLimit-Policy)</td><td class="n">${cs ? `${cs.q} request / ${cs.w} giây` : '—'}</td></tr>
    <tr><td class="sm">Phản hồi có header RateLimit</td><td class="n">${pt(t.co_header_rl)}%</td></tr>
    <tr><td class="sm">Bắn dồn gần nhất</td><td class="n sm">${d ? (d.luot_429 ? `bị 429 ở request thứ ${d.luot_429} · Retry-After ${esc(d.retry_after ?? 'thiếu')} · chờ xong gọi lại: ${d.sau_retry_after ?? '—'}`
      : `${d.so_luot} request liên tục, chưa bị 429`) : 'chưa chạy'}</td></tr>
    <tr><td class="sm">Lỗi 400 / 401 / 404 đúng mã và RFC 9457</td><td class="n">${so(Math.min(t.chuan_loi.dung_ma, t.chuan_loi.rfc9457))}/${so(t.chuan_loi.n)}</td></tr>
    <tr><td class="sm">Gọi mã không tồn tại trả về</td><td class="n">${esc(ml.hien_tai || '—')}</td></tr></table>`;
  const y = (v, ten) => `<tr><td class="sm">${ten}</td><td class="n"><span class="tag ${v ? 'dat' : 'chua_dat'}">${v ? 'Có' : 'Không'}</span></td></tr>`;
  const bm = `<table><tr><td class="sm">Phiên bản TLS</td><td class="n">${esc(b.tls || '—')}</td></tr>
    <tr><td class="sm">Chứng chỉ</td><td class="n">${esc(b.cap_boi || '')} · còn ${b.chung_chi_con_ngay ?? '—'} ngày</td></tr>
    ${y(b.hsts, 'HSTS (Strict-Transport-Security)')}${y(b.http_sang_https, 'Tự chuyển http → https')}${y(b.khoa_qua_query_bi_tu_choi, 'Từ chối khoá API gửi qua URL')}</table>`;
  return `<div class="grid g2">${the('Giới hạn tốc độ và báo lỗi', rl)}${the('Bảo mật', bm)}</div>`;
}

function goiFree(bc) {
  const f = bc.goi.free, d = bc.goi.dn, qf = f.quyen || {}, qd = d.quyen || {};
  const DONG = [['rate_limit_per_minute', 'Request mỗi phút'], ['exchanges', 'Sàn'], ['products', 'Sản phẩm'], ['include_score', 'Điểm sức khoẻ tài chính'],
    ['redistribution', 'Được hiển thị lại cho khách'], ['max_webhook_endpoints', 'Số webhook'], ['delay_minutes', 'Độ trễ dữ liệu (phút)'], ['valid_until', 'Hiệu lực đến']];
  const v = x => x == null ? '—' : Array.isArray(x) ? x.join(', ') : x === true ? 'Có' : x === false ? 'Không' : /T\d\d:/.test(x) ? ngay(x) : x;
  return the('Gói Free và so sánh quyền 2 gói', `${f.ghi_chu_goi ? `<div class="sm" style="margin-bottom:12px">${esc(f.ghi_chu_goi)}</div>` : ''}
    <div style="overflow-x:auto"><table><tr><th>Quyền (từ GET /v1/me)</th><th class="n">Gói Free</th><th class="n">Gói Doanh nghiệp</th></tr>
    ${DONG.map(([k, t]) => `<tr><td class="sm">${t}</td><td class="n sm">${esc(v(qf[k]))}</td><td class="n sm">${esc(v(qd[k]))}</td></tr>`).join('')}</table></div>
    ${f.tong.so_luot ? `<div class="xs mut2" style="margin-top:8px">Số đo tham khảo của gói Free (${f.tong.so_luot} lượt, ${ngay(f.tu)}):
      ${pt(f.tong.kha_dung)}% thành công, trung vị ${so(f.tong.do_tre.p50)} ms, p95 ${so(f.tong.do_tre.p95)} ms.</div>` : ''}`);
}

function apiKhac(bc) {
  const TEN = {vs_gia: 'Vietstock · giá (miễn phí)', vs_tin_rss: 'Vietstock · tin RSS (miễn phí)', tin_moi: 'App Wealbee · tin mới', tin_theo_ma: 'App Wealbee · tin theo mã'};
  const dong = nhom => Object.entries(nhom?.theo_ep || {}).map(([e, t]) => `<tr><td class="sm">${esc(TEN[e] || e)}</td>
    <td class="n">${t.n ? `${so(t.p50)} / ${so(t.p95)} ms` : '—'}</td><td class="n">${nhom.n ? pt(100 * nhom.ok / nhom.n) + '%' : '—'}</td></tr>`).join('');
  const vn = bc.goi.dn.theo_nguon?.['may-vn'] || bc.goi.dn.tong;
  return the('So với các API khác', `<div style="overflow-x:auto"><table><tr><th>API</th><th class="n">Trung vị / p95</th><th class="n">Thành công</th></tr>
    <tr><td class="sm"><b>Wealbee Data API</b> (gói Doanh nghiệp, đo từ Việt Nam)</td><td class="n"><b>${so(vn.do_tre.p50)} / ${so(vn.do_tre.p95)} ms</b></td><td class="n"><b>${pt(vn.kha_dung)}%</b></td></tr>
    ${dong(bc.vietstock)}${dong(bc.tin_app)}</table></div>
    <div class="xs mut2" style="margin-top:8px">Vietstock miễn phí chỉ có giá và tin RSS (API dữ liệu chính thức DataFeed phải mua), không có BCTC đã kiểm chứng,
    nguồn gốc số liệu hay lịch sử phiên bản như Wealbee. API tin của app Wealbee là API nội bộ của app, nay đã có /news trong Data API thay thế.</div>`);
}

async function thayDoi(mk) {
  const r = await fetch('thay_doi.enc', {cache: 'no-store'});
  if (!r.ok) return '';
  let ds = []; try { ds = await moGoi(await r.json(), mk); } catch {}
  if (!ds.length) return '';
  const mot = (b, mo) => {
    const loai = b.loai_ban === 'ghi_chu' ? ['chua_du', 'Ghi chú'] : b.te_di.length ? (b.cai_thien.length ? ['kha', 'Lẫn lộn'] : ['chua_dat', 'Tệ đi']) : ['dat', 'Cải thiện'];
    return `<details ${mo ? 'open' : ''} style="border-top:1px solid var(--line);padding:10px 0"><summary style="cursor:pointer">
      <span class="tag ${loai[0]}">${loai[1]}</span> <b>${tg(b.luc)}</b> <span class="sm mut">${esc(b.tieu_de)}</span></summary>
      ${(b.ghi_chu || []).length ? `<ul class="sm">${b.ghi_chu.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${b.cai_thien.length ? `<div class="sm" style="margin-top:8px"><b class="up">▲ Cải thiện</b><ul>${b.cai_thien.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
      ${b.te_di.length ? `<div class="sm"><b class="down">▼ Tệ đi</b><ul>${b.te_di.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
      <div class="xs mut2">Điểm lúc đó: ${Object.entries(b.diem_hien_tai || {}).filter(([, d]) => d != null).map(([g, d]) => `${g === 'dn' ? 'Gói Doanh nghiệp' : 'Gói Free'} ${so(d, 1)}`).join(' · ') || '—'}</div></details>`;
  };
  return `<div class="card"><div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><h2 style="margin:0">Nhật ký thay đổi</h2>
    <span class="pill">${ds.length} bản</span><div class="sp"></div><span class="xs mut2">tự ghi khi có cải thiện hoặc tệ đi rõ rệt</span></div>
    ${ds.slice(0, 30).map((b, i) => mot(b, i === 0)).join('')}</div>`;
}

function phuongPhap(bc) {
  const gh = bc.nhan_dinh.gioi_han || [];
  return the('Phương pháp và giới hạn của phép đo', `<ul class="sm" style="margin:0;padding-left:18px;display:grid;gap:6px">
    <li>Mỗi giờ, máy đo gọi khoảng 17 endpoint của gói Doanh nghiệp: thông tin gói, công ty, BCTC (mới nhất, danh sách 2 trang, đầy đủ, lịch sử phiên bản), file BCTC,
      sự kiện, tin tức, cùng 3 lỗi cố ý (400 / 401 / 404) để kiểm cách báo lỗi. Bộ đo tự giữ nhịp dưới giới hạn tốc độ.</li>
    <li>Mỗi ngày 1 lần: bắn dồn để kiểm giới hạn tốc độ, kiểm bảo mật (TLS, HSTS, http → https, khoá qua URL) và đếm độ phủ.</li>
    <li>Hai góc đo: máy ở Việt Nam (gần với khách hàng thật, dùng để chấm độ trễ) và GitHub Actions ở Mỹ (để đối chiếu).</li>
    <li>Lỗi do máy đo mất mạng (DNS, hoặc cùng lúc các API khác cũng lỗi) bị loại khỏi phép tính. Độ tươi và chất lượng tính trên toàn bộ
      ${so(bc.web?.so_bctc)} BCTC đã đồng bộ về web, không chỉ vài BCTC mẫu.</li>
    <li>Điểm tổng là trung bình có trọng số: Đạt tính 100%, Khá 60%, Chưa đạt 15%; tiêu chí chưa đủ dữ liệu không tính. Mỗi gói cần ít nhất 12 lượt đo hợp lệ mới được chấm.</li>
    </ul>${gh.length ? `<h3 style="margin-top:14px">Giới hạn cần lưu ý</h3><ul class="sm" style="margin:0;padding-left:18px;display:grid;gap:6px">
    ${gh.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}`);
}

async function main() {
  const khung = $('#app');
  const r = await fetch('bao_cao.enc', {cache: 'no-store'});
  if (!r.ok) { khung.innerHTML = '<div class="card empty">Chưa có báo cáo: bộ quét chưa chạy lượt nào.</div>'; return; }
  const {du_lieu: bc, mk} = await congMatKhau('bao_cao.enc', khung, 'Báo cáo hiệu suất Wealbee API');
  if (bc.phien_ban !== 2) { khung.innerHTML = '<div class="card empty">Báo cáo đang được dựng lại theo cách tính mới, quay lại sau ít phút.</div>'; return; }
  const td = await thayDoi(mk);
  khung.innerHTML = `${hero(bc)}${ketLuan(bc)}${kpis(bc)}
    <div class="grid" style="margin-top:16px">${vanDe(bc)}${manhVaSua(bc)}${bangTieuChi(bc)}${bieuDo(bc)}${bangEp(bc)}${duLieu(bc)}
      ${tinTuc(bc)}${rlBaoMat(bc)}${goiFree(bc)}${apiKhac(bc)}${td}${phuongPhap(bc)}</div>`;
}
main();
