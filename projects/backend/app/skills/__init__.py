"""Teaching Skill 模块：Claude-style skill 包加载与意图驱动检索。

Skill 是「特殊教学方法」的内容资产，不是全局规范容器；通用教学规范见
app.policy。检索器只接受 TeachingIntent / 查询词，不接受原始用户输入。
"""

from app.skills.loader import load_all_skills, load_skill_pack
from app.skills.model import TeachingSkill
from app.skills.retriever import SkillRetriever

__all__ = ["TeachingSkill", "load_all_skills", "load_skill_pack", "SkillRetriever"]
