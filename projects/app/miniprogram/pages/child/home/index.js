const api = require('../../../utils/api');
Page({
  data: { routeNote: '证据不足时先做 1–3 份诊断小测确认起点。' },
  onShow() {
    const g = getApp().globalData;
    if (!g.childToken) { wx.navigateTo({ url: '/pages/parent/home/index' }); return; }
    api.request('/v1/children/' + g.childId + '/route', 'GET', {}, g.childToken)
      .then(d => this.setData({ routeNote: d.source === 'graph' ? '路线由知识图谱与规则驱动（不依赖推荐方法命中）。' : '' }))
      .catch(() => {});
  },
  startLesson() { wx.navigateTo({ url: '/pages/child/lesson/index' }); },
  openAsk() { wx.showToast({ title: '拍摄识别待接入；可手输题目', icon: 'none' }); }
});
