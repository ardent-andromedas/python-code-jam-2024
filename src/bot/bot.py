import asyncio
import io
import logging
from collections import deque

import discord
from discord import app_commands

from ecosystem import EcosystemManager

from .discord_event import DiscordEvent
from .settings import BOT_TOKEN, GIF_CHANNEL_ID, GUILD_ID

logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(name)s: %(message)s")

MAX_MESSAGES = 2


class EcoCordClient(discord.Client):
    """A custom Discord client for managing an ecosystem simulation and handling Discord events."""

    def __init__(self) -> None:
        """Initialize the EcoCordClient with default intents and set up necessary attributes."""
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.test_guild = discord.Object(id=GUILD_ID)
        self.ecosystem_manager = None
        self.ready = False

    async def on_ready(self) -> None:
        """Event receiver for when the client is done preparing the data received from Discord.

        Sets the client as ready and prints a login confirmation message.
        """
        self.ready = True
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")

    async def on_message(self, message: discord.Message) -> None:
        """Event receiver for when a message is sent in a visible channel.

        Creates a DiscordEvent for the message and processes it.

        Args:
        ----
            message (discord.Message): The message that was sent.

        """
        event = DiscordEvent(
            type="message",
            timestamp=message.created_at,
            guild=message.guild,
            channel=message.channel,
            user=message.author,
            content=message.content,
        )
        await self.process_event(event)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Event receiver for when a message reaction is added to a message.

        Creates a DiscordEvent for the reaction and processes it.

        Args:
        ----
            payload (discord.RawReactionActionEvent): The raw event payload for the reaction.

        """
        channel = self.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        event = DiscordEvent(
            type="reaction",
            timestamp=message.created_at,
            guild=self.get_guild(payload.guild_id),
            channel=channel,
            user=payload.member,
            content=f"{payload.emoji} added on {message.content}",
        )
        await self.process_event(event)

    async def on_raw_typing(self, payload: discord.RawTypingEvent) -> None:
        """Event receiver for when a user starts typing in a channel.

        Creates a DiscordEvent for the typing action and processes it.

        Args:
        ----
            payload (discord.RawTypingEvent): The raw event payload for the typing action.

        """
        channel = self.get_channel(payload.channel_id)
        event = DiscordEvent(
            type="typing",
            timestamp=payload.timestamp,
            guild=self.get_guild(payload.guild_id),
            channel=channel,
            user=payload.user,
            content="User is typing",
        )
        await self.process_event(event)

    async def process_event(self, event: DiscordEvent) -> None:
        """Process a DiscordEvent by logging it and passing it to the ecosystem manager.

        Args:
        ----
            event (DiscordEvent): The event to process.

        """
        print(
            f"Event: {event.type} - {event.user.display_name} in {event.channel}: {event.content} @ {event.timestamp}"
        )
        if self.ecosystem_manager:
            self.ecosystem_manager.process_event(event)

    async def start_ecosystem(self) -> None:
        """Initialize and start the ecosystem manager."""
        self.ecosystem_manager = EcosystemManager(generate_gifs=True, interactive=False)
        self.ecosystem_manager.start(show_controls=False)

    async def stop_ecosystem(self) -> None:
        """Stop the ecosystem manager if it exists."""
        if self.ecosystem_manager:
            self.ecosystem_manager.stop()

    async def find_existing_messages(self, channel: discord.TextChannel) -> list[discord.Message]:
        """Find existing ecosystem messages in the given channel.

        Args:
        ----
            channel (discord.TextChannel): The channel to search for messages.

        Returns:
        -------
            list[discord.Message]: A list of existing ecosystem messages, sorted by creation time.

        """
        existing_messages = [
            message
            async for message in channel.history(limit=100)
            if message.author == self.user and message.content.startswith("Ecosystem")
        ]
        return sorted(existing_messages, key=lambda m: m.created_at)

    async def send_gifs(self) -> None:
        """Continuously sends GIFs of the ecosystem to a designated channel.

        Manages a queue of messages to maintain a maximum number of GIFs.
        """
        if not self.ecosystem_manager:
            return

        while not self.ready:
            await asyncio.sleep(1)

        channel = await self.fetch_channel(GIF_CHANNEL_ID)
        message_queue = deque(maxlen=MAX_MESSAGES)

        # Find existing messages and populate the queue
        existing_messages = await self.find_existing_messages(channel)
        # Delete all existing messages except the last max messages
        oldest_messages = existing_messages[:-MAX_MESSAGES]
        for message in oldest_messages:
            await message.delete()
        existing_messages = existing_messages[-MAX_MESSAGES:]
        message_queue.extend(existing_messages)

        while True:
            gif_data = self.ecosystem_manager.get_latest_gif()
            if not gif_data:
                await asyncio.sleep(0.01)
                continue

            gif_bytes, timestamp = gif_data

            content = "Ecosystem"

            # Send new message
            new_message = await channel.send(
                content=content, file=discord.File(io.BytesIO(gif_bytes), filename="ecosystem.gif")
            )

            # If the queue is full, the oldest message will be automatically removed
            # We need to delete it from Discord as well
            if len(message_queue) == MAX_MESSAGES:
                old_message = message_queue[0]
                await old_message.delete()

            message_queue.append(new_message)

    async def timelapse(self, interaction: discord.Interaction, channels: list[discord.TextChannel], timerange: str) \
            -> None:

        """

        args: channels to create timelapse for, time range to grab messages from in Minutes and Seconds

        """
        # interaction.response.send_message(content="Done!",embed=Ecosystem.TimeLapse(channels,timerange)

    async def run_bot(self) -> None:
        """Start the bot and connects to Discord."""
        print("Starting bot...")
        await self.start(BOT_TOKEN)
