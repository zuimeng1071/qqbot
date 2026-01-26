# service/agentUtils/tools.py

import redis.asyncio as redis  # 使用异步 Redis 客户端
from botpy import logging
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from mapper.database import Database
from service.user_service import UserService
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


def _get_group_long_key(group_id: str) -> str:
    return f"{Constant.REDIS_GROUP_MEMORY_KEY}:{group_id}"


@tool
async def queryUserLongMemory(groupId: str, userId: str) -> str:
    """
    查询当前用户的长期记忆画像。包含兴趣、偏好、背景等信息。
    仅在需要个性化回复时调用。
    参数：
    groupId: 群组 ID
    userId: 用户 ID
    返回：
    长期记忆
    """
    try:
        _log.info(f"查询用户 {userId} 的长期记忆")
        key = _get_user_long_key(groupId, userId)
        memory = await _redis_client.get(key)

        if memory:
            return memory.decode("utf-8")
        else:
            return "暂无关于该用户的长期记忆。"
    except Exception as e:
        error_msg = f"查询用户长期记忆时出错：{str(e)}"
        _log.error(error_msg)
        return "查询用户长期记忆时发生错误。"


@tool
async def queryGroupLongMemory(groupId: str) -> str:
    """
    查询当前群组的长期记忆画像。包含群主题、成员偏好、历史事件等。
    仅在群聊中且需要上下文感知时调用。
    参数：
      - groupId: 当前群组ID
    返回值：
      - 群组的长期记忆画像字符串，若无则返回提示信息。
    """
    try:
        _log.info(f"查询群组 {groupId} 的长期记忆")
        if not groupId:
            return "当前不在群聊环境中，无法查询群组记忆。"

        key = _get_group_long_key(groupId)
        memory = await _redis_client.get(key)

        if memory:
            return memory.decode("utf-8")
        else:
            return "暂无关于该群组的长期记忆。"
    except Exception as e:
        error_msg = f"查询群组长期记忆时出错：{str(e)}"
        _log.error(error_msg)
        return "查询群组长期记忆时发生错误。"


@tool
async def queryUserPoints(groupId: str, userId: str) -> str:
    """
    查询用户在指定群组中的当前积分。

    参数：
      - groupId (str): 群组ID
      - userId (str): 用户ID
    返回值：
        - 用户当前积分的字符串表示，若查询失败则返回错误提示。
    """
    try:
        _log.info(f"查询群{groupId}中用户 {userId} 的积分")
        db = Database()
        current_points = await db.get_user_points(userId, groupId)

        if current_points is None:
            await db.init_user_points(userId, groupId)
            current_points = 0

        return f"用户当前积分：{current_points}"
    except Exception as e:
        error_msg = f"查询用户积分时出错：{str(e)}"
        _log.error(error_msg)
        return "查询用户积分时发生错误。"


@tool
async def addUserPoints(groupId: str, userId: str, amount: int, reason: str = "") -> str:
    """
    为用户增加积分。

    参数：
      - groupId (str): 群组ID
      - userId (str): 用户ID
      - amount (int): 要增加的积分数（必须 ≥ 0）
      - reason (str): 原因（可选）
    返回值：
      - 增加积分后的提示信息字符串。
    """
    try:
        if amount < 0:
            return "积分数量不能为负数。"
        elif amount > 9999:
            return "单次增加积分过多，请合理控制在9999以内。"

        _log.info(f"为群{groupId}用户 {userId} 增加 {amount} 积分，原因：{reason}")

        db = Database()
        current_points = await db.get_user_points(userId, groupId)

        if current_points is None:
            await db.init_user_points(userId, groupId)
            current_points = 0

        success = await db.add_user_points(userId, groupId, amount)
        if not success:
            return "积分操作失败，请稍后再试。"

        new_points = await db.get_user_points(userId, groupId) or 0

        msg = f"成功增加{amount}积分"
        if reason:
            msg += f"（原因：{reason}）"
        msg += f"\n当前积分：{new_points}"
        return msg
    except Exception as e:
        error_msg = f"增加用户积分时出错：{str(e)}"
        _log.error(error_msg)
        return "增加用户积分时发生错误。"


@tool
async def deductUserPoints(groupId: str, userId: str, amount: int, reason: str = "") -> str:
    """
    从用户扣除积分（需确保余额充足）。

    参数：
      - groupId (str): 群组ID
      - userId (str): 用户ID
      - amount (int): 要扣除的积分数（必须 ≥ 0）
      - reason (str): 原因（可选）
    返回值：
      - 扣除积分后的提示信息字符串。
    """
    try:
        if amount < 0:
            return "积分数量不能为负数。"
        elif amount > 9999:
            return "单次扣除积分过多，请合理控制在9999以内。"

        _log.info(f"从群{groupId}用户 {userId} 扣除 {amount} 积分，原因：{reason}")

        db = Database()
        current_points = await db.get_user_points(userId, groupId)

        if current_points is None:
            await db.init_user_points(userId, groupId)
            current_points = 0

        if current_points < amount:
            return f"积分不足！当前积分：{current_points}，需扣除：{amount}"

        success = await db.add_user_points(userId, groupId, -amount)
        if not success:
            return "积分操作失败，请稍后再试。"

        new_points = await db.get_user_points(userId, groupId) or 0

        msg = f"成功扣除{amount}积分"
        if reason:
            msg += f"（原因：{reason}）"
        msg += f"\n当前积分：{new_points}"
        return msg
    except Exception as e:
        error_msg = f"扣除用户积分时出错：{str(e)}"
        _log.error(error_msg)
        return "扣除用户积分时发生错误。"


@tool
async def doCheckin(groupId: str, userId: str) -> str:
    """
    执行用户签到操作。
    每天只能签到一次，连续签到可获得额外积分奖励。

    参数：
      - groupId: 群组ID（私聊时传 "private"）
      - userId: 用户ID
    返回值：
        - 签到结果字符串，包含奖励信息或错误提示。
    """
    _log.info(f"用户 {userId} 在群 {groupId} 请求签到")
    try:
        service = UserService()
        result = await service.handle_checkin(group_id=groupId, user_id=userId)
        return result
    except Exception as e:
        error_msg = f"签到工具执行出错: {e}"
        _log.error(error_msg)
        return "签到系统异常，请稍后再试～ (；′⌒`)"


@tool
async def showHelp() -> str:
    """显示帮助信息。"""
    _log.info("用户请求帮助信息")
    try:
        return Constant.HELP
    except Exception as e:
        _log.error(f"帮助工具执行出错: {e}")
        return "帮助信息加载失败，请联系管理员。"
