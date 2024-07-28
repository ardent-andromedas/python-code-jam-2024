import asyncio
import io
import logging
from collections import deque
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands

from ecosystem import EcosystemManager
from storage.models import Database, GuildConfig, event_db_builder

from .discord_event import DiscordEvent, EventType
from .settings import BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(name)s: %(message)s")

MAX_MESSAGES = 2


class EcoCordClient(discord.Client):
    """A custom Discord client for managing multiple ecosystem simulations and handling Discord events."""

    def __init__(self) -> None:
        """Initialize the EcoCordClient with default intents and set up necessary attributes."""
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.tree.add_command(configure)
        self.guilds_data = {}
        self.ready = False
        self.database = Database("ecocord")

    async def on_ready(self) -> None:
        """Event receiver for when the client is done preparing the data received from Discord."""
        await self.database.initialize()
        self.ready = True
        print(f"Logged in as {self.user} (ID: {self.user.id})")

        for guild in self.guilds:
            await self.tree.sync(guild=guild)
            print(f"Synced commands for guild: {guild.name}")

        for guild in self.guilds:
            await self.initialize_guild(guild)

    async def initialize_guild(self, guild: discord.Guild) -> None:
        """Initialize the guild data and ecosystem managers for a given Discord guild.

        This method sets up the necessary data structures for the guild, retrieves the guild configuration
        from the database, and initializes ecosystem managers for the configured channels. It also loads
        critters for online members in each ecosystem manager.

        Args:
        ----
            guild (discord.Guild): The Discord guild to initialize.

        Returns:
        -------
            None

        """
        if guild.id not in self.guilds_data:
            self.guilds_data[guild.id] = {
                "ecosystem_managers": {},
            }
            config = await self.database.get_guild_config(guild.id)
            if config:
                self.guilds_data[guild.id]["gif_channel_id"] = config.gif_channel
                # Call reconfigure_channels here with the channels from the config
                channels = [guild.get_channel(channel_id) for channel_id in config.allowed_channels]
                await self.reconfigure_channels(guild.id, channels)

        print("here")
        online_members = [member.id for member in guild.members if member.status != discord.Status.offline]
        for ecosystem_manager in self.guilds_data[guild.id]["ecosystem_managers"].values():
            ecosystem_manager.set_online_critters(online_members)

        print("there")
        # Start the task to update online critters
        self.loop.create_task(self.update_online_critters(guild))

    async def update_online_critters(self, guild: discord.Guild) -> None:
        """Periodically update online critters for all ecosystem managers in the guild."""
        while True:
            online_members = [member.id for member in guild.members if member.status != discord.Status.offline]
            for ecosystem_manager in self.guilds_data[guild.id]["ecosystem_managers"].values():
                ecosystem_manager.set_online_critters(online_members)
            await asyncio.sleep(5)

    async def on_message(self, message: discord.Message) -> None:
        """Event receiver for when a message is sent in a visible channel.

        Creates a DiscordEvent for the message and processes it.

        Args:
        ----
            message (discord.Message): The message that was sent.

        """
        # Check if the message is a direct message
        is_direct_message = isinstance(message.channel, discord.DMChannel)

        # If it's a direct message, we'll handle it differently
        if is_direct_message:
            return

        event = DiscordEvent.from_discord_objects(
            type=EventType.MESSAGE,
            timestamp=message.created_at,
            guild=message.guild,
            channel=message.channel,
            member=message.author,
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
        event = DiscordEvent.from_discord_objects(
            type=EventType.REACTION,
            timestamp=message.created_at,
            guild=self.get_guild(payload.guild_id),
            channel=channel,
            member=payload.member,
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
        event = DiscordEvent.from_discord_objects(
            type=EventType.TYPING,
            timestamp=payload.timestamp,
            guild=self.get_guild(payload.guild_id),
            channel=channel,
            member=payload.user,
            content="User is typing",
        )
        await self.process_event(event)

    async def process_event(self, event: DiscordEvent) -> None:
        """Process a DiscordEvent by logging it and passing it to the corresponding ecosystem manager."""
        print(
            f"Event: {event.type.name} - {event.member.display_name} in {event.channel}: "
            f"{event.content} @ {event.timestamp}"
        )
        guild_data = self.guilds_data.get(event.guild.id)
        if guild_data:
            ecosystem_manager = guild_data["ecosystem_managers"].get(event.channel.id)
            if ecosystem_manager:
                ecosystem_manager.process_event(event)
            db_event = await event_db_builder(event)
            await self.database.insert_event(db_event)

    async def start_ecosystems(self, guild_id: int, channels: list[discord.TextChannel] | None = None) -> None:
        """Initialize and start ecosystem managers for specified channels."""
        guild_data = self.guilds_data.get(guild_id)
        if not guild_data or guild_data["gif_channel_id"] is None:
            return

        gif_channel = await self.fetch_channel(guild_data["gif_channel_id"])
        existing_threads = {thread.name: thread for thread in gif_channel.threads}

        gif_tasks = []

        for channel in channels:
            if channel.id not in guild_data["ecosystem_managers"]:
                ecosystem_manager = EcosystemManager(generate_gifs=True, interactive=False)
                ecosystem_manager.start(show_controls=False)
                guild_data["ecosystem_managers"][channel.id] = ecosystem_manager

                thread_name = f"Ecosystem-{channel.name}"
                if thread_name in existing_threads:
                    thread = existing_threads[thread_name]
                    print(f"Reusing existing thread for {channel.name}")
                else:
                    thread = await gif_channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread)
                    print(f"Created new thread for {channel.name}")

                gif_tasks.append(self.send_gifs(guild_id, channel.id, thread.id))

        # Start all new gif sending tasks in parallel
        await asyncio.gather(*gif_tasks)

    async def stop_ecosystems(self, guild_id: int, channel_ids: list[int] | None = None) -> None:
        """Stop specified ecosystem managers or all if not specified."""
        guild_data = self.guilds_data.get(guild_id)
        if not guild_data:
            return

        if channel_ids is None:
            channel_ids = list(guild_data["ecosystem_managers"].keys())

        for channel_id in channel_ids:
            ecosystem_manager = guild_data["ecosystem_managers"].pop(channel_id, None)
            if ecosystem_manager:
                ecosystem_manager.stop()

    async def stop_all_ecosystems(self) -> None:
        """Stop all ecosystem managers for all guilds."""
        for guild_data in self.guilds_data.values():
            ecosystem_managers = guild_data.get("ecosystem_managers", {})
            for ecosystem_manager in ecosystem_managers.values():
                ecosystem_manager.stop()
            guild_data["ecosystem_managers"] = {}

    async def reconfigure_channels(self, guild_id: int, new_channels: list[discord.TextChannel]) -> None:
        """Reconfigure the bot to run in the specified channels."""
        guild_data = self.guilds_data.get(guild_id)
        if not guild_data:
            return

        new_channel_ids = {channel.id for channel in new_channels}
        current_channel_ids = set(guild_data["ecosystem_managers"].keys())

        channels_to_stop = current_channel_ids - new_channel_ids
        channels_to_start = new_channel_ids - current_channel_ids

        config_channels = [self.get_guild(guild_id).get_channel(channel) for channel in channels_to_start]

        await self.stop_ecosystems(guild_id, list(channels_to_stop))
        await self.start_ecosystems(guild_id, [channel for channel in new_channels if channel.id in channels_to_start])

        # Update the guild configuration in the database
        config = GuildConfig(
            guild_id=guild_id, allowed_channels=list(new_channel_ids), gif_channel=guild_data["gif_channel_id"]
        )
        await self.database.set_guild_config(config)
        await self.backfill_messages(guild_id=guild_id, channels=config_channels)

    async def send_gifs(self, guild_id: int, channel_id: int, thread_id: int) -> None:
        """Continuously sends GIFs of the ecosystem to a designated thread."""
        guild_data = self.guilds_data.get(guild_id)
        if not guild_data:
            return

        ecosystem_manager = guild_data["ecosystem_managers"].get(channel_id)
        if not ecosystem_manager:
            return

        while not self.ready:
            await asyncio.sleep(1)

        thread = await self.fetch_channel(thread_id)
        message_queue = deque(maxlen=MAX_MESSAGES)

        # Find existing messages and populate the queue
        existing_messages = await self.find_existing_messages(thread)
        # Delete all existing messages except the last max messages
        oldest_messages = existing_messages[:-MAX_MESSAGES]
        for message in oldest_messages:
            await message.delete()
        existing_messages = existing_messages[-MAX_MESSAGES:]
        message_queue.extend(existing_messages)

        while True:
            gif_data = ecosystem_manager.get_latest_gif()
            if not gif_data:
                await asyncio.sleep(0.01)
                continue

            gif_bytes, timestamp = gif_data

            content = f"Ecosystem for #{self.get_channel(channel_id).name}"
            # Send new message
            new_message = await thread.send(
                content=content, file=discord.File(io.BytesIO(gif_bytes), filename="ecosystem.gif")
            )

            # If the queue is full, the oldest message will be automatically removed
            # We need to delete it from Discord as well
            if len(message_queue) == MAX_MESSAGES:
                old_message = message_queue[0]
                await old_message.delete()

            message_queue.append(new_message)

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

    async def backfill_messages(self, guild_id: int, channels: list[discord.TextChannel], after: datetime | None = None) -> None:
        before = datetime.now(timezone.utc)
        duration = after
        if after is None:
            duration = before - timedelta(minutes=60)  # default to messages in the last hour

        async for channel in channels:
            async for message in channel.history(limit=100, before=before, after=duration):
                db_event = await event_db_builder(
                    DiscordEvent(
                        EventType.MESSAGE,
                        timestamp=message.created_at,
                        guild=guild_id,
                        channel=channel.id,
                        member=message.author.id,
                        content=message.content
                    )
                )
                await self.database.insert_event(db_event)

    async def run_bot(self) -> None:
        """Start the bot and connects to Discord."""
        print("Starting bot...")
        await self.start(BOT_TOKEN)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Event receiver for when the bot joins a new guild."""
        await self.initialize_guild(guild)

        # Find a channel visible to admins (e.g., a "general" or "admin" channel)
        admin_channel = next(
            (
                channel
                for channel in guild.text_channels
                if channel.permissions_for(guild.me).send_messages
                   and channel.overwrites_for(guild.default_role).read_messages is not False
                   and any(
                role.permissions.administrator
                for role in guild.roles
                if channel.overwrites_for(role).read_messages is not False
            )
            ),
            None,
        )

        if admin_channel:
            embed = discord.Embed(
                title="EcoCord Bot Installed!",
                description="Bot installed. Admins can use `/configure` to set it up.",
                color=discord.Color.blue(),
            )

            try:
                await admin_channel.send(embed=embed)
                logging.info(
                    "Sent welcome message in guild %s (ID: %s) in channel %s", guild.name, guild.id, admin_channel.name
                )
            except discord.errors.Forbidden:
                logging.warning(
                    "Failed to send welcome message in guild %s (ID: %s) due to permissions", guild.name, guild.id
                )
        else:
            logging.warning(
                "Couldn't find suitable channel to send welcome message in guild %s (ID: %s)", guild.name, guild.id
            )

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Event receiver for when the bot is removed from a guild."""
        if guild.id in self.guilds_data:
            # Stop all ecosystem managers for this guild
            await self.stop_ecosystems(guild.id)
            # Remove the guild data
            del self.guilds_data[guild.id]
        logging.info("Removed from guild %s (ID: %s)", guild.name, guild.id)


class ConfigureView(discord.ui.View):
    """View for configuring EcoCord."""

    def __init__(self, client: discord.Client, guild_id: int, visible_channels: list[discord.TextChannel]) -> None:
        """Initialize the ConfigureView.

        Args:
        ----
            client: The Discord client.
            guild_id: The ID of the guild being configured.
            visible_channels: List of visible text channels in the guild.

        """
        super().__init__()
        self.client = client
        self.guild_id = guild_id
        self.visible_channels = visible_channels

        # Get existing configuration
        guild_data = self.client.guilds_data.get(self.guild_id, {})
        self.managed_channels = [
            channel for channel in visible_channels if channel.id in guild_data.get("ecosystem_managers", {})
        ]
        self.gif_channel = next(
            (channel for channel in visible_channels if channel.id == guild_data.get("gif_channel_id")), None
        )

        # Add managed channels select
        self.add_item(
            discord.ui.ChannelSelect(
                custom_id="managed_channels",
                placeholder="Select managed channels",
                min_values=1,
                max_values=len(visible_channels),
                channel_types=[discord.ChannelType.text],
                default_values=self.managed_channels,
            )
        )

        # Add GIF channel select
        self.add_item(
            discord.ui.ChannelSelect(
                custom_id="gif_channel",
                placeholder="Select GIF channel",
                min_values=1,
                max_values=1,
                channel_types=[discord.ChannelType.text],
                default_values=[self.gif_channel] if self.gif_channel else None,
            )
        )

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.primary)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.on_submit(interaction)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        client = interaction.client
        guild_data = client.guilds_data.get(interaction.guild.id)

        if not self.managed_channels or not self.gif_channel:
            await interaction.response.send_message(
                "Please select both managed channels and a GIF channel before submitting.", ephemeral=True
            )
            return

        if guild_data:
            guild_data["gif_channel_id"] = self.gif_channel.id

        # Update the guild configuration in the database
        config = GuildConfig(
            guild_id=interaction.guild.id,
            allowed_channels=[channel.id for channel in self.managed_channels],
            gif_channel=self.gif_channel.id,
        )
        try:
            await client.database.set_guild_config(config)
        except Exception:
            logging.exception("Failed to update database")
            await interaction.followup.send(
                "An error occurred while saving the configuration. Please try again.", ephemeral=True
            )
            return

        confirmation_message = (
            "Configuration complete!\n\n"
            f"Bot configured to run in channels: {', '.join(channel.name for channel in self.managed_channels)}\n"
            f"GIF threads will be created in: #{self.gif_channel.name}"
        )

        try:
            message = await interaction.original_response()
            await message.edit(content=confirmation_message, view=None)
        except discord.NotFound:
            # If the original message was deleted, send a new message
            await interaction.followup.send(content=confirmation_message, ephemeral=True)

        try:
            await client.reconfigure_channels(interaction.guild.id, self.managed_channels)
        except Exception:
            logging.exception("Failed to reconfigure channels")
            await interaction.followup.send(
                "Configuration saved, but there was an error applying the changes. "
                "Please try again or contact support.",
                ephemeral=True,
            )

        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data["component_type"] == discord.ComponentType.channel_select.value:
            if interaction.data["custom_id"] == "managed_channels":
                self.managed_channels = [
                    interaction.guild.get_channel(int(channel_id)) for channel_id in interaction.data["values"]
                ]
            elif interaction.data["custom_id"] == "gif_channel":
                self.gif_channel = interaction.guild.get_channel(int(interaction.data["values"][0]))

        # Acknowledge the interaction
        await interaction.response.defer()
        return True


@app_commands.command(name="configure", description="Configure EcoCord")
@app_commands.default_permissions(administrator=True)
async def configure(interaction: discord.Interaction) -> None:
    """Configure EcoCord settings for the guild."""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    visible_channels = [
        channel
        for channel in interaction.guild.text_channels
        if channel.permissions_for(interaction.guild.me).send_messages
    ]
    view = ConfigureView(interaction.client, interaction.guild.id, visible_channels)
    await interaction.response.send_message("Please configure the bot:", view=view, ephemeral=True)
