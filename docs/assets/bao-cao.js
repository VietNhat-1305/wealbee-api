// Trang báo cáo đánh giá hiệu suất Wealbee API (giải mã bằng mật khẩu nội bộ).
const XEP = {dat: 'Đạt', kha: 'Khá', chua_dat: 'Chưa đạt', chua_du: 'Chưa đủ dữ liệu'};
const TEN_GOI = {free: 'Gói Free', dn: 'Gói Doanh nghiệp'}, MAU = {free: '#f59e0b', dn: '#22c55e'};
const TEN_NGUON = {github: 'GitHub Actions (máy chủ Mỹ)', 'may-vn': 'Máy ở Việt Nam'};

function oDiem(ten, g) {
  const d = g.diem, xep = d == null ? 'chua_du' : d >= 85 ? 'dat' : d >= 65 ? 'kha' : 'chua_dat';
  return `<div class="card"><h3>${TEN_GOI[ten]}</h3><div style="display:flex;align-items:baseline;gap:10px"><div class="big">${d == null ? '—' : so(d, 1)}</div>
    <div class="mut">/100</div><span class="tag ${xep}">${XEP[xep]}</span></div>
    <div class="sm mut">${so(g.tong.so_luot_quet)} lượt quét · ${so(g.tong.so_request)} request${g.tong.bo_qua ? ` · ${esc(g.tong.bo_qua)}` : ''}</div>
    <div class="bar" style="margin-top:10px"><i style="width:${d || 0}%"></i></div></div>`;
}

function bangTieuChi(bc) {
  const tc = {free: bc.goi.free.tieu_chi, dn: bc.goi.dn.tieu_chi};
  return `<div class="card"><h2>Bảng chấm theo tiêu chí doanh nghiệp</h2><div style="overflow-x:auto"><table>
    <tr><th>Tiêu chí</th><th>Ngưỡng đạt</th><th class="n">Trọng số</th><th class="n">Gói Free</th><th class="n">Gói Doanh nghiệp</th></tr>
    ${tc.dn.map((t, i) => { const f = tc.free[i];
      const o = x => `${x.gia_tri == null ? '—' : so(x.gia_tri, x.gia_tri < 10 ? 2 : 1)} ${esc(x.don_vi)} <span class="tag ${x.xep}">${XEP[x.xep]}</span>`;
      return `<tr><td><b>${esc(t.ten)}</b></td><td class="sm mut">${esc(t.nguong)}</td><td class="n">${t.trong_so}</td><td class="n">${o(f)}</td><td class="n">${o(t)}</td></tr>`; }).join('')}
  </table></div></div>`;
}

function bieuDoTre(bc) {
  const s = [];
  for (const [g, v] of Object.entries(bc.goi)) for (const [n, t] of Object.entries(v.theo_nguon || {}))
    s.push({ten: `${TEN_GOI[g]} · ${TEN_NGUON[n] || n}`, mau: n === 'github' ? MAU[g] : (g === 'dn' ? '#86efac' : '#fde68a'),
            diem: (t.chuoi || []).map(c => [new Date(c.luc).getTime(), c.p50])});
  const kd = [];
  for (const [g, v] of Object.entries(bc.goi)) kd.push({ten: TEN_GOI[g], mau: MAU[g],
    diem: (v.tong.chuoi || []).map(c => [new Date(c.luc).getTime(), c.n ? 100 * c.ok / c.n : null])});
  return `<div class="grid g2"><div class="card"><h2>Độ trễ trung vị mỗi lượt quét (ms)</h2>${bieuDoDuong(s, {donVi: ''})}</div>
    <div class="card"><h2>Tỷ lệ request thành công mỗi lượt (%)</h2>${bieuDoDuong(kd, {donVi: '%'})}</div></div>`;
}

function bangEp(bc) {
  const eps = [...new Set(Object.values(bc.goi).flatMap(v => Object.keys(v.tong.theo_ep || {})))];
  if (!eps.length) return '';
  const o = (g, e) => { const t = bc.goi[g].tong.theo_ep?.[e]; return t?.n ? `${so(t.p50)} / ${so(t.p95)} / ${so(t.p99)}` : '—'; };
  return `<div class="card"><h2>Độ trễ theo endpoint (p50 / p95 / p99, ms)</h2><div style="overflow-x:auto"><table>
    <tr><th>Bài đo</th><th class="n">Gói Free</th><th class="n">Gói Doanh nghiệp</th></tr>
    ${eps.map(e => `<tr><td class="sm">${esc(e)}</td><td class="n">${o('free', e)}</td><td class="n">${o('dn', e)}</td></tr>`).join('')}</table></div>
    <div class="xs mut2">Không tính lượt đầu của mỗi kết nối (có bắt tay TLS); lượt đầu tính riêng ở mục "kết nối lạnh".</div></div>`;
}

