import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import aiosqlite

from bot.discord_event import DiscordEvent


@dataclass
class DBEvent:
    """Represents a database event."""

    event_type: str
    timestamp: int
    guild_id: int
    channel_id: int
    member_id: int
    message_id: int | None
    content: str | None


class EventTypeEnum(str, Enum):
    """Enum for event types."""

    MESSAGE = "message"
    TYPING = "typing"
    REACTION = "reaction"


class CommandType(str, Enum):
    """Enum for command types."""

    ON_LOAD = "on_load"
    GET = "get"
    INSERT = "insert"


@dataclass
class GuildConfig:
    """Represents guild configuration."""

    guild_id: int
    allowed_channels: list[int]
    gif_channel: int | None


@dataclass
class EcosystemState:
    """Represents the ecosystem state."""

    guild_id: int
    cloud_image_id: str
    state_data: dict = field(default_factory=dict)


@dataclass
class UserInfo:
    user_id: int
    guild_id: int
    avatar_data: bytes | None
    role_color: int | None
    last_updated: datetime


class Database:
    """Handles database operations."""

    def __init__(self, db_name: str) -> None:
        """Initialize the Database.

        Args:
        ----
            db_name (str): The name of the database.

        """
        self.db_file_path = f"{db_name}.sqlite3"
        self.logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        """Initialize the database and create tables if they don't exist."""
        try:
            async with aiosqlite.connect(self.db_file_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id TEXT NOT NULL PRIMARY KEY,
                        guild_id INT NOT NULL,
                        event_type TEXT NOT NULL,
                        timestamp INT NOT NULL,
                        channel_id INT NOT NULL,
                        member_id INT NOT NULL,
                        message_id TEXT,
                        content TEXT
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS guild_config (
                        guild_id INTEGER PRIMARY KEY,
                        allowed_channels TEXT NOT NULL,
                        gif_channel INTEGER
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS ecosystem_state (
                        guild_id INTEGER PRIMARY KEY,
                        cloud_image_id TEXT NOT NULL,
                        state_data TEXT NOT NULL
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_info (
                        user_id INTEGER NOT NULL,
                        guild_id INTEGER NOT NULL,
                        avatar_data BLOB,
                        role_color TEXT,
                        last_updated TIMESTAMP NOT NULL,
                        PRIMARY KEY (user_id, guild_id)
                    )
                """)
                await db.commit()
            self.logger.info("Database initialized successfully.")
        except aiosqlite.Error:
            self.logger.exception("Failed to initialize database")
            raise

    async def execute(self, command: CommandType, query: str | None = None, parameters: tuple | None = None) -> None:
        """Execute a database command.

        Args:
        ----
            command (CommandType): The type of command to execute.
            query (Optional[str], optional): The SQL query. Defaults to None.
            parameters (Optional[tuple], optional): Query parameters. Defaults to None.

        Raises:
        ------
            aiosqlite.Error: If there's an error executing the database command.

        """
        try:
            async with aiosqlite.connect(self.db_file_path) as db:
                db: aiosqlite.Connection
                cursor = await db.cursor()
                match command:
                    case CommandType.ON_LOAD:
                        await cursor.execute(query)
                        await db.commit()
                        self.logger.info("Database loaded successfully.")
                    case CommandType.INSERT:
                        await cursor.execute(query, parameters)
                        await db.commit()
                    case CommandType.GET:
                        return await db.execute_fetchall(query, parameters)
        except aiosqlite.Error:
            self.logger.exception("Database error (%s)", command.value)
            raise

    async def insert_event(self, event: DBEvent) -> None:
        query = """
        INSERT INTO events(id, guild_id, event_type, timestamp, channel_id, member_id, message_id, content)
        VALUES(?,?,?,?,?,?,?,?)
        """
        data = (
            str(uuid.uuid4()),
            event.guild_id,
            event.event_type,
            event.timestamp,
            event.channel_id,
            event.member_id,
            event.message_id,
            event.content,
        )
        await self.execute(command=CommandType.INSERT, query=query, parameters=data)

    async def get_events_by_guild(self, guild_id: int, start_time: int, stop_time: int) -> list[DBEvent]:
        """Retrieve events for a specific guild within a specified time range.

        Args:
        ----
            guild_id (int): The ID of the guild.
            start_time (int): The start timestamp.
            stop_time (int): The end timestamp.

        Returns:
        -------
            list[DBEvent]: A list of DBEvent objects.

        """
        query = """
        SELECT event_type, timestamp, guild_id, channel_id, member_id, message_id, content
        FROM events
        WHERE guild_id = ? AND timestamp BETWEEN ? AND ?
        """
        async with (
            aiosqlite.connect(self.db_file_path) as db,
            db.execute(query, (guild_id, start_time, stop_time)) as cursor,
        ):
            rows = await cursor.fetchall()
            return [DBEvent(*row) for row in rows]

    async def set_guild_config(self, config: GuildConfig) -> None:
        """Set or update the configuration for a guild."""
        query = """
        INSERT OR REPLACE INTO guild_config (guild_id, allowed_channels, gif_channel)
        VALUES (?, ?, ?)
        """
        allowed_channels_str = ",".join(map(str, config.allowed_channels))
        data = (config.guild_id, allowed_channels_str, config.gif_channel)
        await self.execute(command=CommandType.INSERT, query=query, parameters=data)

    async def get_guild_config(self, guild_id: int) -> GuildConfig | None:
        """Retrieve the configuration for a specific guild."""
        query = """
        SELECT guild_id, allowed_channels, gif_channel
        FROM guild_config
        WHERE guild_id = ?
        """
        async with aiosqlite.connect(self.db_file_path) as db, db.execute(query, (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                guild_id, allowed_channels_str, gif_channel = row
                allowed_channels = list(map(int, allowed_channels_str.split(",")))
                return GuildConfig(guild_id, allowed_channels, gif_channel)
            return None

    async def save_ecosystem_state(self, state: EcosystemState) -> None:
        """Save or update the ecosystem state for a guild."""
        query = """
        INSERT OR REPLACE INTO ecosystem_state (guild_id, cloud_image_id, state_data)
        VALUES (?, ?, ?)
        """
        state_data_json = json.dumps(state.state_data)
        data = (state.guild_id, state.cloud_image_id, state_data_json)
        await self.execute(command=CommandType.INSERT, query=query, parameters=data)

    async def get_ecosystem_state(self, guild_id: int) -> EcosystemState | None:
        """Retrieve the ecosystem state for a specific guild."""
        query = """
        SELECT guild_id, cloud_image_id, state_data
        FROM ecosystem_state
        WHERE guild_id = ?
        """
        async with aiosqlite.connect(self.db_file_path) as db, db.execute(query, (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                guild_id, cloud_image_id, state_data_json = row
                state_data = json.loads(state_data_json)
                return EcosystemState(guild_id, cloud_image_id, state_data)
            return None

    async def get_user_info(self, user_id: int, guild_id: int) -> UserInfo | None:
        """Retrieve user info for a specific user in a specific guild."""
        query = """
        SELECT user_id, guild_id, avatar_data, role_color, last_updated
        FROM user_info
        WHERE user_id = ? AND guild_id = ?
        """
        async with aiosqlite.connect(self.db_file_path) as db:
            async with db.execute(query, (user_id, guild_id)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return UserInfo(
                        user_id=row[0],
                        guild_id=row[1],
                        avatar_data=row[2],
                        role_color=row[3],
                        last_updated=datetime.fromisoformat(row[4]),
                    )
                return None

    async def set_user_info(self, user_info: UserInfo) -> None:
        """Set or update the user info for a specific user in a specific guild."""
        query = """
        INSERT OR REPLACE INTO user_info (user_id, guild_id, avatar_data, role_color, last_updated)
        VALUES (?, ?, ?, ?, ?)
        """
        data = (
            user_info.user_id,
            user_info.guild_id,
            user_info.avatar_data,
            user_info.role_color,
            user_info.last_updated.isoformat(),
        )
        await self.execute(command=CommandType.INSERT, query=query, parameters=data)

    async def get_random_user_info(self, guild_id: int) -> UserInfo | None:
        """Retrieve random user info for a specific guild."""
        query = """
        SELECT user_id, guild_id, avatar_data, role_color, last_updated
        FROM user_info
        WHERE guild_id = ?
        ORDER BY RANDOM()
        LIMIT 1
        """
        async with aiosqlite.connect(self.db_file_path) as db:
            async with db.execute(query, (guild_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return UserInfo(
                        user_id=row[0],
                        guild_id=row[1],
                        avatar_data=row[2],
                        role_color=row[3],
                        last_updated=datetime.fromisoformat(row[4]),
                    )
                return None


async def event_db_builder(event: DiscordEvent) -> DBEvent:
    """Build a DBEvent from a DiscordEvent.

    Args:
    ----
        event (DiscordEvent): The Discord event to convert.

    Returns:
    -------
        DBEvent: The converted database event.

    """
    message_id = event.message.id if event.type in {EventTypeEnum.MESSAGE, EventTypeEnum.REACTION} else None
    return DBEvent(
        event_type=event.type.value,
        timestamp=event.timestamp.timestamp().__round__(),
        guild_id=event.guild.id,
        channel_id=event.channel.id,
        member_id=event.member.id,
        message_id=message_id,
        content=event.content,
    )
