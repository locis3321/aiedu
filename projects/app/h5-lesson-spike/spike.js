/* 宿主逻辑：fitGenUiViewport scale 适配 + sandbox iframe + keep-alive pool */
(() => {
  'use strict';

  const LOGICAL_W = 1280;
  const LOGICAL_H = 720;
  const POOL_MAX = 2;

  const host = document.getElementById('host');
  const vpLabel = document.getElementById('vp');
  const note = document.getElementById('note');

  // keep-alive pool：场景切换不卸载文档（LRU）
  const pool = new Map(); // key -> iframe

  function fitGenUiViewport(iframe, containerW, containerH) {
    // scale = min(容器宽/逻辑宽, 容器高/逻辑高)；居中；容器小于逻辑时裁剪由 overflow:hidden 完成
    const scale = Math.min(containerW / LOGICAL_W, containerH / LOGICAL_H);
    iframe.style.width = `${LOGICAL_W * scale}px`;
    iframe.style.height = `${LOGICAL_H * scale}px`;
    return scale;
  }

  function mount(key, src) {
    let frame = pool.get(key);
    if (!frame) {
      frame = document.createElement('iframe');
      frame.setAttribute('sandbox', 'allow-scripts'); // 无 allow-same-origin：null origin，无法访问宿主存储/DOM
      frame.setAttribute('title', '课堂');
      frame.src = src + '?auto=1';
      pool.set(key, frame);
      if (pool.size > POOL_MAX) {
        const oldest = pool.keys().next().value;
        pool.get(oldest).remove();
        pool.delete(oldest);
      }
    }
    host.appendChild(frame);
    return frame;
  }

  function show(key) {
    host.innerHTML = '';
    const frame = mount(key, 'lesson.html');
    fitGenUiViewport(frame, host.clientWidth, host.clientHeight);
    vpLabel.textContent = `${host.clientWidth}×${host.clientHeight}`;
  }

  document.querySelectorAll('[data-w]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-w]').forEach(b => b.setAttribute('aria-pressed', 'false'));
      btn.setAttribute('aria-pressed', 'true');
      const w = Number(btn.dataset.w);
      host.style.width = w + 'px';
      host.style.height = Math.round(w * 0.66) + 'px';
      show('scene-a');
    });
  });

  window.addEventListener('message', e => {
    if (e.data && e.data.type === 'lesson') {
      note.textContent = 'iframe状态：' + e.data.state + '（keep-alive pool）';
    }
  });

  document.getElementById('reload').addEventListener('click', () => {
    pool.forEach(f => f.remove());
    pool.clear();
    show('scene-a');
  });

  // 默认：宿主全屏
  host.style.width = '100%';
  host.style.height = '100%';
  show('scene-a');
})();
