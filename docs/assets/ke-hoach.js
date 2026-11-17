// Trang tài liệu SEO nội bộ (kế hoạch, hướng dẫn sửa): markdown mã hoá bằng mật khẩu nội bộ, dựng bằng wb_seo/ke_hoach.py.
// Tệp gói và tên cổng lấy từ <body data-goi data-ten> (mặc định: kế hoạch SEO).
// Bộ dựng markdown gọn: tiêu đề, đoạn, **đậm**, *nghiêng*, `mã`, link, ảnh (anh:<khoá> trong gói), danh sách lồng 1 cấp, bảng, khối mã.
const NHAN_MUC = {'Nghiêm trọng': 'md-nghiem', 'Cao': 'md-cao', 'Trung bình': 'md-tb', 'Thấp': 'md-thap',
  'Chưa làm': 'md-chua', 'Đang làm': 'md-dang', 'Xong': 'md-xong'};

function dong(t) {                                     // định dạng trong dòng (đã escape trước); không đụng vào phần `mã`
  return t.split(/(`[^`]+`)/).map((s, i) => i % 2 ? `<code>${s.slice(1, -1)}</code>` : s
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?![*\w])/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')).join('');
}

function dung(md, anh) {
  const L = md.replace(/\r/g, '').split('\n'), out = [];
  let i = 0, doan = [];
  const xongDoan = () => { if (doan.length) { out.push(`<p>${dong(esc(doan.join(' ')))}</p>`); doan = []; } };
  while (i < L.length) {
    const l = L[i], t = l.trim();
    if (t.startsWith('```')) {                       // khối mã
      xongDoan(); const ma = []; i++;
      while (i < L.length && !L[i].trim().startsWith('```')) ma.push(L[i++]);
      out.push(`<pre>${esc(ma.join('\n'))}</pre>`); i++; continue;
    }
    let m;
    if ((m = t.match(/^(#{1,4})\s+(.*)$/))) { xongDoan(); const n = Math.max(2, m[1].length); out.push(`<h${n}>${dong(esc(m[2]))}</h${n}>`); i++; continue; }
    if ((m = t.match(/^!\[([^\]]*)\]\(anh:([\w-]+)\)$/))) {
      xongDoan(); if (anh[m[2]]) out.push(`<figure><img src="${anh[m[2]]}" alt="${esc(m[1])}"><figcaption>${esc(m[1])}</figcaption></figure>`); i++; continue;
    }
    if (/^\|.*\|$/.test(t) && /^\|[\s:|-]+\|$/.test((L[i + 1] || '').trim())) {   // bảng
      xongDoan();
      const o = s => s.trim().replace(/^\||\|$/g, '').split('|').map(x => x.trim());
      const dau = o(t); i += 2; const hang = [];
      while (i < L.length && /^\|.*\|$/.test(L[i].trim())) hang.push(o(L[i++]));
      const o_ = x => NHAN_MUC[x] ? `<span class="tag ${NHAN_MUC[x]}">${esc(x)}</span>` : dong(esc(x));
      out.push(`<div class="bang"><table><tr>${dau.map(x => `<th>${dong(esc(x))}</th>`).join('')}</tr>${hang.map(h => `<tr>${h.map(x => `<td>${o_(x)}</td>`).join('')}</tr>`).join('')}</table></div>`);
      continue;
    }
    if ((m = l.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/))) {   // danh sách (lồng theo thụt lề)
      xongDoan(); const goc = m[2].endsWith('.') ? 'ol' : 'ul'; let html = `<${goc}>`, mo = false;
      while (i < L.length && (m = L[i].match(/^(\s*)([-*]|\d+\.)\s+(.*)$/))) {
        if (m[1].length >= 2) {
          if (!mo) { html = html.replace(/<\/li>$/, ''); html += `<${m[2].endsWith('.') ? 'ol' : 'ul'}>`; mo = m[2].endsWith('.') ? 'ol' : 'ul'; }
          html += `<li>${dong(esc(m[3]))}</li>`;
        } else {
          if (mo) { html += `</${mo}></li>`; mo = false; }
          html += `<li>${dong(esc(m[3]))}</li>`;
        }
        i++;
      }
      if (mo) html += `</${mo}></li>`;
      out.push(html + `</${goc}>`); continue;
    }
    if (!t) { xongDoan(); i++; continue; }
    doan.push(t); i++;
  }
  xongDoan();
  return out.join('\n');
}

async function main() {
  const khung = $('#app'), goi = document.body.dataset.goi || 'ke_hoach.enc';
  const r = await fetch(goi, {cache: 'no-store'});
  if (!r.ok) { khung.innerHTML = '<div class="card empty">Chưa có bản tài liệu.</div>'; return; }
  const {du_lieu: kh} = await congMatKhau(goi, khung, document.body.dataset.ten || 'Kế hoạch SEO Wealbee');
  khung.innerHTML = `<section class="hero"><span class="pill">Cập nhật ${tg(kh.luc)}</span><h1 style="margin-top:12px">${esc(kh.tieu_de)}</h1>
    <p class="mut">${esc(kh.mo_ta || 'Lỗi kỹ thuật và cách sửa, cụm chủ đề từ khoá, tối ưu cho công cụ tìm kiếm AI, bộ chỉ số theo dõi và lộ trình triển khai.')}</p></section>
    <article class="card kh">${dung(kh.md, kh.anh || {})}</article>`;
}
main();
