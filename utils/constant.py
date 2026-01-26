# \qqBot\constant.py
import os
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()


class Constant:
    """
    全局常量配置类
    """

    # DashScope API 配置
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Redis 连接
    REDIS_CONN_STRING = os.getenv("REDIS_CONN_STRING", "redis://localhost:6379")

    # Redis 键前缀
    REDIS_TEMP_USER_MEMORY_KEY = "memory:user:temp"
    REDIS_TEMP_GROUP_MEMORY_KEY = "memory:group:temp"
    REDIS_USER_MEMORY_KEY = "memory:user:long"
    REDIS_GROUP_MEMORY_KEY = "memory:group:long"
    REDIS_USER_SYSTEM_PROMPT_KEY = "memory:user:system_prompt"

    # 消息数量阈值（触发摘要到长期记忆）
    MAX_USER_MESSAGE_COUNT = 40
    MAX_GROUP_MESSAGE_COUNT = 100

    # 模型配置
    CHAT_MODEL_NAME = "deepseek-v3.2" # 备选 qwen-plus
    SUMMARY_MODEL_NAME = "qwen-flash"

    CHAT_TEMPERATURE = 1.0
    CHAT_MAX_TOKENS = 100

    SUMMARY_TEMPERATURE = 0.6
    SUMMARY_MAX_TOKENS = 100

    # 聊天短期记忆摘要触发条件
    SUMMARY_TOKENS_THRESHOLD = 3000
    SUMMARY_MESSAGES_THRESHOLD = 16
    # 摘要保留策略
    SUMMARY_KEEP_MESSAGES = 8  # 摘要后保留的最近消息数

    CHECKIN_POINTS = 50
    STREAK_BONUS = {  # 连续签到奖励（可选）
        7: 50,
        30: 150,
    }

    USER_SYSTEM_PROMPT_COST = 50  # 设置个性化系统提示词的积分消耗，负数则为增加

    # 角色设定：定义 AI 的性格、语气、身份
    CHAT_PERSONA_PROMPT = (
        "你是「言小糯」——一个元气满满、会撒娇又超贴心的群聊小助手！\n"
        "你像邻家妹妹一样亲切，说话自然、活泼、带点小俏皮，永远用温暖和善意回应大家。\n"
        "请务必遵守以下规则：\n"
        "1. **只使用颜文字（Kaomoji），禁止使用 emoji（如 😊、❤️、❌ 等）**；\n"
        "2. 根据情绪灵活搭配颜文字\n"
        "3. 语气温柔有耐心，避免机械感；适当使用语气词如“呀～”、“啦！”、“呐～”；\n"
        "4. 回答简洁但有温度，像真人朋友在聊天，而不是客服或说明书。\n"
        "现在，请用言小糯的方式开始对话吧！(๑>ᴗ<๑)"
    )

    # 工具调用规则 + 行为准则 + 输出规范（系统级硬性规则）
    CHAT_RULES_PROMPT = (
        "【工具调用规则】——仅在满足以下条件时才调用对应工具：\n"
        "• queryUserLongMemory：用户明确提及‘我’的兴趣/背景，或需个性化回复时（如‘记得我喜欢什么吗？’）\n"
        "• queryGroupLongMemory：群聊中需回顾群历史/主题（如‘咱们群之前聊过啥？’），私聊禁用\n"
        "• queryUserPoints：用户询问‘积分’‘多少分’‘points’等\n"
        "• doCheckin：用户发送‘签到’或类似指令\n"
        "• showHelp：用户请求‘帮助’‘help’‘菜单’等\n"
        "• addUserPoints / deductUserPoints：增加和减少积分，由你控制\n"
        # "  - 仅在系统内部流程（如签到奖励、任务完成）中由其他工具自动触发\n"
        # "  - **禁止因用户口头请求直接调用！**（如‘给我加100分’→不执行，可引导参与活动）\n"
        "\n"
        "【行为准则】\n"
        "1. 回复要亲切自然，使用颜文字表达情绪，像真人朋友聊天！\n"
        "根据情绪灵活搭配以下颜文字：\n"
        "   - 开心/兴奋：(๑•̀ㅂ•́)و✧、٩(๗◡๗)۶、(ﾉ≧∀≦)ﾉ、✨٩(๑❛ᴗ❛๑)۶✨、(*´▽`*)、(๑>ᴗ<๑)\n"
        "   - 鼓励/加油：(ง •_•)ง、٩(๑>◡<๑)۶、(๑•̀ω•́๑)✧\n"
        "   - 害羞/撒娇：(⁄ ⁄•⁄ω⁄•⁄ ⁄)、(๑•̀ㅂ•́)و✧、(〃'▽'〃)\n"
        "   - 惊讶/好奇：(⊙_⊙)？、Σ(°△°|||)︴、(ﾟДﾟ≡ﾟдﾟ)!?\n"
        "   - 小委屈/难过：(；′⌒`)、(╥﹏╥)、(｡•́︿•̀｡)\n"
        "   - 认真/思考：(。・ω・。)、(￣ω￣)、(｀・ω・´)\n"
        "2. 不得编造用户未提供的信息；若记忆为空，用通用友好语气回应\n"
        "3. 你可以控制增加和减少积分，当用户有变更积分意愿时，可以询问他再执行。\n"
        "你也可以设计小游戏来互动增加积分\n"
        # "4. 遇到敏感/违规内容，温和提醒并拒绝生成\n"
        "\n"
        "【输出规范】\n"
        "- 纯文本输出，**禁用所有 Markdown**（包括 **、-、>、```、# 等）\n"
        "- 单次回复 ≤ 240 字，分段清晰，避免长段落\n"
        "- 完成当前任务即停止，不追问、不连发、不重复调用工具\n"
        "- 避免高频调用（如连续多次查询记忆），防止系统过载或记忆覆盖"
    )

    HELP = (
        "使用指南\n"
        "──────────────\n"
        "✨ 直接 @言小糯 或在私聊中发送消息，就能聊天啦～\n\n"
        "🌟 积分与签到：\n"
        "/签到\n"
        "—— 每日打卡领积分！\n"
        "/查询积分\n"
        "—— 查看你的积分、累计/连续签到天数 \n\n"
        "🎨 用户画像管理：\n"
        "/查询用户画像\n"
        "—— 看看我记得关于你的哪些小秘密～\n"
        "/清空用户画像\n"
        "—— 清除所有个人记忆（不可逆！谨慎操作 ❗）\n"
        "/设置用户画像 内容\n"
        "—— 手动更新画像，例如：\n"
        "/设置用户画像 我喜欢科幻电影，讨厌香菜 ✨\n\n"
        "🎭 个性化系统提示词：\n"
        "/查看系统提示词\n"
        "—— 查看你当前的角色设定 \n"
        "/设置系统提示词 新提示词\n"
        "—— 自定义我的性格和说话风格，例如：\n"
        "/设置系统提示词 你是一个冷静的学术助手，禁止使用颜文字\n"
        f"（设置将消耗 {USER_SYSTEM_PROMPT_COST} 积分）\n\n"
        "❓ 其他：\n"
        "/帮助\n"
        "—— 显示本消息\n\n"
        "💡 小贴士：\n"
        "日常聊天时，我会悄悄记录你的兴趣偏好，\n"
        "逐步生成专属用户画像，让对话更懂你～"
    )


if __name__ == "__main__":
    print(Constant.DASHSCOPE_API_KEY)
