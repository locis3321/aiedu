const api = require('../../../utils/api');
Page({
  data: { phone: '', code: '', loginNote: '手机号+短信验证码登录（dev 模式固定验证码 123456，控制台打印 [dev]）' },
  onPhone(e) { this.setData({ phone: e.detail.value }); },
  onCode(e) { this.setData({ code: e.detail.value }); },
  sendCode() {
    api.request('/v1/auth/sms/send', 'POST', { phone: this.data.phone })
      .then(d => wx.showToast({ title: '验证码已发送（mode=' + d.mode + '）', icon: 'none' }))
      .catch(e => wx.showToast({ title: e.message, icon: 'none' }));
  },
  login() {
    api.request('/v1/auth/parents/login-sms', 'POST', { phone: this.data.phone, code: this.data.code })
      .then(d => {
        getApp().globalData.parentToken = d.token;
        wx.navigateTo({ url: '/pages/parent/report/index' });
      })
      .catch(e => wx.showToast({ title: e.message, icon: 'none' }));
  }
});
