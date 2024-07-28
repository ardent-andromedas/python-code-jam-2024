from dataclasses import dataclass
from datetime import datetime
from enum import Flag, auto
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import discord


@dataclass
class FakeUser:
    """A class representing a fake user for testing or placeholder purposes.

    Attributes
    ----------
        id (int): The unique identifier for the fake user.
        display_name (str): The display name of the fake user.

    """

    id: int
    display_name: str


class EventType(Flag):
    """EventType is an enumeration that represents different types of events that can occur in a Discord server.

    Attributes
    ----------
    ON_LOAD : auto
        Represents the event when the ecosystem is loaded.
    MESSAGE : auto
        Represents the event when a message is sent.
    REACTION : auto
        Represents the event when a reaction is added to a message.
    TYPING : auto
        Represents the event when a user starts typing.

    """

    ON_LOAD = auto()
    MESSAGE = auto()
    REACTION = auto()
    TYPING = auto()


@dataclass
class SerializableGuild:
    """Serializable representation of a Discord guild.

    Attributes
    ----------
        id (int): The unique identifier of the guild.
        name (str): The name of the guild.
        verification_level (int): The verification level of the guild.

    """

    id: int
    name: str
    verification_level: int


@dataclass
class SerializableTextChannel:
    """Serializable representation of a Discord text channel.

    Attributes
    ----------
        id (int): The unique identifier of the text channel.
        name (str): The name of the text channel.

    """

    id: int
    name: str


@dataclass
class SerializableMember:
    """Serializable representation of a Discord member.

    Attributes
    ----------
        id (int): The unique identifier of the member.
        name (str): The username of the member.
        display_name (str): The display name of the member.
        roles (list[int]): List of role IDs the member has.
        guild_id (int): The ID of the guild the member belongs to.
        avatar (str): The URL of the member's avatar.
        color (int): The color associated with the member's top role.

    """

    id: int
    name: str
    display_name: str
    roles: list[int]
    guild_id: int
    avatar: str
    color: int


@dataclass
class DiscordEvent:
    """A class representing a Discord event with relevant information.

    Attributes
    ----------
        type (str): The type of the Discord event.
        timestamp (datetime): The timestamp when the event occurred.
        guild (SerializableGuild): Serializable representation of the Discord guild.
        channel (SerializableTextChannel): Serializable representation of the text channel.
        member (SerializableMember | FakeUser): Serializable representation of the member or a FakeUser.
        content (str): The content or message associated with the event.

    """

    type: EventType
    timestamp: datetime
    guild: SerializableGuild
    channel: SerializableTextChannel
    member: SerializableMember | FakeUser
    content: str

    @classmethod
    def from_discord_objects(
        cls,
        type: str,
        timestamp: datetime,
        guild: Optional["discord.Guild"],
        channel: Optional["discord.TextChannel"],
        member: Optional["discord.Member"],
        content: str,
    ) -> "DiscordEvent":
        return cls(
            type=type,
            timestamp=timestamp,
            guild=SerializableGuild(guild.id, guild.name, guild.verification_level.value) if guild else None,
            channel=SerializableTextChannel(channel.id, channel.name)
            if channel and hasattr(channel, "id") and hasattr(channel, "name")
            else None,
            member=SerializableMember(
                member.id,
                member.name,
                member.display_name,
                [role.id for role in member.roles],
                member.guild.id,
                str(member.avatar.url) if member.avatar else None,
                member.color,
            )
            if member
            else None,
            content=content,
        )
