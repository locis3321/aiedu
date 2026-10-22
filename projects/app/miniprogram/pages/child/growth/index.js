const api = require('../../../utils/api');
Page({
  data: { summary: '', items: [] },
  onShow() {
    const g = getApp().globalData;
    if (!g.childToken) return;
    api.request('/v1/children/' + g.childId + '/footprints?days=30', 'GET', {}, g.childToken)
      .then(d => this.setData({ items: d.items, summary: d.note || (d.items.length + ' 次学习记录') }))
      .catch(() => this.setData({ summary: '暂未获取到足迹' }));
  }
});