function chiTiet(bc) {
  const o = (g, f) => { const v = bc.goi[g].tong; try { return f(v) ?? '—'; } catch { return '—'; } };
  const dong = [
    ['Tỷ lệ thành công', v => v.kha_dung == null ? null : so(v.kha_dung, 3) + '%'],
    ['Lỗi máy chủ / mạng', v => v.loi_may_chu == null ? null : so(v.loi_may_chu, 3) + '%'],
    ['Độ trễ p50 / p95 / p99', v => v.do_tre.n ? `${so(v.do_tre.p50)} / ${so(v.do_tre.p95)} / ${so(v.do_tre.p99)} ms` : null],
    ['TTFB p50', v => v.ttfb.n ? so(v.ttfb.p50) + ' ms' : null],
    ['Kết nối lạnh (có TLS) p50', v => v.lanh.n ? so(v.lanh.p50) + ' ms' : null],
    ['Giới hạn tốc độ (header)', v => v.rate_limit.chinh_sach ? `${v.rate_limit.chinh_sach.q} request / ${v.rate_limit.chinh_sach.w}s` : null],
    ['Kiểm 429 gần nhất', v => { const b = v.rate_limit.ban_don; return b ? (b.luot_429 ? `bị 429 ở lượt ${b.luot_429}/${b.so_luot} · Retry-After ${b.retry_after ?? 'thiếu'} · chờ xong gọi lại: ${b.sau_retry_after ?? '—'}` : `không bị 429 sau ${b.so_luot} lượt liên tục`) + ` · ${b.rps} req/s` : null; }],
    ['Độ tươi (thấy file → có số)', v => v.do_tuoi.n ? `trung vị ${so(v.do_tuoi.trung_vi_phut, 1)} phút · ${so(v.do_tuoi.ty_le_15p, 1)}% ≤ 15 phút (n=${v.do_tuoi.n})` : null],
    ['Độ trễ dữ liệu (Wealbee-Effective-Time)', v => v.do_tre_du_lieu_s.n ? `trung vị ${so(v.do_tre_du_lieu_s.p50)} giây` : null],
    ['BCTC verified / phép kiểm đạt', v => v.chat_luong.verified == null ? null : `${so(v.chat_luong.verified, 1)}% / ${so(v.chat_luong.kiem_dat, 1)}%`],
    ['Số công ty được phủ', v => v.so_cong_ty ? so(v.so_cong_ty) : null],
    ['Lỗi gặp phải', v => Object.keys(v.loi || {}).length ? Object.entries(v.loi).map(([k, n]) => `${k}: ${n}`).join(', ') : 'không'],
  ];
  return `<div class="card"><h2>Số đo chi tiết</h2><div style="overflow-x:auto"><table><tr><th>Chỉ số</th><th class="n">Gói Free</th><th class="n">Gói Doanh nghiệp</th></tr>
    ${dong.map(([t, f]) => `<tr><td class="sm">${t}</td><td class="n sm">${esc(o('free', f))}</td><td class="n sm">${esc(o('dn', f))}</td></tr>`).join('')}</table></div></div>`;
}

function quyen(bc) {
  const q = g => bc.goi[g].tong.quyen || {};
  const keys = [...new Set([...Object.keys(q('free')), ...Object.keys(q('dn'))])];
  if (!keys.length) return '';
  return `<div class="card"><h2>So sánh quyền của 2 gói (từ GET /v1/me)</h2><table><tr><th>Quyền</th><th class="n">Gói Free</th><th class="n">Gói Doanh nghiệp</th></tr>
    ${keys.map(k => `<tr><td class="sm">${esc(k)}</td><td class="n sm">${esc(JSON.stringify(q('free')[k] ?? '—'))}</td><td class="n sm">${esc(JSON.stringify(q('dn')[k] ?? '—'))}</td></tr>`).join('')}</table></div>`;
}

