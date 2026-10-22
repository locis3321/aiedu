/* 数芽运营后台 SPA：零依赖，对接 /v1/admin/* API。视觉合同 = prototype-v4 :root tokens。 */
(() => {
  'use strict';

  const API_BASE = localStorage.getItem('admin-api-base') || 'http://127.0.0.1:8000';
  const ROUTES = [
    ['overview', '概览'],
    ['reviews', '审核工作台'],
    ['skills', '教学 Skill'],
    ['prompts', '提示词与人设'],
    ['configs', '模型 / TTS / 形象 / 短信'],
    ['library', '题库与题源'],
    ['exams', '试卷模板与结果治理'],
    ['rules', '积分规则 / 安全反馈'],
    ['users', '业务用户'],
    ['audit', '审计'],
    ['trace', 'Trace'],
  ];

  const state = { token: localStorage.getItem('admin-token') || '', role: localStorage.getItem('admin-role') || '', route: 'overview' };

  const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const app = document.querySelector('#app');

  function toast(msg, ok = true) {
    const el = document.createElement('div');
    el.textContent = msg;
    el.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:' + (ok ? '#1d1836' : '#e5484d') + ';color:#fff8d7;padding:12px 20px;border-radius:14px;z-index:99;font-size:14px';
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2600);
  }

  async function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (state.token) headers.Authorization = 'Bearer ' + state.token;
    const resp = await fetch(API_BASE + path, Object.assign({}, options, { headers }));
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const err = body.error || {};
      throw new Error((err.message || resp.statusText) + '（' + (err.code || resp.status) + '）');
    }
    return body;
  }

  function badge(text, tone) {
    const cls = tone === 'green' ? 'green' : tone === 'warm' ? 'warm' : '';
    return '<span class="pill ' + cls + '">' + esc(text) + '</span>';
  }

  function table(headers, rows, emptyText) {
    if (!rows.length) return '<div class="empty">' + esc(emptyText) + '</div>';
    const head = headers.map(h => '<th>' + esc(h) + '</th>').join('');
    return '<div class="table-wrap"><table><thead><tr>' + head + '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
  }

  function pageHead(title, desc) {
    return '<header class="page-head"><h1>' + esc(title) + '</h1><p>' + esc(desc) + '</p></header>';
  }

  function renderLogin() {
    const roles = ['admin', 'reviewer', 'teacher', 'customer_service'];
    const buttons = roles.map(r => '<button class="button" data-role="' + r + '">' + esc(r) + '</button>').join('');
    app.innerHTML = '<div style="max-width:420px;margin:12vh auto;background:#fff;border:1px solid #eadfba;border-radius:24px;padding:34px">'
      + '<div class="brand"><span class="brand-mark">芽</span><span class="brand-name">数芽 · 运营后台<small>真实服务端 · 角色权限在服务端强制</small></span></div>'
      + '<h2 style="margin-top:22px">选择角色登录</h2>'
      + '<div class="row" style="margin-top:14px">' + buttons + '</div>'
      + '<p class="tiny muted" style="margin-top:16px">开发态登录（生产接 SSO）；凭据仅显示配置状态，不返回密钥。</p>'
      + '<label class="tiny muted" style="display:block;margin-top:10px">API 地址<input id="api-base" value="' + esc(API_BASE) + '" style="margin-top:6px"></label>'
      + '</div>';
    app.querySelectorAll('[data-role]').forEach(btn => btn.addEventListener('click', async () => {
      try {
        const data = await api('/v1/admin/login', { method: 'POST', body: JSON.stringify({ role: btn.dataset.role }) });
        state.token = data.token; state.role = data.role;
        localStorage.setItem('admin-token', data.token);
        localStorage.setItem('admin-role', data.role);
        location.hash = '#overview';
        render();
      } catch (e) { toast(e.message, false); }
    }));
    app.querySelector('#api-base').addEventListener('change', e => { localStorage.setItem('admin-api-base', e.target.value); location.reload(); });
  }

  function shell(content) {
    const nav = ROUTES.map(([key, label]) => '<a href="#' + key + '"' + (state.route === key ? ' aria-current="page"' : '') + '>' + esc(label) + '</a>').join('');
    return '<header class="topbar"><div class="brand"><span class="brand-mark">芽</span><span class="brand-name">数芽 · 运营后台<small>真实服务端 · ' + esc(state.role) + '</small></span></div>'
      + '<button class="button small" id="logout">退出登录</button></header>'
      + '<div class="layout"><nav class="nav" aria-label="后台导航">' + nav
      + '<div class="nav-note">浏览器限制不等于服务端权限；所有写操作留审计。</div></nav>'
      + '<main class="main" id="main">' + content + '</main></div>';
  }

  async function renderOverview() {
    const d = await api('/v1/admin/overview');
    const cards = [['待审核内容', d.pending_reviews], ['生成失败任务', d.generation_failed], ['试卷数', d.exam_papers]];
    const html = cards.map(([k, v]) => '<div style="flex:1;background:#fffdf3;border:1px solid #eadfba;border-radius:16px;padding:18px">'
      + '<strong style="font-size:26px">' + (v == null ? '<span class="muted">空状态</span>' : esc(v)) + '</strong>'
      + '<div class="tiny muted">' + esc(k) + '</div></div>').join('');
    return pageHead('运营概览', d.empty_note || '') + '<div class="panel"><h2>关键指标</h2><div class="row">' + html + '</div>'
      + '<p class="tiny muted" style="margin-top:14px">无服务端数据时显示空状态而非伪指标。</p></div>';
  }

  async function renderReviews() {
    const d = await api('/v1/admin/reviews');
    const rows = d.items.map(item => {
      const ev = item.evidence;
      const mathOk = ev.math_verified || ev.math_mode === 'no_math_claims';
      const flags = [
        ['数学核验', mathOk, ev.math_mode === 'no_math_claims' ? '不适用' : null],
        ['教学门禁', ev.teaching_gate_ok, null],
        ['年龄适配', ev.age_ok, null],
        ['布局证据', ev.layout_ok, null],
        ['人工审核', ev.human_reviewed, null],
      ];
      const flagHtml = flags.map(([name, ok, alt]) => name + '：' + (alt ? badge(alt, 'warm') : (ok ? badge('通过', 'green') : badge('缺')))).join('<br>');
      const gateIssues = (item.gate_issues || []).slice(0, 3).map(i => '<br><small class="muted">· ' + esc(i) + '</small>').join('');
      // 服务端硬证据（数学核验/教学门禁）缺失 → 发布按钮锁定（人工证据发布时确认）
      const locked = !(mathOk && ev.teaching_gate_ok);
      const pubBtn = locked
        ? '<button class="button small" disabled title="缺服务端硬证据（数学核验/教学门禁），不可发布">发布（证据缺）</button>'
        : '<button class="button small primary" data-publish="' + esc(item.revision_id) + '">发布</button>';
      return '<tr><td><strong>' + esc(item.lesson_id) + '</strong><br><small class="muted">rev ' + esc(item.revision) + ' · ' + esc(String(item.revision_id).slice(0, 8)) + '</small></td>'
        + '<td>' + badge(item.status === 'published' ? '已发布' : item.status === 'rejected' ? '已驳回' : '待审核', item.status === 'published' ? 'green' : item.status === 'rejected' ? '' : 'warm') + '</td>'
        + '<td><small>' + flagHtml + gateIssues + '</small></td>'
        + '<td>' + pubBtn + ' '
        + '<button class="button small danger" data-reject="' + esc(item.revision_id) + '">驳回</button></td></tr>';
    });
    return pageHead('审核工作台', '缺证据不可发布；管理员不得强改 verified（核验数据只读）')
      + '<div class="panel">' + table(['课程版本', '状态', '证据齐备性', '操作'], rows, '暂无待审核内容；这不是自动审核通过的声明。') + '</div>'
      + '<p class="tiny muted">发布动作只改发布状态，绝不修改 verification 数据；驳回需填写原因。</p>';
  }

  async function renderSkills() {
    const d = await api('/v1/admin/skills');
    const rows = d.items.map(item => '<tr><td><strong>' + esc(item.name) + '</strong><br><small class="muted">v' + esc(item.version) + ' · 引用 ' + esc(item.referenced_count) + '</small></td>'
      + '<td>' + badge(item.enabled ? '启用' : '停用', item.enabled ? 'green' : '') + '</td>'
      + '<td><button class="button small" data-toggle="' + esc(item.id) + '" data-enabled="' + (item.enabled ? 'false' : 'true') + '">' + (item.enabled ? '停用' : '启用') + '</button> '
      + '<button class="button small danger" data-del-skill="' + esc(item.id) + '">删除</button></td></tr>');
    return pageHead('教学 Skill', '导入安全门：≤1MB、always:true 强制剥离、引用中删除阻止')
      + '<div class="panel"><h2>导入新 Skill</h2>'
      + '<label class="tiny muted">name（slug）<input id="skill-name" placeholder="make-ten"></label>'
      + '<label class="tiny muted" style="display:block;margin-top:8px">SKILL.md 内容<textarea id="skill-content" rows="6" placeholder="---&#10;name: make-ten&#10;description: ...&#10;---&#10;方法正文"></textarea></label>'
      + '<button class="button primary" id="skill-import" style="margin-top:10px">导入（安全门校验）</button></div>'
      + '<div class="panel">' + table(['名称', '状态', '操作'], rows, '暂无 Skill。新增时请写清该方法特有步骤与误区。') + '</div>';
  }

  async function renderPrompts() {
    const teaching = await api('/v1/admin/prompts/teaching');
    const companion = await api('/v1/admin/prompts/companion');
    const listRows = items => items.map(i => '<tr><td>v' + esc(i.version) + '</td>'
      + '<td>' + badge(i.status === 'published' ? '已发布' : i.status === 'draft' ? '草稿' : i.status, i.status === 'published' ? 'green' : 'warm') + '</td>'
      + '<td><small>' + esc(i.content_preview) + '…</small></td>'
      + '<td><button class="button small" data-pub-prompt="' + esc(i.kind) + '" data-ver="' + esc(i.version) + '">发布此版本</button></td></tr>');
    return pageHead('提示词与人设', '教学提示词与陪伴人设分开版本管理；全局政策不可被编辑器绕过')
      + '<div class="panel"><h2>教学提示词</h2>' + table(['版本', '状态', '预览', ''], listRows(teaching.items), '暂无版本')
      + '<label class="tiny muted" style="display:block;margin-top:10px">新草稿内容<textarea id="prompt-teaching" rows="4"></textarea></label>'
      + '<button class="button primary small" data-save-prompt="teaching" style="margin-top:8px">保存草稿</button></div>'
      + '<div class="panel"><h2>陪伴人设</h2>' + table(['版本', '状态', '预览', ''], listRows(companion.items), '暂无版本')
      + '<label class="tiny muted" style="display:block;margin-top:10px">新草稿内容<textarea id="prompt-companion" rows="4"></textarea></label>'
      + '<button class="button primary small" data-save-prompt="companion" style="margin-top:8px">保存草稿</button></div>';
  }

  async function renderConfigs() {
    const models = await api('/v1/admin/models-configs');
    const tts = await api('/v1/admin/tts-config');
    const avatar = await api('/v1/admin/ai-avatar');
    const sms = await api('/v1/admin/sms-template');
    const sys = await api('/v1/admin/system-settings');
    const st = sys.settings || {};
    const sc = sys.secrets || {};
    const secretInput = (id, label, key) => '<label class="tiny muted">' + label + '</label><input id="' + id + '" type="password" placeholder="' + (sc[key] && sc[key].configured ? '已配置（尾号 ' + esc(sc[key].tail) + '），留空不修改' : '未配置，输入后加密存储') + '">';
    const modelRows = models.items.map(m => '<tr><td><strong>' + esc(m.name) + '</strong><br><small class="muted">' + esc(m.provider) + ' · ' + esc(m.model) + ' · ' + esc(m.role) + '</small></td>'
      + '<td>' + badge(m.enabled ? '启用' : '停用', m.enabled ? 'green' : '') + '</td>'
      + '<td>' + badge(m.credential_status === 'configured' ? '已配置' : '未配置', m.credential_status === 'configured' ? '' : 'warm') + '<br><small class="muted">' + (m.api_key_tail ? '密钥尾号 ' + esc(m.api_key_tail) : '凭据仅显示状态') + '</small></td>'
      + '<td><button class="button small" data-edit-model="' + esc(m.id) + '" data-config="' + esc(JSON.stringify({ name: m.name, provider: m.provider, model: m.model, role: m.role, credential_status: m.credential_status, base_url: m.base_url || '', temperature: m.temperature == null ? '' : m.temperature, timeout: m.timeout == null ? '' : m.timeout })) + '">编辑（回填）</button></td></tr>');
    return pageHead('模型 / TTS / AI形象 / 短信模板', '凭据只显示配置状态与尾号；未接入渠道显式呈现，不假装成功')
      + '<div class="panel"><h2>模型配置</h2>' + table(['配置名称', '启停', '凭据状态', ''], modelRows, '暂无模型配置。密钥加密存储，不返回明文。')
      + '<div class="row" style="margin-top:12px"><input id="model-name" placeholder="名称"><input id="model-provider" placeholder="provider"><input id="model-model" placeholder="model">'
      + '<select id="model-role"><option value="generate">生成</option><option value="tts">TTS</option><option value="companion">陪伴</option></select>'
      + '<select id="model-cred"><option value="missing">未配置凭据</option><option value="configured">已配置（仅状态）</option></select>'
      + '<button class="button small primary" id="model-save">保存</button></div>'
      + '<div class="row" style="margin-top:8px"><input id="model-base-url" placeholder="base_url（可空，默认环境变量）"><input id="model-temperature" type="number" step="0.1" min="0" max="2" placeholder="温度（可空）"><input id="model-timeout" type="number" step="5" min="5" placeholder="超时秒（可空）">'
      + '<input id="model-api-key" type="password" placeholder="API Key（留空不修改；加密存储）"></div></div>'
      + '<div class="panel"><h2>TTS / AI形象 / 短信模板</h2>'
      + '<div class="row" style="margin-top:8px">'
      + '<select id="tts-provider">' + ['mimo', 'edge'].map(p => '<option value="' + p + '"' + (tts.provider === p ? ' selected' : '') + '>' + (p === 'mimo' ? 'MiMo-V2.5-TTS（免费期）' : 'edge-tts（免费）') + '</option>').join('') + '</select>'
      + '<select id="tts-voice">' + (tts.voices || []).map(v => '<option value="' + esc(v) + '"' + (tts.voice === v ? ' selected' : '') + '>' + esc(v) + '</option>').join('') + '</select>'
      + '<input id="tts-rate" type="number" step="0.05" min="-0.5" max="1" placeholder="语速（edge ±%，如 0.1）" value="' + (tts.rate == null ? '' : esc(tts.rate)) + '">'
      + '<button class="button small primary" id="tts-save">保存</button>'
      + '<button class="button small" id="tts-test">试听</button></div>'
      + '<p class="tiny muted" style="margin-top:8px">' + esc(tts.note || '') + '</p>'
      + '<p>AI形象：' + (avatar.enabled ? badge('已启用', 'green') : badge('未启用')) + '（轻量角色，不影响数学过程动画）</p>'
      + '<p>短信模板：' + (sms.enabled ? badge('已配置', 'green') : badge('未接入')) + ' —— ' + esc(sms.note || '') + '</p>'
      + '<button class="button small" id="avatar-toggle">' + (avatar.enabled ? '关闭 AI 形象' : '启用 AI 形象') + '</button></div>'
      + '<div class="panel"><h2>系统参数</h2>'
      + '<div class="row" style="margin-top:8px"><label class="tiny muted">验证码有效期(秒)</label><input id="sys-sms-ttl" type="number" value="' + esc(st.sms_code_ttl_seconds) + '">'
      + '<label class="tiny muted">最大尝试</label><input id="sys-sms-attempts" type="number" value="' + esc(st.sms_code_max_attempts) + '">'
      + '<label class="tiny muted">冷却(秒)</label><input id="sys-sms-cooldown" type="number" value="' + esc(st.sms_send_cooldown_seconds) + '">'
      + '<label class="tiny muted">每日上限</label><input id="sys-sms-perday" type="number" value="' + esc(st.sms_max_per_day_per_phone) + '"></div>'
      + '<div class="row" style="margin-top:8px"><label class="tiny muted">家长Token(分)</label><input id="sys-token-parent" type="number" value="' + esc(st.access_token_expire_minutes) + '">'
      + '<label class="tiny muted">孩子Token(分)</label><input id="sys-token-child" type="number" value="' + esc(st.child_token_expire_minutes) + '">'
      + '<label class="tiny muted">Grafana</label><input id="sys-grafana" value="' + esc(st.grafana_base_url) + '">'
      + '<label class="tiny muted">题庄URL</label><input id="sys-tizhuang" value="' + esc(st.question_service_url) + '"></div>'
      + '<div class="row" style="margin-top:8px"><label class="tiny muted">存储后端</label><select id="sys-storage-backend"><option value="local"' + (st.storage_backend === 'local' ? ' selected' : '') + '>local</option><option value="s3"' + (st.storage_backend === 's3' ? ' selected' : '') + '>s3</option></select>'
      + '<label class="tiny muted">本地目录</label><input id="sys-storage-dir" value="' + esc(st.storage_local_dir) + '">'
      + '<label class="tiny muted">S3 Endpoint</label><input id="sys-s3-endpoint" value="' + esc(st.s3_endpoint_url || '') + '">'
      + '<label class="tiny muted">S3 Bucket</label><input id="sys-s3-bucket" value="' + esc(st.s3_bucket) + '"></div>'
      + '<div class="row" style="margin-top:8px"><label class="tiny muted">MiMo base_url</label><input id="sys-mimo-base" value="' + esc(st.mimo_base_url) + '">'
      + '<label class="tiny muted">MiMo model</label><input id="sys-mimo-model" value="' + esc(st.mimo_tts_model) + '"></div>'
      + '<button class="button small primary" id="sys-save-plain">保存系统参数</button></div>'
      + '<div class="panel"><h2>凭据（加密存储，仅显示尾号）</h2>'
      + '<div class="row" style="margin-top:8px">' + secretInput('sec-sms-id', '短信SecretId', 'sms_secret_id')
      + secretInput('sec-sms-key', '短信SecretKey', 'sms_secret_key')
      + secretInput('sec-sms-appid', '短信SDKAppID', 'sms_sdk_app_id')
      + secretInput('sec-mimo-key', 'MiMo API Key', 'mimo_api_key') + '</div>'
      + '<div class="row" style="margin-top:8px">' + secretInput('sec-wechat-id', '微信AppID', 'wechat_app_id')
      + secretInput('sec-wechat-secret', '微信AppSecret', 'wechat_app_secret')
      + secretInput('sec-s3-access', 'S3 AccessKey', 's3_access_key')
      + secretInput('sec-s3-secret', 'S3 SecretKey', 's3_secret_key') + '</div>'
      + '<button class="button small primary" id="sys-save-secrets">保存凭据</button></div>';
  }

  async function renderExams() {
    const results = await api('/v1/admin/exam-results');
    const rows = results.items.map(r => '<tr><td><strong>' + esc(r.paper_id.slice(0, 8)) + '</strong><br><small class="muted">' + esc(r.child_id_masked) + '</small></td>'
      + '<td>' + badge(r.overall_level === 'independent' ? '独立完成' : r.overall_level === 'assisted' ? '提示后完成' : r.overall_level === 'demonstrated' ? '示范后完成' : '待观察', r.overall_level === 'independent' ? 'green' : r.overall_level === 'needs_review' ? '' : 'warm') + '</td>'
      + '<td><small>' + esc((r.evidence_levels || []).join(' / ') || '-') + '</small></td>'
      + '<td><small>' + esc(r.source_note || '-') + '</small></td>'
      + '<td><small>' + (r.anomaly ? badge('异常：' + r.anomaly, 'warm') : badge('无异常', 'green')) + '<br>复核：' + esc(r.review_status) + '</small></td>'
      + '<td><button class="button small" data-review-result="' + esc(r.result_id) + '">标记已复核</button></td></tr>');
    return pageHead('试卷模板与结果治理', results.governance_note || '治理视图只读+复核；不可把未完成或未核验结果写成能力结论')
      + '<div class="panel">' + table(['试卷', '证据带', '题源', '异常/复核', '操作'], rows, '暂无试卷结果。') + '</div>';
  }

  async function renderUsers() {
    const d = await api('/v1/admin/users');
    const rows = d.items.map(u => '<tr><td><strong>' + esc(u.id.slice(0, 8)) + '</strong></td>'
      + '<td>' + esc(u.phone_masked || '(未绑定手机号)') + '</td>'
      + '<td>' + (u.wechat_bound ? badge('已绑定微信', 'green') : badge('未绑定')) + '</td></tr>');
    return pageHead('业务用户', '家长列表与孩子详情（按权限访问）；孩子详情含学习证据与积分流水')
      + '<div class="panel">' + table(['家长 ID', '手机号（脱敏）', '微信'], rows, '暂无家长账号。') + '</div>';
  }

  async function renderAudit() {
    const d = await api('/v1/admin/audit?page=1&page_size=20');
    const rows = d.items.map(a => '<tr><td><strong>' + esc(a.action) + '</strong><br><small class="muted">' + esc(a.target_type) + ' · ' + esc(a.target_id || '-') + '</small></td>'
      + '<td><small>' + (a.created_at ? esc(a.created_at.replace('T', ' ').slice(0, 19)) : '-') + '</small></td>'
      + '<td>' + esc(a.actor_role) + '</td>'
      + '<td><button class="button small danger" data-del-audit="' + esc(a.id) + '">删除（需二次确认）</button></td></tr>');
    return pageHead('审计', d.policy_note || '审计删除仅授权策略内且需二次确认；未知 ID 显式报错')
      + '<div class="panel">' + table(['动作', '时间', '角色', '操作'], rows, '暂无审计记录。') + '</div>';
  }

  async function renderTrace() {
    return pageHead('Trace', '输入 Tempo UID 跳转 Grafana（不自建 Trace 列表）')
      + '<div class="panel"><label class="tiny muted">Tempo UID<input id="trace-uid" placeholder="例如 abc123"></label>'
      + '<button class="button primary" id="trace-go" style="margin-top:10px">生成跳转链接</button>'
      + '<p id="trace-result" class="tiny muted" style="margin-top:12px"></p></div>';
  }

  async function renderLibrary() {
    const [questions, sources] = await Promise.all([
      api('/v1/admin/questions'),
      api('/v1/admin/sources'),
    ]);
    const qRows = questions.items.map(q => '<tr><td><strong>' + esc(q.content) + '</strong><br><small class="muted">' + esc(q.knowledge_code) + ' · G' + esc(q.grade) + ' · ' + esc(q.source) + '</small></td>'
      + '<td>' + badge(q.status === 'approved' ? '已审核' : q.status === 'reviewing' ? '审核中' : q.status === 'rejected' ? '已驳回' : '草稿', q.status === 'approved' ? 'green' : q.status === 'rejected' ? '' : 'warm') + '</td>'
      + '<td>' + (q.math_verified ? badge('已核验', 'green') : badge('未核验')) + '</td>'
      + '<td><button class="button small" data-q-approve="' + esc(q.id) + '" data-status="approved">通过</button> '
      + '<button class="button small danger" data-q-approve="' + esc(q.id) + '" data-status="rejected">驳回</button></td></tr>');
    const sRows = sources.items.map(s => '<tr><td><strong>' + esc(s.name) + '</strong><br><small class="muted">' + esc(s.provider) + '</small></td>'
      + '<td>' + badge(s.enabled ? '启用' : '停用', s.enabled ? 'green' : '') + '</td>'
      + '<td><button class="button small" data-src-connect="' + esc(s.id) + '">连接测试</button></td></tr>');
    return pageHead('题库与题源', '内置题审核态管理（A4）；第三方题源接入/启停/连接测试（A6，未验证前显式呈现）')
      + '<div class="panel"><h2>新增内置题</h2>'
      + '<div class="row" style="margin-top:8px"><input id="q-content" placeholder="题目内容"><input id="q-answer" placeholder="答案"><input id="q-code" placeholder="knowledge_code"><input id="q-grade" placeholder="年级" type="number" min="1" max="12">'
      + '<button class="button small primary" id="q-create">保存（草稿）</button></div></div>'
      + '<div class="panel">' + table(['题目', '状态', '数学核验', '操作'], qRows, '暂无内置题。来源不可伪造。') + '</div>'
      + '<div class="panel"><h2>第三方题源</h2>'
      + '<div class="row" style="margin-top:8px"><input id="src-name" placeholder="名称"><input id="src-provider" placeholder="provider（如 tizhuang）">'
      + '<button class="button small primary" id="src-create">保存</button></div>'
      + table(['题源', '状态', '操作'], sRows, '暂无第三方题源。实际接入待供应商验证后启用。') + '</div>';
  }

  async function renderRules() {
    const [rules, feedbacks] = await Promise.all([
      api('/v1/admin/reward-rules'),
      api('/v1/admin/safety-feedbacks'),
    ]);
    const rRows = rules.items.map(r => '<tr><td>v' + esc(r.version) + '</td>'
      + '<td>' + esc(r.event_type) + '</td>'
      + '<td><small>独立 ' + esc(r.points.independent) + ' / 提示后 ' + esc(r.points.assisted) + ' / 示范后 ' + esc(r.points.demonstrated) + '</small></td>'
      + '<td>' + badge(r.enabled ? '启用' : '停用', r.enabled ? 'green' : '') + '</td></tr>');
    const fRows = feedbacks.items.map(f => '<tr><td><strong>' + esc(f.child_id_masked || '-') + '</strong></td>'
      + '<td><small>' + esc(f.summary_text || '(摘要为空)') + '</small></td>'
      + '<td>' + badge(f.status === 'handled' ? '已处置' : f.status === 'open' ? '待处置' : f.status, f.status === 'handled' ? '' : 'warm') + '</td>'
      + '<td>' + (f.status === 'handled' ? '' : '<button class="button small" data-fb-handle="' + esc(f.id) + '">标记已处置</button>') + '</td></tr>');
    return pageHead('积分规则 / 安全反馈', '积分规则版本化不追改历史流水（A10）；陪伴安全反馈处置（A14，摘要非完整对话）')
      + '<div class="panel"><h2>新增成长星规则版本</h2>'
      + '<div class="row" style="margin-top:8px"><input id="rule-ind" placeholder="独立完成分" type="number"><input id="rule-assist" placeholder="提示后分" type="number"><input id="rule-demo" placeholder="示范后分" type="number"><input id="rule-cap" placeholder="每日上限（可空）" type="number">'
      + '<button class="button small primary" id="rule-create">新建版本（仅 admin）</button></div></div>'
      + '<div class="panel">' + table(['版本', '事件', '分值', '状态'], rRows, '暂无积分规则。') + '</div>'
      + '<div class="panel">' + table(['孩子（脱敏）', '摘要', '状态', '操作'], fRows, '暂无安全反馈条目。') + '</div>';
  }

  const RENDERERS = {
    overview: renderOverview,
    reviews: renderReviews,
    skills: renderSkills,
    prompts: renderPrompts,
    configs: renderConfigs,
    library: renderLibrary,
    exams: renderExams,
    rules: renderRules,
    users: renderUsers,
    audit: renderAudit,
    trace: renderTrace,
  };

  async function render() {
    if (!state.token) { renderLogin(); return; }
    const route = state.route;
    try {
      const content = await RENDERERS[route]();
      app.innerHTML = shell(content);
      bindEvents(route);
    } catch (e) {
      if (String(e.message).includes('UNAUTHORIZED') || String(e.message).includes('登录状态')) {
        state.token = ''; localStorage.removeItem('admin-token'); renderLogin(); return;
      }
      app.innerHTML = shell('<div class="panel error-box">' + esc(e.message) + '</div>');
      bindEvents(route);
    }
  }

  function bindEvents(route) {
  const logout = app.querySelector('#logout');
  if (logout) logout.addEventListener('click', () => {
    state.token = '';
    localStorage.removeItem('admin-token');
    renderLogin();
  });

  app.querySelectorAll('[data-publish]').forEach(b => b.addEventListener('click', async () => {
    // 人工证据逐项确认（教学门禁由生成期记录服务端判定，前端不可自证）
    if (!confirm('数学核验与教学方法门禁已由系统记录。请逐项确认：\n1) 年龄适配已人工核对\n2) 布局呈现已核对\n3) 已完成人工审核\n确定发布？')) return;
    try {
      await api('/v1/admin/reviews/' + b.dataset.publish + '/publish', {
        method: 'POST',
        body: JSON.stringify({ age_ok: true, layout_ok: true, human_reviewed: true }),
      });
      toast('已发布（证据齐备）');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  app.querySelectorAll('[data-reject]').forEach(b => b.addEventListener('click', async () => {
    const reason = prompt('驳回原因（必填）');
    if (!reason) return;
    try {
      await api('/v1/admin/reviews/' + b.dataset.reject + '/reject', { method: 'POST', body: JSON.stringify({ reason }) });
      toast('已驳回');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  const skillImport = app.querySelector('#skill-import');
  if (skillImport) skillImport.addEventListener('click', async () => {
    try {
      const name = app.querySelector('#skill-name').value.trim();
      const content = app.querySelector('#skill-content').value;
      await api('/v1/admin/skills', { method: 'POST', body: JSON.stringify({ name, content }) });
      toast('Skill 导入成功（安全门通过）');
      render();
    } catch (e) { toast(e.message, false); }
  });

  app.querySelectorAll('[data-toggle]').forEach(b => b.addEventListener('click', async () => {
    try {
      await api('/v1/admin/skills/' + b.dataset.toggle + '/toggle?enabled=' + b.dataset.enabled, { method: 'POST' });
      toast('已更新');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  app.querySelectorAll('[data-del-skill]').forEach(b => b.addEventListener('click', async () => {
    if (!confirm('确认删除该 Skill？')) return;
    try {
      await api('/v1/admin/skills/' + b.dataset.delSkill, { method: 'DELETE' });
      toast('已删除');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  app.querySelectorAll('[data-save-prompt]').forEach(b => b.addEventListener('click', async () => {
    const kind = b.dataset.savePrompt;
    const content = app.querySelector('#prompt-' + kind).value;
    try {
      await api('/v1/admin/prompts/' + kind, { method: 'POST', body: JSON.stringify({ content }) });
      toast('草稿已保存');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  app.querySelectorAll('[data-pub-prompt]').forEach(b => b.addEventListener('click', async () => {
    try {
      await api('/v1/admin/prompts/' + b.dataset.pubPrompt + '/' + b.dataset.ver + '/publish', { method: 'POST' });
      toast('已发布');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  const num = (el) => { const v = el.value.trim(); return v === '' ? null : Number(v); };

  app.querySelectorAll('[data-edit-model]').forEach(b => b.addEventListener('click', () => {
    const c = JSON.parse(b.dataset.config);
    app.querySelector('#model-name').value = c.name || '';
    app.querySelector('#model-provider').value = c.provider || '';
    app.querySelector('#model-model').value = c.model || '';
    app.querySelector('#model-role').value = c.role || 'generate';
    app.querySelector('#model-cred').value = c.credential_status || 'missing';
    app.querySelector('#model-base-url').value = c.base_url || '';
    app.querySelector('#model-temperature').value = c.temperature;
    app.querySelector('#model-timeout').value = c.timeout;
    app.querySelector('#model-api-key').value = '';
    toast('已回填（API Key 留空即保持原密钥）');
  }));

  const ttsProvider = app.querySelector('#tts-provider');
  if (ttsProvider) ttsProvider.addEventListener('change', async () => {
    // 切换供应商后刷新音色列表（voices 与 provider 绑定）
    try {
      const d = await api('/v1/admin/tts-config');
      const box = app.querySelector('#tts-voice');
      box.innerHTML = (d.voices || []).map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join('');
      if (d.voice && (d.voices || []).includes(d.voice)) box.value = d.voice;
    } catch (e) { toast(e.message, false); }
  });

  const modelSave = app.querySelector('#model-save');
  if (modelSave) modelSave.addEventListener('click', async () => {
    try {
      await api('/v1/admin/models-configs', {
        method: 'POST',
        body: JSON.stringify({
          name: app.querySelector('#model-name').value.trim(),
          provider: app.querySelector('#model-provider').value.trim(),
          model: app.querySelector('#model-model').value.trim(),
          role: app.querySelector('#model-role').value,
          credential_status: app.querySelector('#model-cred').value,
          base_url: app.querySelector('#model-base-url').value.trim() || null,
          temperature: app.querySelector('#model-temperature').value ? Number(app.querySelector('#model-temperature').value) : null,
          timeout: app.querySelector('#model-timeout').value ? Number(app.querySelector('#model-timeout').value) : null,
          api_key: app.querySelector('#model-api-key').value || null,
        }),
      });
      toast('模型配置已保存（密钥加密存储，仅显示尾号）');
      render();
    } catch (e) { toast(e.message, false); }
  });

  const avatarToggle = app.querySelector('#avatar-toggle');
  if (avatarToggle) avatarToggle.addEventListener('click', async () => {
    const current = avatarToggle.textContent.includes('关闭');
    try {
      await api('/v1/admin/ai-avatar', { method: 'PUT', body: JSON.stringify({ enabled: !current }) });
      toast('AI 形象配置已更新');
      render();
    } catch (e) { toast(e.message, false); }
  });

  const ttsSave = app.querySelector('#tts-save');
  if (ttsSave) ttsSave.addEventListener('click', async () => {
    const rateEl = app.querySelector('#tts-rate');
    try {
      await api('/v1/admin/tts-config', {
        method: 'PUT',
        body: JSON.stringify({
          provider: app.querySelector('#tts-provider').value,
          voice: app.querySelector('#tts-voice').value,
          rate: rateEl.value ? Number(rateEl.value) : null,
        }),
      });
      toast('TTS 配置已保存');
      render();
    } catch (e) { toast(e.message, false); }
  });

  const ttsTest = app.querySelector('#tts-test');
  if (ttsTest) ttsTest.addEventListener('click', async () => {
    try {
      const d = await api('/v1/admin/tts-config/test', {
        method: 'POST',
        body: JSON.stringify({ voice: app.querySelector('#tts-voice').value }),
      });
      const audio = new Audio('data:audio/' + d.format + ';base64,' + d.audio_base64);
      audio.play().then(() => toast('试听中（' + d.provider + '）')).catch(() => toast('浏览器阻止自动播放，请点击播放器', false));
    } catch (e) { toast(e.message, false); }
  });

  const sysSavePlain = app.querySelector('#sys-save-plain');
  if (sysSavePlain) sysSavePlain.addEventListener('click', async () => {
    try {
      await api('/v1/admin/system-settings', {
        method: 'PUT',
        body: JSON.stringify({ values: {
          sms_code_ttl_seconds: num(app.querySelector('#sys-sms-ttl')),
          sms_code_max_attempts: num(app.querySelector('#sys-sms-attempts')),
          sms_send_cooldown_seconds: num(app.querySelector('#sys-sms-cooldown')),
          sms_max_per_day_per_phone: num(app.querySelector('#sys-sms-perday')),
          access_token_expire_minutes: num(app.querySelector('#sys-token-parent')),
          child_token_expire_minutes: num(app.querySelector('#sys-token-child')),
          grafana_base_url: app.querySelector('#sys-grafana').value.trim(),
          question_service_url: app.querySelector('#sys-tizhuang').value.trim(),
          storage_backend: app.querySelector('#sys-storage-backend').value,
          storage_local_dir: app.querySelector('#sys-storage-dir').value.trim(),
          s3_endpoint_url: app.querySelector('#sys-s3-endpoint').value.trim() || null,
          s3_bucket: app.querySelector('#sys-s3-bucket').value.trim(),
          mimo_base_url: app.querySelector('#sys-mimo-base').value.trim(),
          mimo_tts_model: app.querySelector('#sys-mimo-model').value.trim(),
        } }),
      });
      toast('系统参数已保存');
      render();
    } catch (e) { toast(e.message, false); }
  });

  const sysSaveSecrets = app.querySelector('#sys-save-secrets');
  if (sysSaveSecrets) sysSaveSecrets.addEventListener('click', async () => {
    const pick = (id) => { const v = app.querySelector(id).value; return v ? v : null; };
    try {
      await api('/v1/admin/system-settings/secrets', {
        method: 'POST',
        body: JSON.stringify({ values: {
          sms_secret_id: pick('#sec-sms-id'),
          sms_secret_key: pick('#sec-sms-key'),
          sms_sdk_app_id: pick('#sec-sms-appid'),
          mimo_api_key: pick('#sec-mimo-key'),
          wechat_app_id: pick('#sec-wechat-id'),
          wechat_app_secret: pick('#sec-wechat-secret'),
          s3_access_key: pick('#sec-s3-access'),
          s3_secret_key: pick('#sec-s3-secret'),
        } }),
      });
      toast('凭据已保存（加密存储，仅显示尾号）');
      render();
    } catch (e) { toast(e.message, false); }
  });

  app.querySelectorAll('[data-review-result]').forEach(b => b.addEventListener('click', async () => {
    try {
      await api('/v1/admin/exam-results/' + b.dataset.reviewResult + '/review', { method: 'POST' });
      toast('已标记复核（不产生能力结论）');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  app.querySelectorAll('[data-del-audit]').forEach(b => b.addEventListener('click', async () => {
    if (!confirm('删除审计记录属高危操作，需二次确认。确认删除？')) return;
    try {
      await api('/v1/admin/audit/' + b.dataset.delAudit + '?confirm=true', { method: 'DELETE' });
      toast('已删除');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  const traceGo = app.querySelector('#trace-go');
  if (traceGo) traceGo.addEventListener('click', async () => {
    const uid = app.querySelector('#trace-uid').value.trim();
    if (!uid) return;
    try {
      const d = await api('/v1/admin/trace?uid=' + encodeURIComponent(uid));
      app.querySelector('#trace-result').innerHTML = '<a href="' + esc(d.grafana_url) + '" target="_blank" rel="noopener">打开 Grafana Trace</a>';
    } catch (e) { toast(e.message, false); }
  });

  const qCreate = app.querySelector('#q-create');
  if (qCreate) qCreate.addEventListener('click', async () => {
    try {
      await api('/v1/admin/questions', {
        method: 'POST',
        body: JSON.stringify({
          content: app.querySelector('#q-content').value.trim(),
          answer: app.querySelector('#q-answer').value.trim(),
          knowledge_code: app.querySelector('#q-code').value.trim(),
          grade: Number(app.querySelector('#q-grade').value || 1),
        }),
      });
      toast('题目已保存（草稿，需审核）');
      render();
    } catch (e) { toast(e.message, false); }
  });

  app.querySelectorAll('[data-q-approve]').forEach(b => b.addEventListener('click', async () => {
    try {
      await api('/v1/admin/questions/' + b.dataset.qApprove + '/status', {
        method: 'POST', body: JSON.stringify({ status: b.dataset.status }),
      });
      toast('状态已更新');
      render();
    } catch (e) { toast(e.message, false); }
  }));

  const srcCreate = app.querySelector('#src-create');
  if (srcCreate) srcCreate.addEventListener('click', async () => {
    try {
      await api('/v1/admin/sources', {
        method: 'POST',
        body: JSON.stringify({
          name: app.querySelector('#src-name').value.trim(),
          provider: app.querySelector('#src-provider').value.trim(),
        }),
      });
      toast('题源已保存');
      render();
    } catch (e) { toast(e.message, false); }
  });

  app.querySelectorAll('[data-src-connect]').forEach(b => b.addEventListener('click', async () => {
    try {
      const d = await api('/v1/admin/sources/' + b.dataset.srcConnect + '/connect-test', { method: 'POST' });
      toast(d.connected ? '连接成功（' + (d.note || '') + '）' : '未接入：' + (d.note || ''));
      render();
    } catch (e) { toast(e.message, false); }
  }));

  const ruleCreate = app.querySelector('#rule-create');
  if (ruleCreate) ruleCreate.addEventListener('click', async () => {
    try {
      await api('/v1/admin/reward-rules', {
        method: 'POST',
        body: JSON.stringify({
          points_independent: Number(app.querySelector('#rule-ind').value || 0),
          points_assisted: Number(app.querySelector('#rule-assist').value || 0),
          points_demonstrated: Number(app.querySelector('#rule-demo').value || 0),
          daily_cap: app.querySelector('#rule-cap').value ? Number(app.querySelector('#rule-cap').value) : null,
        }),
      });
      toast('规则版本已创建（不追改历史流水）');
      render();
    } catch (e) { toast(e.message, false); }
  });

  app.querySelectorAll('[data-fb-handle]').forEach(b => b.addEventListener('click', async () => {
    try {
      await api('/v1/admin/safety-feedbacks/' + b.dataset.fbHandle + '/handle', { method: 'POST' });
      toast('已标记处置（不展示完整对话）');
      render();
    } catch (e) { toast(e.message, false); }
  }));
}

window.addEventListener('hashchange', () => {
  const route = (location.hash || '#overview').slice(1);
  if (ROUTES.some(r => r[0] === route)) {
    state.route = route;
    render();
  }
});

state.route = (location.hash || '#overview').slice(1);
if (!ROUTES.some(r => r[0] === state.route)) state.route = 'overview';
render();
})();
