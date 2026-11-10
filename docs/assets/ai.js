// Trợ lý AI phân tích đầu tư: Gemini API (gói miễn phí của Google) + dữ liệu Wealbee (BCTC, tin) + giá cổ phiếu.
// Chạy hẳn trên trình duyệt, không cần máy chủ: Gemini gọi "công cụ", trang tự đọc dữ liệu rồi trả kết quả cho Gemini.
// - BCTC: data/ma/<MÃ>.json của web đang xem (Wealbee Data API, đồng bộ mỗi giờ; bản Free được giải mã bằng mật khẩu nhóm)
// - Tin: ../tin/ (API tin của app Wealbee, xuất mỗi giờ); web Free thêm Vietstock
// - Giá: Vietstock (web Free) / VNDirect dchart (công khai, gọi thẳng)
// Khoá Gemini: khoá nhóm ../ai/khoa.json (mã hoá bằng mật khẩu nội bộ, tạo bằng `python -m wb_api.khoa_ai`)
// hoặc khoá riêng người dùng dán vào (chỉ lưu trong trình duyệt của họ).
(() => {
  const API = 'https://generativelanguage.googleapis.com/v1beta';
  const kho = s => ({
    get: k => { try { return s().getItem(k); } catch { return null; } },
    set: (k, v) => { try { v == null ? s().removeItem(k) : s().setItem(k, v); } catch {} }});
  const LS = kho(() => localStorage), SS = kho(() => sessionStorage);
  const A = {khoa: null, nguonKhoa: '', goiNhom: undefined, models: null, model: null, nghi: {}, ls: [], dang: false, huy: null};
  class LoiKhoa extends Error {}

  // ---------------- khoá + model ----------------
  async function goiNhom() {
    if (A.goiNhom === undefined) A.goiNhom = await taiJson('../ai/khoa.json');
    return A.goiNhom;
  }
  async function layKhoa() {
    if (A.khoa) return A.khoa;
    const rieng = LS.get('ai_khoa_rieng');
    if (rieng) { A.khoa = rieng; A.nguonKhoa = 'khoá riêng của bạn'; return rieng; }
    const g = await goiNhom();
    if (g) for (const mk of [D.mk, SS.get('mk_noi_bo')].filter(Boolean)) {
      try { A.khoa = (await moGoi(g, mk)).khoa; A.nguonKhoa = 'khoá nhóm'; return A.khoa; } catch {}
    }
    return null;
  }
  const ver = n => parseFloat((n.match(/^gemini-(\d+(?:\.\d+)?)/) || [])[1] || 0);
  function xepModel(ten) {                        // ưu tiên Flash (nhanh, có lượt miễn phí), dự phòng Flash-Lite
    const theo = re => ten.filter(n => re.test(n)).sort((a, b) => ver(b) - ver(a));
    const ds = [LS.get('ai_model')];
    if (ten.includes('gemini-flash-latest')) ds.push('gemini-flash-latest');
    ds.push(...theo(/^gemini-\d+(\.\d+)?-flash$/).slice(0, 2));
    if (ten.includes('gemini-flash-lite-latest')) ds.push('gemini-flash-lite-latest');
    ds.push(...theo(/^gemini-\d+(\.\d+)?-flash-lite$/).slice(0, 1));
    if (!ten.length) ds.push('gemini-flash-latest', 'gemini-flash-lite-latest', 'gemini-2.5-flash');
    return [...new Set(ds.filter(Boolean))];
  }
  async function dsModel(lamMoi) {
    if (A.models && !lamMoi) return A.models;
    let ten = [];
    try {
      const r = await fetch(`${API}/models?pageSize=1000`, {headers: {'x-goog-api-key': A.khoa}});
      const j = await r.json().catch(() => ({}));
      if (!r.ok && [400, 401, 403].includes(r.status)) throw new LoiKhoa(j.error?.message || 'HTTP ' + r.status);
      ten = (j.models || []).filter(m => (m.supportedGenerationMethods || []).includes('generateContent'))
        .map(m => m.name.replace(/^models\//, '')).filter(n => /^gemini-/.test(n) && !/image|tts|audio|live|embedding|robotics|computer/.test(n));
    } catch (e) { if (e instanceof LoiKhoa) throw e; }
    A.tatCa = ten;
    return A.models = xepModel(ten);
  }

  // ---------------- gọi Gemini (stream SSE) ----------------
  function themPhan(parts, p) {
    const cuoi = parts[parts.length - 1];
    const laChu = q => q && q.text != null && !q.functionCall && !q.thought;
    if (laChu(p) && laChu(cuoi)) {                // gộp các mẩu chữ của stream; giữ chữ ký suy nghĩ (thoughtSignature) nếu có
      cuoi.text += p.text;
      if (p.thoughtSignature) cuoi.thoughtSignature = p.thoughtSignature;
    } else parts.push({...p});
  }
  async function goiGemini(body, khiCoChu) {
    let loi = null;
    const ds = (await dsModel()).filter(m => !(A.nghi[m] > Date.now()));
    for (const m of ds.length ? ds : A.models) {
      let r;
      try {
        r = await fetch(`${API}/models/${m}:streamGenerateContent?alt=sse`, {method: 'POST', signal: A.huy?.signal,
          headers: {'content-type': 'application/json', 'x-goog-api-key': A.khoa}, body: JSON.stringify(body)});
      } catch (e) { if (e.name === 'AbortError') throw e; loi = {msg: 'Không kết nối được Gemini (mạng)'}; continue; }
      if (!r.ok) {
        const j = await r.json().catch(() => ({})), msg = j.error?.message || 'HTTP ' + r.status;
        if ([400, 401, 403].includes(r.status) && /api.?key|permission|referer|blocked|denied/i.test(msg)) throw new LoiKhoa(msg);
        if ([404, 429, 500, 503].includes(r.status)) {
          const lauDai = r.status === 404 || /limit: 0\b|per ?day|PerDay/i.test(msg);   // model không có ở gói miễn phí / hết lượt ngày
          A.nghi[m] = Date.now() + (lauDai ? 6 * 36e5 : 60e3);
          loi = {status: r.status, msg}; continue;
        }
        throw new Error(msg);
      }
      A.model = m; veDau();
      const parts = [], rd = r.body.getReader(), dec = new TextDecoder();
      let buf = '', ket = null, dung = null;
      const doc = ln => {
        ln = ln.trim(); if (!ln.startsWith('data:')) return;
        let c; try { c = JSON.parse(ln.slice(5)); } catch { return; }
        const cd = c.candidates?.[0];
        for (const p of cd?.content?.parts || []) themPhan(parts, p);
        if (cd?.finishReason) ket = cd.finishReason;
        if (c.promptFeedback?.blockReason) ket = 'BLOCKED';
        if (c.usageMetadata) dung = c.usageMetadata;
        const chu = parts.filter(p => p.text != null && !p.thought && !p.functionCall).map(p => p.text).join('');
        if (chu) khiCoChu(chu);
      };
      for (;;) {
        const {done, value} = await rd.read();
        if (done) break;
        buf += dec.decode(value, {stream: true});
        let i; while ((i = buf.indexOf('\n')) >= 0) { doc(buf.slice(0, i)); buf = buf.slice(i + 1); }
      }
      doc(buf);
      return {parts, ket, dung};
    }
    const e = new Error(loi?.status === 429 ? 'HET_LUOT' : loi?.msg || 'Không gọi được Gemini');
    e.chiTiet = loi?.msg; throw e;
  }

  // ---------------- công cụ: đọc dữ liệu Wealbee ----------------
  const tyD = x => x == null ? null : Math.round(x / 1e8) / 10;                       // đồng -> tỷ đồng, 1 số lẻ
  const tile = (a, b) => a == null || b == null || !b ? null : Math.round(a / b * 1000) / 10;
  const tang = (a, b) => a == null || b == null || !b ? null : Math.round((a - b) / Math.abs(b) * 1000) / 10;
  const gon = o => {                                                                   // bỏ trường rỗng cho đỡ tốn token
    if (Array.isArray(o)) return o.map(gon);
    if (o && typeof o === 'object') {
      const r = {};
      for (const [k, v] of Object.entries(o)) { const g = gon(v);
        if (g != null && !(typeof g === 'object' && !Array.isArray(g) && !Object.keys(g).length) && !(Array.isArray(g) && !g.length)) r[k] = g; }
      return r;
    }
    return o;
  };
  const SAN = () => D.cty;
  const tenCty = m => SAN()[m]?.short_name || SAN()[m]?.name || '';
  const ngayVN = s => { const d = new Date(s); return isNaN(d) ? s : d.toLocaleString('vi-VN', {hour12: false, timeZone: 'Asia/Ho_Chi_Minh',
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'}); };
  const chuanMa = m => String(m || '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '');

  function timCty(tu) {
    const q = khoBo(String(tu || '').trim()), Q = chuanMa(tu);
    if (!q) return [];
    const ds = Object.values(SAN()).filter(c => c.ticker === Q || khoBo(`${c.ticker} ${c.name} ${c.short_name || ''}`).includes(q));
    ds.sort((a, b) => (b.ticker === Q) - (a.ticker === Q) || !!D.idx.cong_ty[b.ticker] - !!D.idx.cong_ty[a.ticker]);
    return ds.slice(0, 8).map(c => ({ma: c.ticker, ten: c.name, san: c.exchange, nganh: NGANH[c.industry_type] || c.industry_type,
      co_bctc: !!D.idx.cong_ty[c.ticker], ky_moi_nhat: D.idx.cong_ty[c.ticker]?.ky}));
  }

  function chiTieu(bang) {
    const o = {};
    for (const [k, v] of Object.entries(bang || {})) {
      if (v == null || typeof v !== 'object') { if (typeof v === 'number') o[nhanKhoa(k)] = k === 'eps' ? v : tyD(v); continue; }
      o[nhanKhoa(k)] = {quy: tyD(v.quarter), quy_cung_ky: tyD(v.quarter_prior_year), luy_ke: tyD(v.ytd), luy_ke_cung_ky: tyD(v.ytd_prior_year),
        cuoi_ky: tyD(v.end_of_period), dau_nam: tyD(v.start_of_year)};
    }
    return o;
  }
  function tyLe(st) {
    const i = st.income_statement || {}, b = st.balance_sheet || {}, c = st.cash_flow || {};
    const dt = i.revenue || {}, ln = i.net_profit || {}, lg = i.gross_profit || {};
    const vc = b.equity || b.owners_equity || {}, ts = b.total_assets || {}, no = b.total_liabilities || {}, vay = b.borrowings || {};
    const cfo = c.operating || c.operating_cash_flow || {}, nam = 12 / (st.months_ytd || 12);
    const tb = x => x.end_of_period == null ? null : x.start_of_year == null ? x.end_of_period : (x.end_of_period + x.start_of_year) / 2;
    return {
      bien_ln_gop_quy_pct: tile(lg.quarter, dt.quarter), bien_ln_gop_quy_cung_ky_pct: tile(lg.quarter_prior_year, dt.quarter_prior_year),
      bien_lnst_quy_pct: tile(ln.quarter, dt.quarter), bien_lnst_quy_cung_ky_pct: tile(ln.quarter_prior_year, dt.quarter_prior_year),
      tang_dt_quy_so_cung_ky_pct: tang(dt.quarter, dt.quarter_prior_year), tang_lnst_quy_so_cung_ky_pct: tang(ln.quarter, ln.quarter_prior_year),
      tang_dt_luy_ke_so_cung_ky_pct: tang(dt.ytd, dt.ytd_prior_year), tang_lnst_luy_ke_so_cung_ky_pct: tang(ln.ytd, ln.ytd_prior_year),
      roe_nam_hoa_pct: ln.ytd == null ? null : tile(ln.ytd * nam, tb(vc)), roa_nam_hoa_pct: ln.ytd == null ? null : tile(ln.ytd * nam, tb(ts)),
      no_phai_tra_tren_vcsh_lan: tile(no.end_of_period, vc.end_of_period) == null ? null : tile(no.end_of_period, vc.end_of_period) / 100,
      vay_tren_vcsh_lan: tile(vay.end_of_period, vc.end_of_period) == null ? null : tile(vay.end_of_period, vc.end_of_period) / 100,
      lctt_kinh_doanh_tren_lnst_luy_ke_lan: tile(cfo.ytd, ln.ytd) == null ? null : tile(cfo.ytd, ln.ytd) / 100,
    };
  }
  async function bctc({ma}) {
    const m = chuanMa(ma);
    if (!D.idx.cong_ty[m]) return {loi: `Web chưa có BCTC của mã ${m || ma}.`, goi_y: timCty(ma).slice(0, 5)};
    if (!D.ma[m]) D.ma[m] = await tai(`ma/${m}`);
    const du = D.ma[m]; if (!du) return {loi: `Không tải được BCTC ${m}.`};
    const kys = Object.keys(du.ky).sort().reverse().slice(0, 4), c = SAN()[m] || {};
    return gon({ma: m, ten: c.name, san: c.exchange, don_vi: 'tỷ đồng (tỷ lệ tính sẵn theo %, hoặc "lần")',
      nguon: `Wealbee Data API (gói ${CH.goi === 'dn' ? 'Doanh nghiệp' : 'Free'})`,
      cac_ky: kys.map(k => { const st = du.ky[k], hs = st.health_score;
        return {ky: st.period_label || k, trang_thai: st.status === 'verified' ? 'đã kiểm chứng' : st.status === 'needs_review' ? 'cần soát lại' : st.status,
          pham_vi: st.scope === 'consolidated' ? 'hợp nhất' : st.scope === 'single_entity' ? 'riêng' : st.scope,
          loai_hinh: NGANH[st.industry_type] || st.industry_type, so_thang_luy_ke: st.months_ytd,
          diem_suc_khoe_tai_chinh: hs && hs.value != null ? `${hs.value}/${hs.max || 10}` : null,
          ly_do_can_soat: st.review_reasons, phep_kiem_dat: st.kiem ? `${st.kiem.dat}/${st.kiem.tong}` : null,
          ket_qua_kinh_doanh: chiTieu(st.income_statement), can_doi_ke_toan: chiTieu(st.balance_sheet),
          luu_chuyen_tien_te: chiTieu(st.cash_flow), ty_le_tinh_san: tyLe(st), file_goc: st.nguon_goc?.document_url}; })});
  }

  const NGUON_TIN_AI = () => [['Wealbee', '../tin/moi.json', m => `../tin/ma/${m}.json`]]
    .concat(CH.vietstock ? [['Vietstock', '../vietstock/tin_moi.json', m => `../vietstock/tin_ma/${m}.json`]] : []);
  async function tinTuc({ma, tu_khoa, so_tin}) {
    const m = chuanMa(ma), n = Math.min(30, Math.max(1, +so_tin || 12)), q = khoBo(tu_khoa || '');
    let ds = [];
    for (const [ten, chung, theoMa] of NGUON_TIN_AI()) {
      const j = await taiJson(m ? theoMa(m) : chung);
      for (const x of j?.ds || []) ds.push({...x, _n: ten});
    }
    if (q) ds = ds.filter(x => khoBo(`${x.tieu_de} ${x.tom_tat}`).includes(q));
    ds.sort((a, b) => (b.luc || '').localeCompare(a.luc || ''));
    return gon({pham_vi: m ? `tin nhắc tới ${m} trong khoảng 30 ngày` : 'tin mới nhất toàn thị trường', so_tin: Math.min(n, ds.length),
      ds: ds.slice(0, n).map(x => ({luc: ngayVN(x.luc), nguon: x._n, loai: x.loai || (x.muc || []).join(', '),
        tieu_de: String(x.tieu_de || '').replace(/\*\*/g, ''), tom_tat: String(x.tom_tat || '').replace(/\*\*/g, ''),
        sac_thai: {positive: 'tích cực', negative: 'tiêu cực', neutral: 'trung lập'}[x.sac_thai] || x.sac_thai,
        ma_lien_quan: (x.ma || []).slice(0, 8), link: x.link}))});
  }

  async function giaCp({ma}) {
    const m = chuanMa(ma);
    if (!m) return {loi: 'Thiếu mã'};
    const to = Math.floor(Date.now() / 1000), fr = to - 400 * 86400;
    let j = CH.vietstock ? await taiJson(`../vietstock/gia/${m}.json`) : null, nguon = 'Vietstock';
    if (!j?.t?.length) {
      nguon = 'VNDirect';
      j = await fetch(`https://dchart-api.vndirect.com.vn/dchart/history?resolution=D&symbol=${m}&from=${fr}&to=${to}`).then(r => r.json()).catch(() => null);
    }
    if (!j?.t?.length) return {loi: `Không lấy được giá ${m}.`};
    const k = Math.max(...j.c) < 1000 ? 1000 : 1, c = j.c.map(v => Math.round(v * k)), t = j.t, n = c.length, cuoi = c[n - 1];
    const lui = s => { const i = n - 1 - s; return i >= 0 ? tang(cuoi, c[i]) : null; };
    const nam = c.slice(-250), kl = (j.v || []).slice(-20);
    const thang = {};
    t.forEach((x, i) => { const d = new Date(x * 1000); thang[`${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`] = c[i]; });
    return gon({ma: m, nguon: `${nguon} (API công khai miễn phí)`, don_vi: 'đồng/cổ phiếu',
      phien_cuoi: new Date(t[n - 1] * 1000).toLocaleDateString('vi-VN'), gia_dong_cua: cuoi,
      thay_doi_pct: {'1_tuan': lui(5), '1_thang': lui(21), '3_thang': lui(63), '6_thang': lui(126), '12_thang': lui(250)},
      cao_nhat_52_tuan: Math.max(...nam), thap_nhat_52_tuan: Math.min(...nam), cach_dinh_52_tuan_pct: tang(cuoi, Math.max(...nam)),
      kl_trung_binh_20_phien: kl.length ? Math.round(kl.reduce((a, b) => a + b, 0) / kl.length) : null,
      gia_cuoi_moi_thang: Object.entries(thang).slice(-13).map(([th, g]) => `${th}: ${g}`)});
  }

  function locCp({nganh, san, sap_xep = 'diem_suc_khoe', thu_tu = 'giam', so_luong = 10, chi_lai = false, diem_toi_thieu}) {
    const n = Math.min(40, Math.max(1, +so_luong || 10)), S = String(san || '').toUpperCase();
    let ds = Object.entries(D.idx.cong_ty).map(([m, v]) => ({ma: m, ten: tenCty(m), san: SAN()[m]?.exchange, nganh: v.nganh, ky: v.ky,
      trang_thai: v.tt, doanh_thu_quy_ty: tyD(v.dt), lnst_quy_ty: tyD(v.ln), bien_lnst_pct: tile(v.ln, v.dt), diem: v.diem}));
    if (nganh) ds = ds.filter(x => x.nganh === nganh);
    if (S) ds = ds.filter(x => x.san === S);
    if (chi_lai) ds = ds.filter(x => x.lnst_quy_ty > 0);
    if (diem_toi_thieu != null) ds = ds.filter(x => x.diem != null && x.diem >= +diem_toi_thieu);
    const f = {diem_suc_khoe: 'diem', doanh_thu: 'doanh_thu_quy_ty', loi_nhuan: 'lnst_quy_ty', bien_loi_nhuan: 'bien_lnst_pct'}[sap_xep] || 'diem';
    ds = ds.filter(x => x[f] != null).sort((a, b) => (thu_tu === 'tang' ? 1 : -1) * (a[f] - b[f]));
    return gon({ghi_chu: 'Số liệu quý gần nhất của từng mã, tỷ đồng; điểm sức khoẻ tài chính /10 (chỉ gói Doanh nghiệp có điểm).',
      tong_so_ma_khop: ds.length, ds: ds.slice(0, n).map(x => ({...x, nganh: NGANH[x.nganh] || x.nganh}))});
  }

  const CONG_CU = [
    {name: 'tim_cong_ty', description: 'Tìm mã cổ phiếu theo tên hoặc một phần tên công ty (gõ không dấu được). Dùng khi người dùng nói tên công ty mà không nói mã.',
      parameters: {type: 'object', properties: {tu_khoa: {type: 'string', description: 'Tên công ty hoặc mã, ví dụ "vinamilk", "hoa phat", "FPT"'}}, required: ['tu_khoa']}},
    {name: 'bao_cao_tai_chinh', description: 'Lấy BCTC (Wealbee Data API) của một mã: các quý gần nhất, kết quả kinh doanh (quý + luỹ kế, kèm cùng kỳ năm trước), cân đối kế toán (cuối kỳ, đầu năm), lưu chuyển tiền tệ (luỹ kế), điểm sức khoẻ tài chính, trạng thái kiểm chứng và các tỷ lệ tính sẵn (biên lợi nhuận, tăng trưởng, ROE/ROA năm hoá, nợ/VCSH, vay/VCSH, LCTT kinh doanh/LNST).',
      parameters: {type: 'object', properties: {ma: {type: 'string', description: 'Mã cổ phiếu, ví dụ FPT'}}, required: ['ma']}},
    {name: 'tin_tuc', description: 'Lấy tin tức thị trường / doanh nghiệp từ Wealbee (có tóm tắt, sắc thái tích cực/tiêu cực, mã liên quan, link). Bỏ trống "ma" để lấy tin mới nhất toàn thị trường.',
      parameters: {type: 'object', properties: {ma: {type: 'string', description: 'Mã cổ phiếu (tuỳ chọn)'},
        tu_khoa: {type: 'string', description: 'Lọc theo từ khoá trong tiêu đề/tóm tắt (tuỳ chọn)'}, so_tin: {type: 'integer', description: 'Số tin, mặc định 12, tối đa 30'}}}},
    {name: 'gia_co_phieu', description: 'Lấy giá đóng cửa gần nhất và biến động 1 tuần/1/3/6/12 tháng, đỉnh/đáy 52 tuần, khối lượng trung bình 20 phiên, giá cuối mỗi tháng.',
      parameters: {type: 'object', properties: {ma: {type: 'string'}}, required: ['ma']}},
    {name: 'loc_co_phieu', description: 'Lọc và xếp hạng các mã có BCTC trên web theo số liệu quý gần nhất (điểm sức khoẻ tài chính, doanh thu, LNST, biên LNST). Dùng cho câu hỏi kiểu "top", "mã nào tốt nhất ngành", "lọc cổ phiếu".',
      parameters: {type: 'object', properties: {
        nganh: {type: 'string', enum: ['corporate', 'bank', 'securities', 'insurance'], description: 'corporate = doanh nghiệp thường, bank = ngân hàng, securities = chứng khoán, insurance = bảo hiểm'},
        san: {type: 'string', enum: ['HOSE', 'HNX', 'UPCOM']},
        sap_xep: {type: 'string', enum: ['diem_suc_khoe', 'doanh_thu', 'loi_nhuan', 'bien_loi_nhuan']},
        thu_tu: {type: 'string', enum: ['giam', 'tang']}, so_luong: {type: 'integer', description: 'mặc định 10, tối đa 40'},
        chi_lai: {type: 'boolean', description: 'chỉ lấy mã có LNST quý > 0'}, diem_toi_thieu: {type: 'number'}}}},
  ];
  const CHAY = {tim_cong_ty: a => ({ket_qua: timCty(a.tu_khoa)}), bao_cao_tai_chinh: bctc, tin_tuc: tinTuc, gia_co_phieu: giaCp, loc_co_phieu: locCp};
  const MO_TA = {tim_cong_ty: a => `Tìm “${a.tu_khoa}”`, bao_cao_tai_chinh: a => `Đọc BCTC ${chuanMa(a.ma)}`,
    tin_tuc: a => a.ma ? `Đọc tin ${chuanMa(a.ma)}` : 'Đọc tin thị trường', gia_co_phieu: a => `Lấy giá ${chuanMa(a.ma)}`, loc_co_phieu: () => 'Lọc cổ phiếu'};

  function heThong() {
    const homNay = new Date().toLocaleDateString('vi-VN', {weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Asia/Ho_Chi_Minh'});
    return `Bạn là trợ lý phân tích đầu tư chứng khoán Việt Nam, gắn trên web tra cứu BCTC dùng dữ liệu Wealbee. Hôm nay là ${homNay}.
Dữ liệu: BCTC của ${so(Object.keys(D.idx.cong_ty).length)} mã (Wealbee Data API, gói ${CH.goi === 'dn' ? 'Doanh nghiệp, có điểm sức khoẻ tài chính /10' : 'Free, không có điểm sức khoẻ'}, cập nhật ${tg(D.idx.cap_nhat)}); tin tức Wealbee${CH.vietstock ? ' + Vietstock' : ''}; giá cổ phiếu ${CH.vietstock ? 'Vietstock/VNDirect' : 'VNDirect'}.${D.chon ? `\nNgười dùng đang xem mã ${D.chon} trên web; câu hỏi không nói mã thì hiểu là hỏi về ${D.chon}.` : ''}

Cách làm:
- Luôn gọi công cụ để lấy số liệu trước khi nhận xét. Tuyệt đối không bịa số; công cụ không có thì nói rõ là chưa có dữ liệu. Không dùng kiến thức cũ của bạn về số liệu doanh nghiệp.
- Trong BCTC: "quy" = giá trị quý, "quy_cung_ky" = cùng quý năm trước, "luy_ke" = luỹ kế từ đầu năm, "cuoi_ky"/"dau_nam" = số dư cân đối. Đơn vị tỷ đồng. Dùng luôn "ty_le_tinh_san", không tự tính lại.
- Luôn ghi kỳ báo cáo (VD Q3/2026) cạnh con số. Kỳ có trạng thái "cần soát lại" thì nhắc người dùng thận trọng.
- Phân tích một mã: (1) Kết luận nhanh 2-3 câu; (2) Kết quả kinh doanh và tăng trưởng; (3) Biên lợi nhuận, hiệu quả (ROE/ROA); (4) Sức khoẻ tài chính: nợ, vay, dòng tiền; (5) Tin tức đáng chú ý và tác động; (6) Giá và vị thế giá; (7) Rủi ro / điều cần theo dõi. Khi cần đủ bức tranh thì gọi cả bao_cao_tai_chinh, tin_tuc, gia_co_phieu (gọi song song được).
- So sánh nhiều mã: dùng bảng markdown.
- Dẫn link tin khi nhắc tới tin, dạng [tiêu đề ngắn](link).
- Có thể nêu nhận định tham khảo kèm lý do, nhưng không khẳng định chắc chắn nên mua/bán. Kết thúc bằng 1 dòng nghiêng ngắn: thông tin tham khảo, không phải khuyến nghị đầu tư.
- Trả lời bằng tiếng Việt, súc tích, markdown (tiêu đề ###, gạch đầu dòng, **in đậm** số quan trọng).`;
  }

  // ---------------- vòng hội thoại ----------------
  async function hoi(cau) {
    cau = String(cau || '').trim();
    if (!cau || A.dang) return;
    if (!await layKhoa()) return veCaiDat();
    A.dang = true; A.huy = new AbortController(); veNut();
    $('#ai-goi-y')?.remove();
    themTin('u', esc(cau));
    const o = themTin('a', '<div class="ai-buoc"></div><div class="ai-chu"><span class="ai-nhay">Đang suy nghĩ…</span></div>');
    const buoc = $('.ai-buoc', o), chuEl = $('.ai-chu', o);
    const moc = A.ls.length;
    A.ls.push({role: 'user', parts: [{text: cau}]});
    let truoc = '', xong = false;
    try {
      for (let vong = 0; vong < 8 && !xong; vong++) {
        const kq = await goiGemini({systemInstruction: {parts: [{text: heThong()}]}, contents: A.ls, tools: [{functionDeclarations: CONG_CU}]},
          chu => { chuEl.innerHTML = md(truoc + chu) + '<span class="ai-nhay">▍</span>'; cuon(); });
        A.ls.push({role: 'model', parts: kq.parts.length ? kq.parts : [{text: ''}]});
        const chuVong = kq.parts.filter(p => p.text != null && !p.thought && !p.functionCall).map(p => p.text).join('');
        if (chuVong.trim()) truoc += chuVong + '\n\n';
        const goi = kq.parts.filter(p => p.functionCall);
        if (!goi.length) {
          xong = true;
          let ghi = '';
          if (kq.ket === 'MAX_TOKENS') ghi = '\n\n_(Câu trả lời bị cắt vì quá dài. Hỏi “viết tiếp” để xem phần còn lại.)_';
          else if (kq.ket && !['STOP', 'FINISH_REASON_UNSPECIFIED'].includes(kq.ket) && !truoc.trim()) ghi = `_(Gemini không trả lời câu này: ${kq.ket})_`;
          chuEl.innerHTML = md(truoc.trim() + ghi) || '<span class="mut">(không có nội dung)</span>';
          break;
        }
        chuEl.innerHTML = truoc ? md(truoc) : '<span class="ai-nhay">Đang lấy dữ liệu…</span>';
        const traLoi = await Promise.all(goi.map(async p => {
          const {name, args = {}, id} = p.functionCall;
          const dong = document.createElement('div');
          dong.textContent = '⏳ ' + (MO_TA[name]?.(args) || name); buoc.appendChild(dong); cuon();
          let res;
          try { res = CHAY[name] ? await CHAY[name](args) : {loi: 'Không có công cụ ' + name}; }
          catch (e) { res = {loi: 'Lỗi khi lấy dữ liệu: ' + (e.message || e)}; }
          if (Array.isArray(res) || typeof res !== 'object' || res == null) res = {ket_qua: res};
          dong.textContent = (res.loi ? '⚠️ ' : '✓ ') + (MO_TA[name]?.(args) || name) + (res.loi ? ` (${res.loi})` : '');
          const fr = {name, response: res}; if (id) fr.id = id;
          return {functionResponse: fr};
        }));
        A.ls.push({role: 'user', parts: traLoi});
      }
      if (!xong) chuEl.innerHTML = md(truoc + '\n\n_(Dừng sau 8 lượt lấy dữ liệu. Hỏi cụ thể hơn giúp em nhé.)_');
      o.insertAdjacentHTML('beforeend', `<div class="xs mut2 ai-cuoi">${esc(A.model || '')}</div>`);
    } catch (e) {
      A.ls.length = moc;                                         // bỏ lượt hỏng để lịch sử gửi lại luôn hợp lệ
      if (e.name === 'AbortError') chuEl.innerHTML = md(truoc) + '<div class="xs mut2">Đã dừng.</div>';
      else if (e instanceof LoiKhoa) {
        chuEl.innerHTML = `<div class="ai-loi">Khoá Gemini bị từ chối: ${esc(e.message.slice(0, 220))}</div>`;
        if (A.nguonKhoa === 'khoá riêng của bạn') LS.set('ai_khoa_rieng', null);
        A.khoa = null; A.models = null;
      } else if (e.message === 'HET_LUOT') chuEl.innerHTML = `<div class="ai-loi">Gemini bản miễn phí đã hết lượt (giới hạn mỗi phút và mỗi ngày của khoá).
        Đợi khoảng 1 phút rồi hỏi lại; nếu hết lượt ngày thì phải chờ Google đặt lại (khoảng 14-15h giờ Việt Nam).</div>`;
      else chuEl.innerHTML = `<div class="ai-loi">Lỗi: ${esc(String(e.message || e).slice(0, 300))}</div>`;
    } finally {
      A.dang = false; A.huy = null; veNut(); cuon();
      if (A.ls.length > 60) { let i = A.ls.length - 40; while (i < A.ls.length && !(A.ls[i].role === 'user' && A.ls[i].parts[0]?.text != null)) i++; A.ls.splice(0, i); }
    }
  }

  // ---------------- markdown gọn (đã escape trước, chỉ dựng thẻ an toàn) ----------------
  function md(s) {
    const inl = t => t.replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
      .replace(/(^|[\s(])[*_]([^*_\n]+)[*_](?=[\s).,:;!?]|$)/g, '$1<i>$2</i>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    const L = esc(s || '').split('\n');
    let o = '', ds = null, p = [];
    const dongP = () => { if (p.length) { o += `<p>${p.map(inl).join('<br>')}</p>`; p = []; } };
    const dongDs = () => { if (ds) { o += `</${ds}>`; ds = null; } };
    for (let i = 0; i < L.length; i++) {
      const l = L[i], t = l.trim();
      if (/^\|.*\|$/.test(t) && /^\|[\s:|-]+\|$/.test((L[i + 1] || '').trim())) {             // bảng
        dongP(); dongDs();
        const o_ = c => c.trim().replace(/^\||\|$/g, '').split('|').map(x => inl(x.trim()));
        o += `<div class="ai-bang"><table><tr>${o_(t).map(x => `<th>${x}</th>`).join('')}</tr>`;
        i += 2;
        while (i < L.length && /^\|.*\|$/.test(L[i].trim())) { o += `<tr>${o_(L[i]).map(x => `<td>${x}</td>`).join('')}</tr>`; i++; }
        o += '</table></div>'; i--; continue;
      }
      let m;
      if ((m = t.match(/^(#{1,4})\s+(.*)$/))) { dongP(); dongDs(); o += `<h4>${inl(m[2])}</h4>`; continue; }
      if ((m = t.match(/^[-*•]\s+(.*)$/)) || (m = t.match(/^\d+[.)]\s+(.*)$/))) {
        dongP(); const loai = /^\d/.test(t) ? 'ol' : 'ul';
        if (ds !== loai) { dongDs(); o += `<${loai}>`; ds = loai; }
        o += `<li>${inl(m[1])}</li>`; continue;
      }
      if (/^(-{3,}|\*{3,})$/.test(t)) { dongP(); dongDs(); o += '<hr>'; continue; }
      if (!t) { dongP(); dongDs(); continue; }
      dongDs(); p.push(t);
    }
    dongP(); dongDs();
    return o;
  }

  // ---------------- giao diện ----------------
  const GOI_Y = () => (D.chon ? [`Phân tích nhanh ${D.chon}`, `${D.chon} có tin gì đáng chú ý?`, `Dòng tiền và nợ vay của ${D.chon} thế nào?`] : [])
    .concat(['Tin thị trường hôm nay có gì đáng chú ý?', CH.goi === 'dn' ? 'Top 10 mã HOSE có điểm sức khoẻ tài chính cao nhất' : 'Top 10 mã HOSE lãi lớn nhất quý gần nhất',
      'So sánh FPT với CMG', 'Ngân hàng nào có lợi nhuận quý tăng mạnh nhất?']).slice(0, 5);
  function cuon() { const k = $('#ai-tn'); if (k) k.scrollTop = k.scrollHeight; }
  function themTin(ai, html) {
    const d = document.createElement('div'); d.className = 'ai-m ' + ai; d.innerHTML = html; $('#ai-tn').appendChild(d); cuon(); return d;
  }
  function veDau() { const e = $('#ai-model'); if (e) e.textContent = A.khoa ? `Gemini${A.model ? ' · ' + A.model : ''} · ${A.nguonKhoa}` : 'Gemini (miễn phí)'; }
  function veNut() {
    const b = $('#ai-gui'); if (!b) return;
    b.textContent = A.dang ? 'Dừng' : 'Gửi'; b.classList.toggle('sec', A.dang);
  }
  function veChat() {
    $('#ai-than').innerHTML = `<div id="ai-tn" class="ai-tn">${A.ls.length ? '' : `<div class="ai-m a"><div class="ai-chu">
        <p>Chào bạn 👋 Mình đọc <b>BCTC và tin tức Wealbee</b> (kèm giá cổ phiếu) để phân tích đầu tư giúp bạn. Hỏi bằng tiếng Việt, ví dụ:</p></div>
        <div id="ai-goi-y" class="ai-goi-y">${GOI_Y().map(x => `<button class="tab">${esc(x)}</button>`).join('')}</div></div>`}</div>
      <form class="ai-nhap" id="ai-form"><textarea id="ai-o" rows="1" placeholder="${D.chon ? `Hỏi về ${D.chon} hoặc mã bất kỳ…` : 'Hỏi về mã cổ phiếu, ngành, tin tức…'}"></textarea>
        <button class="btn" id="ai-gui" type="submit">Gửi</button></form>
      <div class="xs mut2 ai-chan">Gemini bản miễn phí: Google có thể dùng nội dung hỏi đáp để cải thiện sản phẩm, đừng nhập thông tin riêng tư. AI có thể sai, hãy đối chiếu số liệu.</div>`;
    for (const b of document.querySelectorAll('#ai-goi-y button')) b.onclick = () => hoi(b.textContent);
    const o = $('#ai-o');
    o.oninput = () => { o.style.height = 'auto'; o.style.height = Math.min(140, o.scrollHeight) + 'px'; };
    o.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#ai-form').requestSubmit(); } };
    $('#ai-form').onsubmit = e => { e.preventDefault(); if (A.dang) { A.huy?.abort(); return; } const v = o.value; o.value = ''; o.oninput(); hoi(v); };
    veDau(); veNut();
    if (A.htmlCu) { $('#ai-tn').innerHTML = A.htmlCu; A.htmlCu = null; cuon(); }
    if (A.cho) { const c = A.cho; A.cho = null; hoi(c); }           // câu hỏi bấm trước khi có khoá
  }
  async function veCaiDat(thongBao) {
    if ($('#ai-tn')?.children.length && A.ls.length) A.htmlCu = $('#ai-tn').innerHTML;
    const g = await goiNhom();
    const rieng = LS.get('ai_khoa_rieng');
    let model = '';
    if (A.khoa) {
      await dsModel().catch(() => null);
      const ds = [...new Set([...(A.tatCa || []), ...(A.models || [])])].sort((a, b) => ver(b) - ver(a) || a.localeCompare(b));
      model = `<label class="sm">Model Gemini<select id="ai-chon-model" style="width:100%;margin-top:6px"><option value="">Tự chọn (Flash mới nhất, hết lượt thì đổi sang Flash-Lite)</option>
        ${ds.map(m => `<option ${LS.get('ai_model') === m ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select></label>`;
    }
    $('#ai-than').innerHTML = `<div class="ai-tn"><div class="ai-cai">
      ${thongBao ? `<div class="ai-loi">${esc(thongBao)}</div>` : ''}
      ${A.khoa ? `<div class="sm">Đang dùng <b>${esc(A.nguonKhoa)}</b>.</div>${model}` : ''}
      ${g && !(A.khoa && A.nguonKhoa === 'khoá nhóm') ? `<div class="card"><h3>Dùng khoá AI chung của nhóm</h3>
        <div class="sm mut">Nhập mật khẩu nội bộ (cùng mật khẩu web bản Free) để mở khoá Gemini của nhóm.</div>
        <input class="search" id="ai-mk" type="password" placeholder="Mật khẩu nhóm" style="margin-top:10px">
        <button class="btn" id="ai-mo" style="margin-top:10px">Mở khoá</button></div>` : ''}
      <div class="card"><h3>${rieng ? 'Khoá Gemini riêng của bạn' : g ? 'Hoặc dùng khoá Gemini của riêng bạn' : 'Dùng khoá Gemini miễn phí của bạn'}</h3>
        <div class="sm mut">Miễn phí: vào <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a> → <b>Create API key</b> → dán vào đây.
        Khoá chỉ lưu trong trình duyệt này, trang gửi thẳng tới Google, không qua máy chủ nào khác.</div>
        <input class="search" id="ai-khoa" type="password" placeholder="${rieng ? 'Đã lưu khoá riêng · dán khoá mới để thay' : 'AIza…'}" style="margin-top:10px" autocomplete="off">
        <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap"><button class="btn" id="ai-luu">Lưu khoá</button>
        ${rieng ? '<button class="btn sec" id="ai-xoa">Xoá khoá riêng</button>' : ''}</div></div>
      <div class="sm" id="ai-bao"></div>
      ${A.khoa ? '<button class="btn sec" id="ai-ve">← Quay lại trò chuyện</button>' : ''}</div></div>`;
    const bao = t => { $('#ai-bao').innerHTML = t; };
    if ($('#ai-mo')) {
      const mo = async () => {
        bao('Đang giải mã…');
        try { const v = $('#ai-mk').value; A.khoa = (await moGoi(g, v)).khoa; A.nguonKhoa = 'khoá nhóm'; SS.set('mk_noi_bo', v);
          LS.set('ai_khoa_rieng', null); A.models = null; veChat(); } catch { bao('<span class="down">Sai mật khẩu</span>'); }
      };
      $('#ai-mo').onclick = mo; $('#ai-mk').onkeydown = e => { if (e.key === 'Enter') mo(); };
    }
    const luu = async () => {
      const v = $('#ai-khoa').value.trim(); if (!v) return;
      bao('Đang kiểm khoá với Google…');
      const cu = [A.khoa, A.nguonKhoa]; A.khoa = v; A.models = null;
      try { await dsModel(); LS.set('ai_khoa_rieng', v); A.nguonKhoa = 'khoá riêng của bạn'; veChat(); }
      catch (e) { [A.khoa, A.nguonKhoa] = cu; A.models = null; bao(`<span class="down">Khoá không dùng được: ${esc(String(e.message).slice(0, 200))}</span>`); }
    };
    $('#ai-luu').onclick = luu; $('#ai-khoa').onkeydown = e => { if (e.key === 'Enter') luu(); };
    if ($('#ai-xoa')) $('#ai-xoa').onclick = () => { LS.set('ai_khoa_rieng', null); A.khoa = null; A.models = null; A.nguonKhoa = ''; layKhoa().then(() => veCaiDat()); };
    if ($('#ai-chon-model')) $('#ai-chon-model').onchange = e => { LS.set('ai_model', e.target.value || null); A.models = xepModel(A.tatCa || []); A.nghi = {}; };
    if ($('#ai-ve')) $('#ai-ve').onclick = veChat;
    veDau();
  }
  async function mo(cau) {
    $('#ai-khung').classList.add('mo'); $('#ai-nen').classList.add('mo'); document.body.classList.add('ai-dang-mo');
    if (!$('#ai-tn') || $('.ai-cai')) {
      if (await layKhoa()) veChat(); else { A.cho = cau; return veCaiDat(); }
    }
    if (cau) hoi(cau); else setTimeout(() => $('#ai-o')?.focus(), 50);
  }
  function dong() { $('#ai-khung').classList.remove('mo'); $('#ai-nen').classList.remove('mo'); document.body.classList.remove('ai-dang-mo'); }

  function gan() {
    if ($('#ai-khung')) return;
    document.body.insertAdjacentHTML('beforeend', `<button class="ai-noi" id="ai-noi" title="Trợ lý AI phân tích đầu tư">✦ Hỏi AI</button>
      <div class="ai-nen" id="ai-nen"></div>
      <aside class="ai-khung" id="ai-khung" aria-label="Trợ lý AI"><div class="ai-dau"><div class="brand" style="font-size:15px"><i>✦</i>Trợ lý phân tích</div>
        <div class="sp"></div><button class="ai-icon" id="ai-moi" title="Cuộc trò chuyện mới">＋</button><button class="ai-icon" id="ai-cd" title="Khoá và model">⚙</button>
        <button class="ai-icon" id="ai-dong" title="Đóng">✕</button></div>
        <div class="xs mut2" id="ai-model" style="padding:0 16px 8px">Gemini (miễn phí)</div><div id="ai-than" class="ai-than"></div></aside>`);
    $('#ai-noi').onclick = () => mo();
    $('#ai-dong').onclick = dong; $('#ai-nen').onclick = dong;
    $('#ai-cd').onclick = () => veCaiDat();
    $('#ai-moi').onclick = () => { if (A.dang) A.huy?.abort(); A.ls = []; A.htmlCu = null; layKhoa().then(k => k ? veChat() : veCaiDat()); };
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#ai-khung').classList.contains('mo')) dong(); });
    layKhoa().then(veDau);
  }

  window.AI = {gan, mo, phanTich: m => mo(`Phân tích đầu tư mã ${m}: kết quả kinh doanh quý gần nhất và xu hướng, biên lợi nhuận, sức khoẻ tài chính, dòng tiền, tin tức gần đây, diễn biến giá; nêu điểm mạnh, rủi ro và điều cần theo dõi.`),
    _md: md, _cc: CHAY};
})();
