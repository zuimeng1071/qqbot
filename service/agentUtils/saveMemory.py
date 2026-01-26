# service/agentUtils/saveMemory.py
import json
import asyncio
from typing import List, Dict, Any
from botpy import logging

from redis.asyncio import Redis
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from utils.constant import Constant

_log = logging.get_logger()


def _get_user_temp_key(group_id: str, user_id: str) -> str:
    return f"{Constant.REDIS_TEMP_USER_MEMORY_KEY}:{group_id}:{user_id}"


def _get_group_temp_key(group_id: str) -> str:
    return f"{Constant.REDIS_TEMP_GROUP_MEMORY_KEY}:{group_id}"


class SaveMemory:
    """
    管理用户和群组的临时记忆与长期记忆（摘要）—— 异步版本
    """

    def __init__(self):
        self.summary_llm = ChatOpenAI(
            model=Constant.SUMMARY_MODEL_NAME,
            api_key=Constant.DASHSCOPE_API_KEY,
            base_url=Constant.DASHSCOPE_BASE_URL,
            temperature=Constant.SUMMARY_TEMPERATURE,
            max_tokens=Constant.SUMMARY_MAX_TOKENS,
        )
        self.redis_client: Redis = Redis.from_url(Constant.REDIS_CONN_STRING, decode_responses=True)

    @staticmethod
    def _get_user_long_key(group_id: str, user_id: str) -> str:
        return f"{Constant.REDIS_USER_MEMORY_KEY}:{group_id}:{user_id}"

    @staticmethod
    def _get_group_long_key(group_id: str) -> str:
        return f"{Constant.REDIS_GROUP_MEMORY_KEY}:{group_id}"

    @staticmethod
    def _messages_to_text(messages: List[Dict[str, Any]]) -> str:
        """将消息列表转为纯文本"""
        lines = []
        for msg in messages:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _summarize(self, conversation: str, previous_summary: str = "", is_group: bool = False) -> str:
        """调用 LLM 生成增量式摘要（异步）"""
        context_type = "群聊" if is_group else "私聊"

        if previous_summary:
            prompt = (
                f"你是一个记忆助手。以下是关于某个{context_type}的历史画像：\n"
                f"--- 历史画像 ---\n{previous_summary}\n"
                f"--- 结束 ---\n\n"
                f"现在新增了以下对话内容：\n{conversation}\n\n"
                f"请结合历史画像和新增对话，生成一个**更新后的、更全面的{context_type}画像**。\n"
                f"保留重要历史信息，融入新发现，删除过时内容。不超过500字。"
            )
        else:
            prompt = (
                f"你是一个记忆助手。请基于以下{context_type}的对话内容，生成一个详细的{context_type}画像。"
                f"包括但不限于兴趣、偏好、重要背景信息等，不要限制于对话中直接提及的信息，但确保所有推断都是合理的。不超过500字\n\n"
                f"对话内容：\n{conversation}"
            )

        response = await self.summary_llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()

    async def userMessageSummary(self, group_id: str, user_id: str, messages: List[Dict[str, Any]]):
        """对用户临时记忆进行总结并存入长期记忆（支持增量更新）"""
        _log.info(f"开始处理群{group_id}, 用户 {user_id} 的对话")
        if not messages:
            return

        # 清空临时记忆
        temp_key = _get_user_temp_key(group_id, user_id)
        await self.redis_client.delete(temp_key)

        # 读取已有长期记忆（如果有）
        long_key = self._get_user_long_key(group_id, user_id)
        previous_summary = await self.redis_client.get(long_key)  # decode_responses=True → str

        # 构造新对话文本
        conversation = self._messages_to_text(messages)

        # 生成**增量式**摘要
        summary = await self._summarize(conversation, previous_summary=previous_summary or "", is_group=False)

        # 保存新摘要
        await self.redis_client.set(long_key, summary)
        _log.info(f"已更新群{group_id}, 用户 {user_id} 的长期记忆摘要")

    async def groupMessageSummary(self, group_id: str, messages: List[Dict[str, Any]]):
        """对群组临时记忆进行总结并存入长期记忆（支持增量更新）"""
        _log.info(f"开始处理群组 {group_id} 的对话")
        if not messages:
            return

        # 清空临时记忆
        temp_key = _get_group_temp_key(group_id)
        await self.redis_client.delete(temp_key)

        # 读取已有长期记忆
        long_key = self._get_group_long_key(group_id)
        previous_summary = await self.redis_client.get(long_key)

        # 构造新对话文本
        conversation = self._messages_to_text(messages)

        # 生成增量摘要
        summary = await self._summarize(conversation, previous_summary=previous_summary or "", is_group=True)

        # 保存
        await self.redis_client.set(long_key, summary)
        _log.info(f"已更新群组 {group_id} 的长期记忆摘要")

    async def save(self, groupId: str = None, userId: str = None, userMessage: str = "", agentMessage: str = ""):
        """
        保存一轮对话（用户 + 助手）到临时记忆，并自动判断是否触发总结。
        触发总结时使用 asyncio.create_task 执行，避免阻塞。
        """
        if not userId:
            raise ValueError("userId is required")

        # 构造本轮对话
        new_messages = []
        if userMessage.strip():
            new_messages.append({"role": "user", "content": userMessage.strip()})
        if agentMessage.strip():
            new_messages.append({"role": "assistant", "content": agentMessage.strip()})

        if not new_messages:
            return

        # === 处理用户维度记忆 ===
        user_temp_key = _get_user_temp_key(groupId, userId)
        user_raw = await self.redis_client.get(user_temp_key)
        user_messages = json.loads(user_raw) if user_raw else []
        user_messages.extend(new_messages)

        if len(user_messages) >= Constant.MAX_USER_MESSAGE_COUNT:
            # 👇 关键：使用 asyncio.create_task 异步执行总结
            asyncio.create_task(self.userMessageSummary(groupId, userId, user_messages.copy()))
        else:
            await self.redis_client.set(user_temp_key, json.dumps(user_messages, ensure_ascii=False))

        # === 处理群组维度记忆（如果 groupId 存在）===
        if groupId:
            group_temp_key = _get_group_temp_key(groupId)
            group_raw = await self.redis_client.get(group_temp_key)
            group_messages = json.loads(group_raw) if group_raw else []
            group_messages.extend(new_messages)

            if len(group_messages) >= Constant.MAX_GROUP_MESSAGE_COUNT:
                asyncio.create_task(self.groupMessageSummary(groupId, group_messages.copy()))
            else:
                await self.redis_client.set(group_temp_key, json.dumps(group_messages, ensure_ascii=False))


# 示例主函数（异步）
if __name__ == "__main__":
    async def main():
        save_memory = SaveMemory()
        try:
            for i in range(10):
                await save_memory.save(
                    groupId=f"abc{i%2}",
                    userId=f"123{i%5}",
                    userMessage=f"用户消息 {i}",
                    agentMessage=f"助手回复 {i}"
                )
                _log.info(f"已保存第 {i} 条对话")
                await asyncio.sleep(1)
            await asyncio.sleep(5)  # 等待后台任务完成
        finally:
            await save_memory.redis_client.close()

    asyncio.run(main())