const api = require('../../../utils/api');
Page({
  data: { children: [], selectedId: '', counts: {}, dims: [] },
  onShow() {
    const g = getApp().globalData;
    if (!g.parentToken) return;
    // 不自动挑选孩子：列出档案，家长显式选择（治理规则：缺失身份显式失败，不自动挑选）
    api.request('/v1/children', 'GET', {}, g.parentToken)
      .then(list => this.setData({ children: list || [] }))
      .catch(e => wx.showToast({ title: e.message, icon: 'none' }));
  },
  selectChild(e) {
    const id = e.currentTarget.dataset.id;
    const g = getApp().globalData;
    g.childId = id;
    this.setData({ selectedId: id });
    api.request('/v1/children/' + id + '/switch-session', 'POST', {}, g.parentToken)
      .then(sw => { g.childToken = sw.token; return sw.token; })
      .then(() => Promise.all([
        api.request('/v1/children/' + id + '/reports/summary?days=30', 'GET', {}, g.parentToken),
        api.request('/v1/children/' + id + '/profile/dimensions', 'GET', {}, g.parentToken),
      ]))
      .then(([summary, profile]) => {
        this.setData({ counts: summary.counts, dims: profile.dimensions });
      })
      .catch(e => wx.showToast({ title: e.message, icon: 'none' }));
  }
});
