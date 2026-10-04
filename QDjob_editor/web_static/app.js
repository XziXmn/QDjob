/* ===================== QDjob WebUI 公共脚本 ===================== */
(function () {
  'use strict';

  const APP = window.APP || {};

  // ---------- 主题 ----------
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('qdjob-theme', theme);
  }
  const themeBtn = document.getElementById('theme-btn');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      const order = ['auto', 'light', 'dark'];
      const cur = localStorage.getItem('qdjob-theme') || 'auto';
      const next = order[(order.indexOf(cur) + 1) % order.length];
      applyTheme(next);
      toast('主题已切换为: ' + ({ auto: '跟随系统', light: '浅色', dark: '深色' }[next]), 'ok');
    });
  }

  // ---------- 侧栏（移动端）----------
  const menuBtn = document.getElementById('menu-btn');
  const backdrop = document.getElementById('sidebar-backdrop');
  function closeSidebar() { document.body.classList.remove('sidebar-open'); }
  if (menuBtn) menuBtn.addEventListener('click', () => document.body.classList.toggle('sidebar-open'));
  if (backdrop) backdrop.addEventListener('click', closeSidebar);

  // ---------- Toast ----------
  const toastContainer = document.getElementById('toast-container');
  function toast(message, type) {
    if (!toastContainer) { console.log(message); return; }
    const el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.textContent = message;
    toastContainer.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 2600);
    setTimeout(() => el.remove(), 3000);
  }

  // ---------- Modal ----------
  const modalRoot = document.getElementById('modal-root');
  function openModal(html) {
    if (!modalRoot) return;
    modalRoot.innerHTML = '<div class="modal-backdrop"></div><div class="modal">' + html + '</div>';
    modalRoot.classList.add('open');
    const bd = modalRoot.querySelector('.modal-backdrop');
    if (bd) bd.addEventListener('click', closeModal);
  }
  function closeModal() {
    if (!modalRoot) return;
    modalRoot.classList.remove('open');
    modalRoot.innerHTML = '';
  }
  function confirmDialog(message, title) {
    return new Promise(function (resolve) {
      openModal(
        '<h3>' + escapeHtml(title || '确认') + '</h3>' +
        '<p>' + escapeHtml(message) + '</p>' +
        '<div class="modal-actions">' +
        '<button class="btn" id="dlg-cancel">取消</button>' +
        '<button class="btn danger" id="dlg-ok">确定</button>' +
        '</div>'
      );
      document.getElementById('dlg-cancel').onclick = function () { closeModal(); resolve(false); };
      document.getElementById('dlg-ok').onclick = function () { closeModal(); resolve(true); };
    });
  }

  // ---------- 内联状态提示（按钮附近持久显示） ----------
  function status(target, type, title, detail) {
    const el = typeof target === 'string' ? qs(target) : target;
    if (!el) return;
    const icons = { ok: '✅', err: '❌', warn: '⚠️', info: 'ℹ️' };
    el.innerHTML = '<div class="inline-msg ' + (type || 'info') + '">' +
      '<span class="icon">' + (icons[type] || icons.info) + '</span>' +
      '<div class="body"><div class="title">' + escapeHtml(title || '') + '</div>' +
      (detail ? '<div class="detail">' + detail + '</div>' : '') +
      '</div></div>';
  }

  function clearStatus(target) {
    const el = typeof target === 'string' ? qs(target) : target;
    if (el) el.innerHTML = '';
  }

  // ---------- 工具 ----------
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ---------- API ----------
  async function api(method, url, data, opts) {
    opts = opts || {};
    const headers = { 'Accept': 'application/json' };
    if (data !== undefined && data !== null) headers['Content-Type'] = 'application/json';
    if (APP.csrfToken) headers['X-CSRF-Token'] = APP.csrfToken;
    let resp;
    try {
      resp = await fetch(url, {
        method: method,
        headers: headers,
        credentials: 'same-origin',
        body: (data !== undefined && data !== null) ? JSON.stringify(data) : undefined,
      });
    } catch (e) {
      if (!opts.silent) toast('网络请求失败: ' + e.message, 'err');
      throw e;
    }
    if (resp.status === 401) {
      toast('登录已失效，正在跳转...', 'warn');
      setTimeout(() => { window.location.href = '/login'; }, 800);
      throw new Error('unauthorized');
    }
    let json = null;
    try { json = await resp.json(); } catch (e) { json = { ok: false, message: '服务器返回异常' }; }
    if (!json.ok && !opts.silent) toast(json.message || '操作失败', 'err');
    return json;
  }

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // 暴露到全局
  window.UI = {
    api, toast, openModal, closeModal, confirmDialog,
    escapeHtml, qs, qsa, applyTheme, solveCaptcha, status, clearStatus,
  };

  // ---------- 腾讯验证码（内嵌浏览器，替代 pywebview）----------
  var CAPTCHA_APPID = '1600000770';
  var captchaLoading = null;

  function ensureCaptchaScript() {
    if (window.TencentCaptcha) return Promise.resolve(true);
    if (captchaLoading) return captchaLoading;
    captchaLoading = new Promise(function (resolve) {
      var s = document.createElement('script');
      s.src = 'https://turing.captcha.qcloud.com/TJCaptcha.js';
      s.onload = function () { resolve(true); };
      s.onerror = function () { captchaLoading = null; resolve(false); };
      document.head.appendChild(s);
    });
    return captchaLoading;
  }

  /**
   * 触发腾讯验证码，成功返回 {randstr, ticket}；失败返回 null。
   * 若验证码脚本无法加载（网络受限），使用与原 template.html 一致的兜底逻辑。
   */
  function solveCaptcha() {
    return new Promise(function (resolve) {
      function fallback() {
        var ticket = 'trerror_1001_' + CAPTCHA_APPID + '_' + Math.floor(Date.now() / 1000);
        resolve({
          randstr: '@' + Math.random().toString(36).slice(2),
          ticket: ticket,
          fallback: true,
        });
      }
      function callback(res) {
        if (res && res.ret === 0) resolve({ randstr: res.randstr, ticket: res.ticket });
        else resolve(null);
      }
      ensureCaptchaScript().then(function (loaded) {
        if (!loaded || typeof window.TencentCaptcha === 'undefined') { fallback(); return; }
        try {
          var cap = new window.TencentCaptcha(CAPTCHA_APPID, callback, { userLanguage: 'zh-cn' });
          cap.show();
        } catch (e) { fallback(); }
      });
    });
  }
})();

