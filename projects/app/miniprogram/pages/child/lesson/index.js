Page({
  data: { lessonUrl: '' },
  onLoad() {
    // spike：本地 H5（生产为业务域名下的课堂 H5，对接 T3 answer-filtered API）
    this.setData({ lessonUrl: 'http://127.0.0.1:8080/lesson.html' });
  }
});
