// Trang theo dõi sức khoẻ SEO wealbee.com (giải mã bằng mật khẩu nội bộ). Số liệu do wb_seo/chay.py dựng mỗi ngày.
const XEP = {dat: 'Đạt', canh_bao: 'Cảnh báo', loi: 'Lỗi', chua_do: 'Chưa đo'};
const LOP = {dat: 'dat', canh_bao: 'kha', loi: 'chua_dat', chua_do: 'chua_du'};
const MUC = {cao: ['Xấu đi', 'chua_dat'], trung_binh: ['Cần để ý', 'kha'], tot: ['Tốt lên', 'dat']};
const msVn = x => x == null ? '—' : x >= 1000 ? so(x / 1000, 1) + ' s' : so(x) + ' ms';

function dau(bc) {
  const d = bc.diem, xep = d == null ? 'chua_du' : d >= 85 ? 'dat' : d >= 60 ? 'kha' : 'chua_dat';
  const dem = x => bc.chi_so.filter(c => c.xep === x).length;
  return `<section class="hero"><span class="pill">Kiểm lần cuối ${tg(bc.tao_luc)}</span><h1 style="margin-top:12px">Sức khoẻ SEO wealbee.com</h1>
    <p class="mut">${bc.chi_so.length} chỉ số trong 5 nhóm: khả năng được tìm thấy, thẻ trên trang, tốc độ trên điện thoại, liên kết và bảo mật.
    Mỗi chỉ số có ngưỡng và căn cứ ở bảng dưới.</p></section>
    <div class="grid bc-dau"><div class="card"><h3>Điểm sức khoẻ</h3><div style="display:flex;align-items:baseline;gap:10px">
      <div class="big">${d == null ? '—' : so(d, 1)}</div><div class="mut">/100</div><span class="tag ${xep}">${xep === 'dat' ? 'Tốt' : xep === 'kha' ? 'Trung bình' : 'Kém'}</span></div>
      <div class="bar" style="margin:10px 0 8px"><i style="width:${d || 0}%"></i></div>
      <div class="sm"><span class="tag dat">Đạt ${dem('dat')}</span> <span class="tag kha">Cảnh báo ${dem('canh_bao')}</span> <span class="tag chua_dat">Lỗi ${dem('loi')}</span></div></div>
      <div class="card"><h3>Điểm theo ngày</h3>${bieuDoDuong([{ten: 'Điểm sức khoẻ', mau: '#4f8cff', diem: bc.lich_su.map(r => [new Date(r.luc).getTime(), r.diem])}], {cao: 170})}</div></div>`;
}

function canhBao(bc) {
  const ds = bc.canh_bao || [];
  if (!ds.length) return '';
  return `<div class="card"><h2>Cảnh báo gần đây</h2>${ds.slice(0, 20).map(c => `<div class="bc-vd"><span class="bc-muc ${MUC[c.muc]?.[1] === 'chua_dat' ? 'cao' : MUC[c.muc]?.[1] === 'kha' ? 'trung_binh' : 'thap'}">${MUC[c.muc]?.[0] || c.muc}</span>
    <span class="sm mut2" style="margin:0 8px">${tg(c.luc)}</span><span class="sm">${esc(c.chu)}</span></div>`).join('')}</div>`;
}

function bang(bc) {
  const nhom = Object.keys(bc.nhom);
  return `<div class="card"><h2>Bộ chỉ số, ngưỡng và căn cứ</h2><div style="overflow-x:auto"><table>
    <tr><th>Chỉ số</th><th class="n">Hiện tại</th><th>Ngưỡng đạt</th><th class="n">Trọng số</th><th class="n">Trạng thái</th></tr>
    ${nhom.map(n => `<tr><td colspan="5" class="xs mut2" style="padding-top:16px">${esc(bc.nhom[n]).toUpperCase()}</td></tr>` +
      bc.chi_so.filter(c => c.nhom === n).map(c => `<tr><td><b>${esc(c.ten)}</b><div class="xs mut2">${esc(c.can_cu)}</div></td>
        <td class="n sm">${esc(c.gia_tri)}</td><td class="sm mut">${esc(c.nguong)}</td><td class="n">${c.trong_so}</td>
        <td class="n"><span class="tag ${LOP[c.xep]}">${XEP[c.xep]}</span></td></tr>`).join('')).join('')}</table></div>
    <div class="xs mut2" style="margin-top:8px">Điểm = trung bình có trọng số (Đạt 100%, Cảnh báo 50%, Lỗi 0%); chỉ số chưa đo không tính.</div></div>`;
}

