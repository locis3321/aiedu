/* 被承载课堂：Gate 最小实现（tap_target 门槛 + burst 状态动画 + 过关自动继续） */
(() => {
  'use strict';

  const tokens = document.querySelectorAll('.token');
  const fb = document.getElementById('fb');
  const speech = document.getElementById('speech');

  let unlocked = false;

  function burst(x, y) {
    for (let i = 0; i < 8; i++) {
      const dot = document.createElement('span');
      dot.className = 'burst';
      dot.style.left = x + 'px';
      dot.style.top = y + 'px';
      document.querySelector('.scene').appendChild(dot);
      const angle = (i / 8) * Math.PI * 2;
      dot.animate(
        [
          { transform: 'translate(0,0)', opacity: 1 },
          { transform: `translate(${Math.cos(angle) * 90}px, ${Math.sin(angle) * 90}px)`, opacity: 0 },
        ],
        { duration: 700, easing: 'cubic-bezier(.2,.8,.2,1)' }
      );
      setTimeout(() => dot.remove(), 720);
    }
  }

  tokens.forEach(tok => {
    tok.addEventListener('click', () => {
      if (unlocked) return;
      const value = tok.dataset.v;
      if (value === '2') {
        unlocked = true;
        tok.classList.add('selected');
        fb.textContent = '对啦！8 + 2 = 10。';
        fb.className = 'feedback good';
        speech.textContent = '过关自动继续……（下一步：解释与迁移）';
        const rect = tok.getBoundingClientRect();
        burst(rect.left + rect.width / 2, rect.top + rect.height / 2);
        setTimeout(() => {
          fb.textContent = '完成尝试 → 进入解释（结论文本此时才解锁）';
          window.parent.postMessage({ type: 'lesson', state: 'unlocked' }, '*');
        }, 900);
      } else {
        fb.textContent = '再试一次：想想 10 的补数。';
        fb.className = 'feedback';
        tok.animate([{ transform: 'translateX(0)' }, { transform: 'translateX(10px)' }, { transform: 'translateX(0)' }], { duration: 160 });
      }
    });
  });
})();

// auto=1：自动演示过关（模拟孩子操作），供宿主验证 keep-alive
if (new URLSearchParams(location.search).get('auto') === '1') {
  setTimeout(() => document.querySelector('[data-v="2"]').click(), 800);
}
