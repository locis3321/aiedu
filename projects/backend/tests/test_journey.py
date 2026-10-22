# ruff: noqa: E501
"""T11 集成 E2E：三条跨端旅程（真实本地栈 PG16+Redis，非 mock）。

家长旅程：短信dev登录→监护同意→建档两个孩子→初步路线/诊断建议→报告(四级分列+画像视图)→安排练习
孩子旅程：选孩子→session→课堂尝试(先想后看/提示阶梯)→证据落库→积分幂等发放→足迹回看
治理旅程：内核生成→待审核→缺证据阻断→补齐发布→method_source；试卷模板审核+结果治理
"""

import random

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.jobs.service import publish_revision
from app.points import service as points_service
from app.storage.db import create_session_factory
from app.strategies import make_ten

pytestmark = pytest.mark.e2e

FIXED_CODE = "123456"


def _phone():
    return '138' + str(random.randint(10000000, 99999999))


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def db():
    factory = create_session_factory()
    with factory() as session:
        yield session


@pytest.fixture(autouse=True)
def _admin_dev_login(monkeypatch):
    """e2e 旅程使用开发态后台登录（生产默认关闭，见 test_admin.py）。"""
    monkeypatch.setenv("ADMIN_DEV_LOGIN_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def auth(token):
    return {"Authorization": "Bearer " + token}


def _register_parent(client, phone=None):
    phone = phone or _phone()
    client.post('/v1/auth/sms/send', json={'phone': phone})
    resp = client.post('/v1/auth/parents/login-sms', json={'phone': phone, 'code': FIXED_CODE})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _grant_consents(client, token, pid):
    for key in ('guardian_rules', 'privacy_notice'):
        r = client.post('/v1/parents/' + pid + '/consents', json={'consent_key': key}, headers=auth(token))
        assert r.status_code == 200, r.text


def _create_child(client, token, nickname, grade):
    r = client.post('/v1/children', json={'nickname': nickname, 'grade': grade}, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()['id']


def _publish_make_ten(db, a=16, b=8, k=2, mark_published=False):
    from app.jobs.service import next_revision

    spec = make_ten.build({'a': a, 'b': b, 'k': k}).model_dump(mode='json')
    # 生成期门禁记录（服务端产生）：make-ten 无 MAJOR 违规
    spec['_meta'] = {'gate_report': {'issues': [], 'passed': True}}
    rev_no = next_revision(db, spec['lesson_id'])
    publish_revision(db, lesson_id=spec['lesson_id'], revision=rev_no,
                     spec_json=spec, runtime_version='0.1.0', asset_manifest_ref=None)
    if mark_published:
        _mark_published(db, spec['lesson_id'], rev_no)
    spec['revision'] = rev_no
    return spec


def _mark_published(db, lesson_id: str, revision: int) -> None:
    """人工审核发布：写 ReviewRecord(published)（护栏5：孩子侧仅可用已发布课程）。"""
    from app.admin_api.models import ReviewRecord
    from app.storage.models import LessonRevision

    rev = (
        db.query(LessonRevision)
        .filter_by(lesson_id=lesson_id, revision=revision)
        .first()
    )
    record = ReviewRecord(revision_id=rev.id, lesson_id=rev.lesson_id)
    record.math_verified = True
    record.teaching_gate_ok = True
    record.age_ok = True
    record.layout_ok = True
    record.human_reviewed = True
    record.status = "published"
    db.add(record)
    db.commit()


# ---------------------------------------------------------------- 家长旅程


def test_parent_journey(client, db):
    data = _register_parent(client)
    token, pid = data['token'], data['user']['id']
    _grant_consents(client, token, pid)

    # 建档两个孩子
    child_a = _create_child(client, token, '小禾', '3')
    child_b = _create_child(client, token, '小川', '7')
    assert child_a != child_b

    # 证据不足 → 初步路线（source=graph）+ 诊断建议
    route = client.get('/v1/children/' + child_a + '/route', headers=auth(token))
    assert route.status_code == 200 and route.json()['source'] == 'graph'
    diag = client.post('/v1/children/' + child_a + '/diagnostics', headers=auth(token))
    assert diag.status_code in (200, 422)  # 无已审核题时显式失败（不编造）

    # 报告：四级分列 + 画像视图（无证据=待观察）
    summary = client.get('/v1/children/' + child_a + '/reports/summary?days=30', headers=auth(token))
    assert summary.status_code == 200
    counts = summary.json()['counts']
    assert set(counts) == {'independent', 'assisted', 'demonstrated', 'needs_review'}
    profile = client.get('/v1/children/' + child_a + '/reports/profile-view', headers=auth(token))
    dims = {d['code']: d for d in profile.json()['dimensions']}
    assert dims['operations']['level'] == 'needs_review'  # 无证据=待观察，非0分

    # 安排练习：无薄弱点证据 → 显式说明，不自动挑选默认题
    ps = client.post('/v1/children/' + child_a + '/practice-sets', headers=auth(token))
    body = ps.json()
    assert body['question_ids'] == [] and '暂无薄弱点证据' in body['basis']['note']


# ---------------------------------------------------------------- 孩子旅程


def test_child_journey(client, db):
    spec = _publish_make_ten(db, a=17, b=9, k=7, mark_published=True)
    data = _register_parent(client)
    token, pid = data['token'], data['user']['id']
    _grant_consents(client, token, pid)
    child_id = _create_child(client, token, '小禾', '3')
    switch = client.post('/v1/children/' + child_id + '/switch-session', headers=auth(token)).json()
    ct = switch['token']

    # 每日学习 session
    sid = client.post('/v1/sessions', json={'source': 'home'}, headers=auth(ct)).json()['session_id']
    act = client.post('/v1/sessions/' + sid + '/activities',
                      json={'kind': 'gate', 'lesson_id': spec['lesson_id'], 'revision': spec['revision']},
                      headers=auth(ct))
    assert act.status_code == 201, act.text
    aid = act.json()['activity']['activity_id']

    # 先想后看：answer-filtered 无答案字段；完整解答 403
    filtered = client.get('/v1/activities/' + aid + '/answer-filtered', headers=auth(ct)).json()
    for n in filtered['spec']['activity_graph']:
        if n.get('response'):
            assert n['response'].get('expected') is None
    locked = client.get('/v1/activities/' + aid + '/answer', headers=auth(ct))
    assert locked.status_code == 403

    # 尝试→提示阶梯（错误返回提示而非答案）→正确→证据落库
    wrong = client.post('/v1/activities/' + aid + '/attempts',
                        json={'step_id': 'find-complement', 'value': 99},
                        headers=auth(ct))
    assert wrong.json()['correct'] is False and wrong.json()['hint']
    answers = {
        'find-complement': str(10 - 9),
        'find-source': str(7),
        'find-sum': str(17 + 9),
        'transfer-practice': '33',
    }
    for step_id, value in answers.items():
        r = client.post('/v1/activities/' + aid + '/attempts',
                        json={'step_id': step_id, 'value': value},
                        headers=auth(ct))
        assert r.json()['correct'] is True, r.text

    # 积分发放（幂等：重复 grant 不重复发）
    from app.learning.models import EvidenceRecord as _ER

    factory = create_session_factory()
    with factory() as s:
        ev = s.query(_ER).filter_by(child_id=child_id).first()
        ev_id = ev.id if ev else None
    assert ev_id is not None
    points_service.create_rule_version(s, event_type='reward',
                                      points_independent=8, points_assisted=4,
                                      points_demonstrated=2)
    g1 = client.post('/v1/rewards/grant', json={'evidence_id': ev_id}, headers=auth(ct))
    g2 = client.post('/v1/rewards/grant', json={'evidence_id': ev_id}, headers=auth(ct))
    assert g1.status_code == 200 and g2.json()['idempotent'] is True

    # 足迹回看（易错跳转原课证据）
    fp = client.get('/v1/children/' + child_id + '/footprints?days=30', headers=auth(ct)).json()
    assert fp['items'] and fp['items'][0]['replay_ref'] == fp['items'][0]['activity_id']


# ---------------------------------------------------------------- 治理旅程


def test_governance_journey(client, db):
    spec = _publish_make_ten(db, a=18, b=9, k=8)
    admin = client.post('/v1/admin/login', json={'role': 'admin'}).json()['token']

    # 内核生成 → 待审核列表出现该 revision
    reviews = client.get('/v1/admin/reviews', headers=auth(admin)).json()['items']
    target = next((r for r in reviews if r['lesson_id'] == spec['lesson_id']), None)
    assert target is not None and target['status'] == 'pending'
    assert target['evidence']['math_verified'] is True  # make-ten 核验通过

    # 门禁来自生成期记录（前端自证无效）；缺"人工审核"证据阻断 → 补齐后发布
    assert target['evidence']['teaching_gate_ok'] is True
    blocked = client.post('/v1/admin/reviews/' + target['revision_id'] + '/publish',
                          json={"age_ok": True, "layout_ok": True,
                                "human_reviewed": False},
                          headers=auth(admin))
    assert blocked.status_code == 422
    published = client.post('/v1/admin/reviews/' + target['revision_id'] + '/publish',
                            json={"age_ok": True, "layout_ok": True,
                                  "human_reviewed": True},
                            headers=auth(admin))
    assert published.json()['status'] == 'published'

    # R4 来源透明：method_source=skill（make-ten 策略族）
    data = _register_parent(client)
    token, pid = data['token'], data['user']['id']
    _grant_consents(client, token, pid)
    child_id = _create_child(client, token, '小禾', '3')
    switch = client.post('/v1/children/' + child_id + '/switch-session', headers=auth(token)).json()
    ct = switch['token']
    sid = client.post('/v1/sessions', json={'source': 'home'}, headers=auth(ct)).json()['session_id']
    act = client.post('/v1/sessions/' + sid + '/activities',
                      json={'kind': 'gate', 'lesson_id': spec['lesson_id'], 'revision': spec['revision']},
                      headers=auth(ct)).json()
    assert act['activity']['method_source'] == 'skill'

    # 试卷模板审核门禁 + 结果治理（A4/A15）
    from app.questionbank import service as qb_service

    tpl = qb_service.create_exam_template(db, type_='stage', title='阶段测评')
    approve = client.post('/v1/admin/exam-templates/' + tpl['id'] + '/approve', headers=auth(admin))
    assert approve.json()['review_status'] == 'approved'
    results = client.get('/v1/admin/exam-results', headers=auth(admin)).json()
    assert results['governance_note'] and '不可把未完成或未核验结果写成能力结论' in results['governance_note']