function tocDo(bc) {
  const td = bc.kiem_tra.toc_do || {}, ten = {trang_chu: 'Trang chủ', bai_viet: 'Bài viết mới nhất'};
  const ds = Object.entries(td).filter(([, v]) => v && typeof v === 'object');
  if (!ds.length) return '';
  const o = (v, tot, kem, f) => `<td class="n"><span class="${v <= tot ? 'up' : v <= kem ? '' : 'down'}">${f(v)}</span></td>`;
  const xu = bc.lich_su.filter(r => r.toc_do?.bai_viet);
  return `<div class="grid g2"><div class="card"><h2>Tốc độ trên điện thoại</h2><div style="overflow-x:auto"><table>
      <tr><th>Trang</th><th class="n">LCP</th><th class="n">CLS</th><th class="n">TBT</th><th class="n">Dung lượng</th><th class="n">Font</th></tr>
      ${ds.map(([k, v]) => `<tr><td class="sm"><a href="${esc(v.url)}" target="_blank" rel="noopener">${ten[k] || k}</a></td>${o(v.lcp, 2500, 4000, msVn)}${o(v.cls, 0.1, 0.25, x => so(x, 3))}${o(v.tbt, 200, 600, msVn)}
        <td class="n sm">${so(v.kb)} KB · ${v.so_request} req</td><td class="n sm">${so(v.font_kb)} KB</td></tr>`).join('')}</table></div>
      <div class="xs mut2" style="margin-top:8px">Chrome giả lập điện thoại tầm trung (CPU chậm 4×, 4G chậm), trung vị 3 lần. Xanh: tốt theo Core Web Vitals; đỏ: kém.</div></div>
    <div class="card"><h2>LCP bài viết theo ngày (giây)</h2>${bieuDoDuong([{ten: 'Bài viết', mau: '#f59e0b', diem: xu.map(r => [new Date(r.luc).getTime(), r.toc_do.bai_viet.lcp / 1000])},
      {ten: 'Trang chủ', mau: '#7c5cff', diem: xu.filter(r => r.toc_do.trang_chu).map(r => [new Date(r.luc).getTime(), r.toc_do.trang_chu.lcp / 1000])}], {cao: 170})}</div></div>`;
}

function chiTiet(bc) {
  const k = bc.kiem_tra, ln = k.link_nguon || {}, sm = k.sitemap || {}, rb = k.robots || {};
  const dong = (t, v) => `<tr><td class="sm">${t}</td><td class="n sm">${v}</td></tr>`;
  return `<div class="grid g2"><div class="card"><h2>Liên kết và sitemap</h2><table>
      ${dong('Link nguồn trích dẫn đã kiểm', `${so(ln.tong)} link của ${so(k.so_bai_kiem)} bài mới nhất`)}
      ${dong('Gãy thật (404, 410, tên miền không tồn tại)', so(ln.hong))}${dong('Báo phản hồi chậm, chưa kiểm được', so(ln.chua_kiem_duoc || 0))}
      ${dong('Sitemap', `${so(sm.so_url)} URL trong ${so(sm.so_file)} file`)}${dong('robots.txt chặn bot tìm kiếm', (rb.chan_bot_tim_kiem || []).join(', ') || 'không')}
      ${dong('Ghi rõ bot AI trong robots.txt', (rb.ghi_ro_bot_ai || []).join(', ') || 'chưa')}</table>
      ${(ln.mau_hong || []).length ? `<div class="xs mut2" style="margin-top:8px">Link gãy: ${ln.mau_hong.map(([u, s]) => `${esc(s)} ${esc(u.slice(0, 70))}`).join(' · ')}</div>` : ''}</div>
    <div class="card"><h2>Bot AI nhìn thấy gì (HTML gốc)</h2><table>
      ${Object.entries(k.trang || {}).map(([t, v]) => dong(esc(t), `${v.status ?? esc(v.loi || '')} · ${so(v.so_ky_tu || 0)} ký tự · H1 ${(v.h1 || []).length} · ${v.so_link ?? 0} link`)).join('')}</table>
      <div class="xs mut2" style="margin-top:8px">Đọc trang như bot không chạy JavaScript (OAI-SearchBot, PerplexityBot): số ký tự chữ, số H1, số link thấy được.</div></div></div>`;
}

async function main() {
  const khung = $('#app');
  const r = await fetch('bao_cao.enc', {cache: 'no-store'});
  if (!r.ok) { khung.innerHTML = '<div class="card empty">Chưa có lượt kiểm nào.</div>'; return; }
  const {du_lieu: bc} = await congMatKhau('bao_cao.enc', khung, 'Sức khoẻ SEO wealbee.com');
  khung.innerHTML = `${dau(bc)}<div class="grid" style="margin-top:16px">${canhBao(bc)}${bang(bc)}${tocDo(bc)}${chiTiet(bc)}
    <div class="card sm mut"><h2>Lịch chạy</h2><ul style="margin:0;padding-left:18px;display:grid;gap:6px">
      <li>Mỗi ngày 08:15 (giờ Việt Nam): toàn bộ phép kiểm, gồm đo tốc độ, kiểm link nguồn của 30 bài mới nhất, sitemap, robots, bảo mật.</li>
      <li>Cảnh báo khi một chỉ số chuyển sang Lỗi, chuyển từ Đạt sang Cảnh báo, hoặc điểm tụt từ 5 trở lên: mở hoặc bình luận issue "Cảnh báo sức khoẻ SEO" trên GitHub (GitHub gửi email cho chủ repo).</li>
      <li>Chạy tay bất cứ lúc nào: GitHub → Actions → "Suc khoe SEO" → Run workflow, hoặc <code>python -m wb_seo.chay</code> trên máy.</li></ul></div></div>`;
}
main();
