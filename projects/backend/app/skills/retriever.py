"""Teaching Skill 检索器：只接受 TeachingIntent，不接受原始用户输入。

检索结果只是候选教学方法材料；是否使用、如何使用由 planner 结合教学
目标决定，检索器不直接决定课程内容。
"""

from app.intent.contract import TeachingIntent
from app.skills.model import TeachingSkill


class SkillRetriever:
    """基于意图候选查询词的关键词检索（可替换为向量检索实现）。"""

    def __init__(self, skills: list[TeachingSkill]) -> None:
        self._skills = skills

    def retrieve(self, intent: TeachingIntent) -> list[TeachingSkill]:
        """按 TeachingIntent 检索候选 skill；无命中返回空列表。

        匹配范围：name / description / SKILL.md 正文。name 与 description
        按 Claude 规范常用英文，正文为中文教学方法，两者都参与匹配。
        """
        queries = intent.candidate_skill_queries
        if not queries:
            return []
        hits: list[TeachingSkill] = []
        for skill in self._skills:
            haystack = f"{skill.name} {skill.description} {skill.content}"
            if any(q in haystack for q in queries):
                hits.append(skill)
        return hits

    def all(self) -> list[TeachingSkill]:
        return list(self._skills)
