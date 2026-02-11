# mapper/database.py
import aiomysql
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()


class Database:
    def __init__(self):
        self.host = os.getenv("MYSQL_HOST")
        self.port = int(os.getenv("MYSQL_PORT"))
        self.user = os.getenv("MYSQL_USER")
        self.password = os.getenv("MYSQL_PASSWORD")
        self.database = os.getenv("MYSQL_DATABASE")
        self._pool = None  # 连接池将在首次使用或显式初始化时创建

    async def _get_pool(self):
        """获取连接池（单例模式）"""
        if self._pool is None:
            self._pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                charset='utf8mb4',
                autocommit=True,
                minsize=1,
                maxsize=10,
            )
        return self._pool

    async def close(self):
        """关闭连接池（应在应用退出时调用）"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()

    from datetime import date

    async def init_user(self, user_id: str, group_id: str):
        """
        初始化用户在三张表中的记录（仅当记录不存在时插入默认值）
        - user_status: is_reusable = True
        - user_points: points = 0
        - checkin_records: total_days=0, streak_days=0, last_checkin_date=NULL
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # 初始化 user_status
                await cursor.execute("""
                    INSERT IGNORE INTO user_status (user_id, group_id, is_reusable)
                    VALUES (%s, %s, %s)
                """, (user_id, group_id, 1))

                # 初始化 user_points
                await cursor.execute("""
                    INSERT IGNORE INTO user_points (user_id, group_id, points)
                    VALUES (%s, %s, %s)
                """, (user_id, group_id, 0))

                # 初始化 checkin_records
                await cursor.execute("""
                    INSERT IGNORE INTO checkin_records 
                        (user_id, group_id, last_checkin_date, total_days, streak_days)
                    VALUES (%s, %s, %s, %s, %s)
                """, (user_id, group_id, None, 0, 0))

    # ========================
    # Table: checkin_records
    # ========================

    async def get_checkin_record(self, user_id: str, group_id: str):
        """获取用户的签到记录（含累计、连续天数）"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                sql = """
                    SELECT last_checkin_date, total_days, streak_days
                    FROM checkin_records
                    WHERE user_id = %s AND group_id = %s
                """
                await cursor.execute(sql, (user_id, group_id))
                return await cursor.fetchone()

    async def add_or_update_checkin(self, user_id: str, group_id: str, checkin_date: date, total_days: int,
                                    streak_days: int):
        """插入或更新签到记录"""
        pool = await self._get_pool()
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    sql = """
                        INSERT INTO checkin_records 
                            (user_id, group_id, last_checkin_date, total_days, streak_days)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            last_checkin_date = VALUES(last_checkin_date),
                            total_days = VALUES(total_days),
                            streak_days = VALUES(streak_days),
                            updated_at = CURRENT_TIMESTAMP
                    """
                    await cursor.execute(sql, (user_id, group_id, checkin_date, total_days, streak_days))
            return True
        except Exception as e:
            print(f"Update checkin record error: {e}")
            return False

    # ========================
    # Table: user_status
    # ========================

    async def create_or_update_user_status(self, user_id: str, group_id: str, is_reusable: bool = True):
        """插入或更新用户状态（ON DUPLICATE KEY UPDATE）"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = """
                    INSERT INTO user_status (user_id, group_id, is_reusable)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        is_reusable = VALUES(is_reusable),
                        updated_at = CURRENT_TIMESTAMP
                """
                await cursor.execute(sql, (user_id, group_id, int(is_reusable)))

    async def get_user_status(self, user_id: str, group_id: str):
        """获取用户状态"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                sql = "SELECT * FROM user_status WHERE user_id = %s AND group_id = %s"
                await cursor.execute(sql, (user_id, group_id))
                return await cursor.fetchone()

    async def update_user_status(self, user_id: str, group_id: str, is_reusable: bool):
        """更新用户状态（也可用 create_or_update_user_status）"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "UPDATE user_status SET is_reusable = %s WHERE user_id = %s AND group_id = %s"
                affected = await cursor.execute(sql, (int(is_reusable), user_id, group_id))
                return affected > 0

    async def delete_user_status(self, user_id: str, group_id: str):
        """删除用户状态（会级联删除 user_points）"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "DELETE FROM user_status WHERE user_id = %s AND group_id = %s"
                affected = await cursor.execute(sql, (user_id, group_id))
                return affected > 0

    # ========================
    # Table: user_points
    # ========================

    async def get_user_points(self, user_id: str, group_id: str):
        """获取用户当前积分"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                sql = "SELECT points FROM user_points WHERE user_id = %s AND group_id = %s"
                await cursor.execute(sql, (user_id, group_id))
                result = await cursor.fetchone()
                return result['points'] if result else None

    async def add_user_points(self, user_id: str, group_id: str, delta: int):
        """增加/减少用户积分（支持负数）"""
        # 显式初始化用户状态（更清晰）
        await self.create_or_update_user_status(user_id, group_id)

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = """
                    UPDATE user_points
                    SET points = points + %s
                    WHERE user_id = %s AND group_id = %s
                """
                affected = await cursor.execute(sql, (delta, user_id, group_id))
                return affected > 0

    async def set_user_points(self, user_id: str, group_id: str, points: int):
        """直接设置用户积分"""
        await self.init_user_points(user_id, group_id)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "UPDATE user_points SET points = %s WHERE user_id = %s AND group_id = %s"
                await cursor.execute(sql, (points, user_id, group_id))

    async def delete_user_points(self, user_id: str, group_id: str):
        """删除用户积分（一般不建议单独删，因有外键依赖）"""
        # 注意：由于外键 ON DELETE CASCADE，删 user_status 会自动删 points
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                sql = "DELETE FROM user_points WHERE user_id = %s AND group_id = %s"
                affected = await cursor.execute(sql, (user_id, group_id))
                return affected > 0

    # ========================
    # Table: user_system_prompts
    # ========================

    async def get_user_system_prompt(self, user_id: str, group_id: str) -> str | None:
        """获取用户自定义系统提示词"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                sql = "SELECT system_prompt FROM user_system_prompts WHERE user_id = %s AND group_id = %s"
                await cursor.execute(sql, (user_id, group_id))
                result = await cursor.fetchone()
                return result['system_prompt'] if result else None

    async def set_user_system_prompt(self, user_id: str, group_id: str, prompt: str) -> bool:
        """设置或更新用户系统提示词"""
        pool = await self._get_pool()
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    sql = """
                        INSERT INTO user_system_prompts (user_id, group_id, system_prompt)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            system_prompt = VALUES(system_prompt),
                            updated_at = CURRENT_TIMESTAMP
                    """
                    await cursor.execute(sql, (user_id, group_id, prompt))
            return True
        except Exception as e:
            print(f"Error saving system prompt: {e}")
            return False
