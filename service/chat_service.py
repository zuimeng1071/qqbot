# service/chat_service.py

import asyncio
import redis.asyncio as redis
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.redis import AsyncRedisSaver

from service.agentUtils.saveMemory import SaveMemory
from service.agentUtils.tools import (
    queryUserLongMemory,
    queryGroupLongMemory,
    doCheckin,
    showHelp,
    queryUserPoints,
    addUserPoints,
    deductUserPoints,
)
from service.user_service import UserService
from utils.constant import Constant


class ChatService:
    def __init__(self):
        # 延迟初始化 async 组件
        self._agent = None
        self._save_memory = None
        self._initialized = False

    async def _initialize(self):
        """在 asyncio loop 中安全初始化"""
        if self._initialized:
            return

        # 1. 创建 Redis 客户端并初始化 Checkpointer
        redis_client = redis.from_url(Constant.REDIS_CONN_STRING)
        checkpointer = AsyncRedisSaver(redis_client=redis_client)

        # 2. 初始化模型
        chat_llm = ChatOpenAI(
            model=Constant.CHAT_MODEL_NAME,
            api_key=Constant.DASHSCOPE_API_KEY,
            base_url=Constant.DASHSCOPE_BASE_URL,
            temperature=Constant.CHAT_TEMPERATURE,
            max_tokens=Constant.CHAT_MAX_TOKENS,
        )

        summary_llm = ChatOpenAI(
            model=Constant.SUMMARY_MODEL_NAME,
            api_key=Constant.DASHSCOPE_API_KEY,
            base_url=Constant.DASHSCOPE_BASE_URL,
            temperature=Constant.SUMMARY_TEMPERATURE,
            max_tokens=Constant.SUMMARY_MAX_TOKENS,
        )

        # 3. 注册工具
        tools = [
            queryUserLongMemory,
            queryGroupLongMemory,
            queryUserPoints,
            addUserPoints,
            deductUserPoints,
            doCheckin,
            showHelp,
        ]

        # 4. 创建智能体（✅ 保留你的完整逻辑）
        self._agent = create_agent(
            model=chat_llm,
            tools=tools,
            middleware=[
                SummarizationMiddleware(
                    model=summary_llm,
                    trigger=[("tokens", Constant.SUMMARY_TOKENS_THRESHOLD),
                             ("messages", Constant.SUMMARY_MESSAGES_THRESHOLD)],
                    keep=("messages", Constant.SUMMARY_KEEP_MESSAGES),
                )
            ],
            checkpointer=checkpointer,
        )

        self._save_memory = SaveMemory()
        self._initialized = True

    async def chat(self, groupId: str = None, userId: str = None, message: str = None) -> str:
        if not userId:
            raise ValueError("userId is required")

        await self._initialize()

        thread_id = f"{groupId or 'private'}_{userId}"

        # 获取系统提示（保持你的调用方式）
        actual_system_prompt = await UserService.getSystemPromptForUser(groupId or "private", userId)
        actual_system_prompt += "\n\n" + Constant.CHAT_RULES_PROMPT

        # 注入上下文（完全保留你的逻辑）
        if groupId:
            context_prefix = f"[群组ID:{groupId}|用户ID:{userId}] "
        else:
            context_prefix = f"[私聊|用户ID:{userId}] "

        contextualized_message = context_prefix + message.strip()

        messages = [
            SystemMessage(content=actual_system_prompt),
            HumanMessage(content=message.strip() + contextualized_message)  # 按你写的保留
        ]

        # 异步调用智能体
        response = await self._agent.ainvoke(
            {"messages": messages},
            config=RunnableConfig(configurable={"thread_id": thread_id}),
        )

        assistant_reply = response["messages"][-1].content

        # 保存记忆（假设 save 是 async）
        await self._save_memory.save(
            groupId=groupId,
            userId=userId,
            userMessage=message.strip(),
            agentMessage=assistant_reply.strip(),
        )

        return assistant_reply


# ======================
# 主程序：保持你原有的交互风格，但内部异步运行
# ======================
if __name__ == "__main__":
    import asyncio

    # 模拟同步输入（不阻塞 event loop）
    async def async_input(prompt: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, prompt)

    async def run_chat():
        chat = ChatService()
        while True:
            try:
                groupId = await async_input("群组ID（留空为私聊）：") or None
                userId = await async_input("用户ID：")
                message = await async_input("用户消息：")
                if message.lower() in ["exit", "quit", "bye"]:
                    break
                reply = await chat.chat(groupId=groupId, userId=userId, message=message)
                print("助手回复：", reply)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print("❌ 错误:", e)

    # 启动异步主循环
    asyncio.run(run_chat())