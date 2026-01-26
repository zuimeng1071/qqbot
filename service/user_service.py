# service/user_service.py
from datetime import date, timedelta
from botpy import logging
import redis.asyncio as redis
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
import asyncio

from mapper.database import Database
from utils.constant import Constant

# 初始化异步 Redis 客户端
_redis_client = redis.from_url(Constant.REDIS_CONN_STRING)

_update_llm = ChatOpenAI(
    model=Constant.SUMMARY_MODEL_NAME,
    api_key=Constant.DASHSCOPE_API_KEY,
    base_url=Constant.DASHSCOPE_BASE_URL,
    temperature=Constant.SUMMARY_TEMPERATURE,
    max_tokens=Constant.SUMMARY_MAX_TOKENS,
)

_log = logging.get_logger()


def _get_user_long_key(group_id: str, user_id: str) -> str:
    return f"{Constant.REDIS_USER_MEMORY_KEY}:{group_id}:{user_id}"


class UserService:
    def __init__(self):
        self.db = Database()

    async def handle_checkin(self, group_id: str, user_id: str) -> str:
        today = date.today()
        yesterday = today - timedelta(days=1)

        # 查询已有记录（异步）
        record = await self.db.get_checkin_record(user_id, group_id)

        if record and record['last_checkin_date'] == today:
            return "你今天已经签到过了！"

        if record is None:
            total_days = 1
            streak_days = 1
        else:
            last_date = record['last_checkin_date']
            total_days = record['total_days'] + 1

            if last_date == yesterday:
                streak_days = record['streak_days'] + 1
            elif last_date < yesterday:
                streak_days = 1
            else:
                streak_days = record['streak_days']

        # 更新数据库（异步）
        success = await self.db.add_or_update_checkin(
            user_id=user_id,
            group_id=group_id,
            checkin_date=today,
            total_days=total_days,
            streak_days=streak_days
        )
        if not success:
            return "签到失败，请稍后再试。"

        # 计算积分
        bonus = 0
        points_delta = Constant.CHECKIN_POINTS

        for days, extra in Constant.STREAK_BONUS.items():
            if streak_days == days:
                bonus = extra
                points_delta += bonus
                break

        await self.db.create_or_update_user_status(user_id, group_id, is_reusable=True)
        await self.db.add_user_points(user_id, group_id, points_delta)

        points = await self.db.get_user_points(user_id, group_id) or 0

        reply = f"签到成功！+{Constant.CHECKIN_POINTS} 积分"
        if bonus > 0:
            reply += f"\n连续签到 {streak_days} 天！额外奖励 +{bonus} 积分"
        reply += f"\n当前积分：{points}"
        reply += f"\n累计签到：{total_days} 天"
        reply += f"\n连续签到：{streak_days} 天"

        return reply

    async def handle_query_points(self, group_id: str, user_id: str) -> str:
        points = await self.db.get_user_points(user_id, group_id)
        record = await self.db.get_checkin_record(user_id, group_id)

        if points is None and record is None:
            return "你还没有签到记录。发送“签到”开始吧！"

        lines = []
        if points is not None:
            lines.append(f"当前积分：{points}")
        if record:
            lines.append(f"累计签到：{record['total_days']} 天")
            lines.append(f"连续签到：{record['streak_days']} 天")
            lines.append(f"上次签到：{record['last_checkin_date']}")

        return "\n".join(lines) if lines else "暂无数据"

    @staticmethod
    async def queryUserLongMemory(groupId: str, userId: str) -> str:
        _log.info(f"查询用户 {userId} 的长期记忆")
        key = _get_user_long_key(groupId, userId)
        memory = await _redis_client.get(key)

        if memory:
            return memory.decode("utf-8")
        else:
            return "暂无关于该用户的长期记忆。"

    @staticmethod
    async def clearUserLongMemory(groupId: str, userId: str) -> str:
        _log.info(f"清除用户 {userId} 在群组 {groupId} 的长期记忆")
        key = _get_user_long_key(groupId, userId)
        deleted = await _redis_client.delete(key)
        if deleted:
            return f"已成功清除用户 {userId} 在上下文 {groupId} 中的长期记忆。"
        else:
            return f"未找到用户 {userId} 在上下文 {groupId} 的长期记忆，无需清除。"

    @staticmethod
    async def updateUserLongMemory(groupId: str, userId: str, update_instruction: str) -> str:
        key = _get_user_long_key(groupId, userId)
        current_memory = await _redis_client.get(key)
        current_memory_str = current_memory.decode("utf-8") if current_memory else ""

        if current_memory_str:
            prompt = (
                "你是一个记忆管理助手。以下是某用户的当前画像：\n"
                f"--- 当前画像 ---\n{current_memory_str}\n"
                "--- 结束 ---\n\n"
                "用户提供了以下更新指令：\n"
                f"「{update_instruction}」\n\n"
                "请结合当前画像和用户的新指令，生成一个**更新后的、连贯的用户画像**。\n"
                "保留未被否定的旧信息，融入新内容，删除明显过时或被纠正的信息。\n"
                "输出应简洁、结构清晰，不超过500字。不要包含解释或问候语。"
            )
        else:
            prompt = (
                "你是一个记忆管理助手。用户提供了以下关于自己的新信息：\n"
                f"「{update_instruction}」\n\n"
                "请基于此生成一个初步的用户画像，包括兴趣、偏好或背景等。\n"
                "输出应简洁、结构清晰，不超过500字。不要包含解释或问候语。"
            )

        try:
            response = await _update_llm.ainvoke([HumanMessage(content=prompt)])  # ✅ ainvoke
            new_profile = response.content.strip()

            await _redis_client.set(key, new_profile)
            return f"用户画像已更新。新画像：{new_profile}"
        except Exception as e:
            _log.error(f"更新用户画像失败 - group:{groupId} user:{userId}, error: {e}")
            return "更新失败，请稍后再试。"

    @staticmethod
    async def getSystemPromptForUser(groupId: str, userId: str) -> str:
        cache_key = f"{Constant.REDIS_USER_SYSTEM_PROMPT_KEY}:{groupId}:{userId}"
        cached = await _redis_client.get(cache_key)
        if cached:
            return cached.decode("utf-8")

        db = Database()
        prompt_from_db = await db.get_user_system_prompt(userId, groupId)
        if prompt_from_db:
            await _redis_client.setex(cache_key, 3600, prompt_from_db)
            return prompt_from_db
        else:
            return Constant.CHAT_PERSONA_PROMPT

    @staticmethod
    async def updateUserSystemPrompt(groupId: str, userId: str, prompt_instruction: str) -> str:
        cost = Constant.USER_SYSTEM_PROMPT_COST
        db = Database()

        current_points = await db.get_user_points(userId, groupId)
        if current_points is None or current_points < cost:
            return f"积分不足！设置系统提示词需要 {cost} 积分。"

        if not await db.add_user_points(userId, groupId, -cost):
            return "扣除积分失败，请稍后再试。"

        success = await db.set_user_system_prompt(userId, groupId, prompt_instruction)
        if not success:
            return f"保存失败，但已扣除 {cost} 积分（请联系管理员）。"

        cache_key = f"{Constant.REDIS_USER_SYSTEM_PROMPT_KEY}:{groupId}:{userId}"
        await _redis_client.setex(cache_key, 3600, prompt_instruction)

        return f"个性化系统提示词已设置成功！已扣除 {cost} 积分。"

    @staticmethod
    async def handle_help() -> str:
        """帮助信息是静态的，可保持同步，但为统一接口也声明为 async"""
        return Constant.HELP