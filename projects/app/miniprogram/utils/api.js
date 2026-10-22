const request = (path, method, data, token) => new Promise((resolve, reject) => {
  wx.request({
    url: getApp().globalData.apiBase + path,
    method: method || 'GET',
    data: data || {},
    header: token ? { Authorization: 'Bearer ' + token } : {},
    success(res) {
      if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data);
      else reject(new Error((res.data && res.data.error && res.data.error.message) || ('HTTP ' + res.statusCode)));
    },
    fail(err) { reject(new Error(err.errMsg)); }
  });
});

module.exports = { request };