function baoMat(bc) {
  const b = bc.bao_mat; if (!b) return '';
  const y = (v, t) => `<tr><td class="sm">${t}</td><td class="n"><span class="tag ${v ? 'dat' : 'chua_dat'}">${v ? 'Có' : 'Không'}</span></td></tr>`;
  return `<div class="card"><h2>Bảo mật</h2><table>
    <tr><td class="sm">Phiên bản TLS</td><td class="n">${esc(b.tls || b.tls_loi || '—')}</td></tr>
    <tr><td class="sm">Chứng chỉ (còn hạn)</td><td class="n">${esc(b.cap_boi || '')} · ${b.chung_chi_con_ngay ?? '—'} ngày</td></tr>
    ${y(b.hsts, 'Header HSTS (Strict-Transport-Security)')}${y(b.http_sang_https, 'Tự chuyển http → https')}
    ${b.khoa_qua_query_bi_tu_choi != null ? y(b.khoa_qua_query_bi_tu_choi, 'Từ chối khoá gửi qua URL (query string)') : ''}</table></div>`;
}

async function main() {
  const khung = $('#app');
  const r = await fetch('bao_cao.enc', {cache: 'no-store'});
  if (!r.ok) { khung.innerHTML = '<div class="card empty">Chưa có báo cáo: bộ quét chưa chạy lượt nào.</div>'; return; }
  const {du_lieu: bc} = await congMatKhau('bao_cao.enc', khung, 'Báo cáo hiệu suất Wealbee API');
  khung.innerHTML = `<section class="hero"><span class="pill">Cập nhật ${tg(bc.tao_luc)}</span>
      <h1 style="margin-top:12px">Đánh giá hiệu suất Wealbee Data API</h1>
      <p class="mut">Quét tự động mỗi giờ từ ${bc.nguon.map(n => TEN_NGUON[n] || n).join(' và ') || '—'}, so sánh gói Free với gói Doanh nghiệp theo các tiêu chí của một API dữ liệu cho doanh nghiệp.
      Dữ liệu từ ${tg(bc.tu)} đến ${tg(bc.den)} (${so(bc.so_luot)} bản ghi, 30 ngày gần nhất).</p></section>
    <div class="grid g3">${oDiem('free', bc.goi.free)}${oDiem('dn', bc.goi.dn)}
      <div class="card"><h3>Health check (không cần khoá)</h3><div class="big">${bc.health.n ? so(100 * bc.health.ok / bc.health.n, 2) : '—'}<span class="mut" style="font-size:18px">%</span></div>
      <div class="sm mut">${so(bc.health.n)} lượt · p50 ${so(bc.health.do_tre.p50)} ms · p95 ${so(bc.health.do_tre.p95)} ms</div></div></div>
    <div class="card" style="margin-top:16px"><h2>Nhận xét chính</h2><ul>${bc.nhan_xet.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
    <div class="grid" style="margin-top:16px">${bangTieuChi(bc)}${bieuDoTre(bc)}${chiTiet(bc)}${bangEp(bc)}<div class="grid g2">${quyen(bc)}${baoMat(bc)}</div>
    <div class="card sm mut"><h2>Phương pháp</h2><ul>
      <li>Mỗi giờ: health check + 13 bài đo cho mỗi gói (me, companies, company, statement mới nhất, danh sách 2 trang, statement đầy đủ, versions, filings, events, lỗi 400 / 401 / 404). Bộ đo tự giữ nhịp dưới giới hạn tốc độ.</li>
      <li>Mỗi ngày 1 lần: bắn dồn để kiểm giới hạn tốc độ (lúc nào bị 429, có Retry-After không, chờ xong có gọi lại được không) và kiểm bảo mật (TLS, HSTS, http → https, khoá qua URL).</li>
      <li>Hai góc đo: GitHub Actions chạy liên tục (máy chủ ở Mỹ, độ trễ mạng cao hơn người dùng Việt Nam), máy ở Việt Nam chạy khi máy bật. Lịch GitHub có thể trễ / bỏ lượt: khoảng trống không có nghĩa là API sập.</li>
      <li>Điểm tổng = trung bình có trọng số (Đạt 100%, Khá 60%, Chưa đạt 15%), bỏ tiêu chí chưa đủ dữ liệu.</li></ul></div></div>`;
}
main();
