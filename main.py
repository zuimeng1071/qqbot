import os
import re
import botpy
from botpy import logging, Intents
from botpy.ext.cog_yaml import read
from botpy.message import GroupMessage, C2CMessage

# 导入服务
from service.user_service import UserService
from service.chat_service import ChatService

# 全局服务实例
user_service = UserService()
chatService = ChatService()

# 预编译正则（提升高频场景性能）
_CHECKIN_PATTERN = re.compile(r'\s*/签到\s*', re.IGNORECASE)
_QUERY_POINTS_PATTERN = re.compile(r'\s*/查询积分\s*', re.IGNORECASE)
_CLEAR_MEM_PATTERN = re.compile(r'\s*/清空用户画像\s*', re.IGNORECASE)
_QUERY_MEM_PATTERN = re.compile(r'\s*/查询用户画像\s*', re.IGNORECASE)
_SET_MEM_PATTERN = re.compile(r'\s*/设置用户画像\s*(.*)', re.IGNORECASE | re.DOTALL)
_VIEW_PROMPT_PATTERN = re.compile(r'\s*/查看系统提示词\s*', re.IGNORECASE)
_SET_PROMPT_PATTERN = re.compile(r'\s*/设置系统提示词\s*(.*)', re.IGNORECASE | re.DOTALL)
_HELP_PATTERN = re.compile(r'\s*(帮助|help|菜单|/帮助)\s*', re.IGNORECASE)

_log = logging.get_logger()
config = read(os.path.join(os.path.dirname(__file__), "config.yaml"))


class MyClient(botpy.Client):

    async def reply_group(self, group_openid: str, msg_id: str, content: str):
        await self.api.post_group_message(
            group_openid=group_openid,
            msg_id=msg_id,
            msg_type=0,
            content=content
        )

    async def reply_c2c(self, openid: str, msg_id: str, content: str):
        await self.api.post_c2c_message(
            openid=openid,
            msg_id=msg_id,
            msg_type=0,
            content=content
        )

    async def on_ready(self):
        _log.info(f"「{self.robot.name}」已上线！")

    async def _handle_user_message(self, gid: str, uid: str, raw_msg: str, reply_func):
        """
        统一处理用户指令（群聊 or 私聊）
        :param gid: group id（私聊时为 "PRIVATE"）
        :param uid: user id
        :param raw_msg: 原始消息内容
        :param reply_func: 异步回复函数，如 lambda r: self.reply_group(...)
        """
        msg = raw_msg.strip()

        try:
            # 签到
            if _CHECKIN_PATTERN.fullmatch(msg):
                reply = await user_service.handle_checkin(gid, uid)  # TODO: 若 service 异步化，改为 await
                await reply_func(reply)
                return

            # 查询积分
            elif _QUERY_POINTS_PATTERN.fullmatch(msg):
                reply = await user_service.handle_query_points(gid, uid)
                await reply_func(reply)
                return

            # 清空用户画像
            elif _CLEAR_MEM_PATTERN.fullmatch(msg):
                reply = await user_service.clearUserLongMemory(gid, uid)
                await reply_func(reply)
                return

            # 查询用户画像
            elif _QUERY_MEM_PATTERN.fullmatch(msg):
                reply = await user_service.queryUserLongMemory(gid, uid)
                await reply_func(reply)
                return

            # 设置用户画像
            elif match := _SET_MEM_PATTERN.fullmatch(msg):
                content_param = match.group(1).strip()
                if not content_param:
                    reply = "请提供要设置的用户画像内容，例如：\n/设置用户画像 我喜欢科幻电影，讨厌香菜"
                else:
                    reply = await user_service.updateUserLongMemory(gid, uid, content_param)
                await reply_func(reply)
                return

            # 查看系统提示词
            elif _VIEW_PROMPT_PATTERN.fullmatch(msg):
                reply = await user_service.getSystemPromptForUser(gid, uid)
                await reply_func(reply)
                return

            # 设置系统提示词
            elif match := _SET_PROMPT_PATTERN.fullmatch(msg):
                content_param = match.group(1).strip()
                if not content_param:
                    reply = "请提供要设置的系统提示词内容，例如：\n/设置系统提示词 你是一个冷静的学术助手，禁止使用颜文字"
                else:
                    reply = await user_service.updateUserSystemPrompt(gid, uid, content_param)
                await reply_func(reply)
                return

            # 帮助
            elif _HELP_PATTERN.fullmatch(msg):
                reply = await user_service.handle_help()
                await reply_func(reply)
                return

            # AI 回复
            else:
                ai_reply = await chatService.chat(groupId=gid, userId=uid, message=raw_msg)
                await reply_func(ai_reply)

        except Exception as e:
            _log.error(f"处理用户消息出错 (gid={gid}, uid={uid}): {e}", exc_info=True)
            await reply_func("抱歉，系统出错了，请联系管理员：2450907441。")

    async def on_group_at_message_create(self, message: GroupMessage):
        gid = message.group_openid
        uid = message.author.member_openid
        content = message.content or ""
        _log.info(f"处理群{gid}用户{uid}的消息：{content}")

        await self._handle_user_message(
            gid, uid, content,
            lambda r: self.reply_group(gid, message.id, r)
        )

    async def on_c2c_message_create(self, message: C2CMessage):
        uid = message.author.user_openid
        content = message.content or ""
        _log.info(f"处理私聊用户{uid}的消息：{content}")

        await self._handle_user_message(
            "PRIVATE", uid, content,
            lambda r: self.reply_c2c(uid, message.id, r)
        )


if __name__ == "__main__":
    intents = Intents(public_messages=True)
    client = MyClient(intents=intents)
    client.run(appid=config["appid"], secret=config["secret"])