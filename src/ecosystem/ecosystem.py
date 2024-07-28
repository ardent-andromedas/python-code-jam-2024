import atexit
import contextlib
import io
import multiprocessing
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import numpy as np

from .shared_numpy_array import SharedNumpyArray

# Hide pygame welcome message
with contextlib.redirect_stdout(None):
    import pygame

import random

from PIL import Image

from bot.discord_event import (
    DiscordEvent,
    SerializableGuild,
    SerializableMember,
    SerializableTextChannel,
)
from storage import Database, UserInfo

from .bird import Bird
from .cloud_manager import CloudManager
from .frog import Frog
from .snake import Snake
from .speech_bubble import SpeechBubble
from .wordclouds import WordCloudObject


class Ecosystem:
    """Represents the ecosystem simulation environment.

    This class manages the overall ecosystem, including various entities like plants, frogs, snakes, and birds.
    It handles the simulation logic, drawing, and user interface elements.
    """

    def __init__(
        self,
        width: int,
        height: int,
        generate_gifs: bool = False,
        gif_duration: int = 5,
        fps: int = 30,
        interactive: bool = True,
    ) -> None:
        """Initialize the Ecosystem.

        Args:
        ----
            width (int): Width of the ecosystem surface.
            height (int): Height of the ecosystem surface.
            generate_gifs (bool): Whether to generate GIFs of the simulation.
            gif_duration (int): Duration of each GIF in seconds.
            fps (int): Frames per second for the simulation.
            interactive (bool): Whether the ecosystem is interactive or not.

        """
        self.width = width
        self.height = height
        self.activity = 1
        self.elapsed_time = 0
        self.surface = pygame.Surface((width, height))

        self.sky_colors = [
            (200, 200, 200),  # Barren gray
            (135, 206, 235),  # Lush blue
        ]
        self.ground_colors = [
            (210, 180, 140),  # Barren tan
            (34, 139, 34),  # Lush green
        ]

        self.critters = []
        self.speech_bubbles = []

        self.font = None
        self.activity_slider = None
        self.spawn_critter_button = None
        self.reset_button = None

        self.generate_gifs = generate_gifs
        self.fps = fps
        self.interactive = interactive

        if self.generate_gifs:
            self.gif_duration = gif_duration
            self.frames_per_gif = self.fps * self.gif_duration
            self.frame_count = 0
            self.shared_frames = SharedNumpyArray((self.frames_per_gif, width, height, 3))
            self.current_frame_index = multiprocessing.Value("i", 0)
            self.frame_count_queue = multiprocessing.Queue()
            self.gif_info_queue = multiprocessing.Queue()
            self.gif_process = multiprocessing.Process(
                target=self._gif_generation_process,
                args=(
                    self.shared_frames,
                    self.current_frame_index,
                    self.frame_count_queue,
                    self.gif_info_queue,
                    self.fps,
                ),
            )
            self.gif_process.start()

        self.cloud_manager = CloudManager(self.width, self.height)
        self.word_cloud = WordCloudObject(
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod "
            "tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, "
            "quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo "
            "consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse "
            "cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat "
            "non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
            self.width,
            self.height,
            5,
        )

        atexit.register(self.cleanup)

    def setup_ui(self) -> None:
        """Set up the user interface elements for the ecosystem."""
        self.font = pygame.font.Font(None, 24)

        button_width = 120
        button_height = 30
        button_spacing = 10
        top_margin = 20
        left_margin = 20

        self.activity_slider = pygame.Rect(left_margin, top_margin, 200, 20)

        button_y = top_margin + self.activity_slider.height + button_spacing

        self.spawn_critter_button = Button(
            left_margin,
            button_y,
            button_width,
            button_height,
            "Spawn Critter",
            (0, 255, 0),
            (0, 0, 0),
            self.font,
        )

        self.reset_button = Button(
            left_margin + button_width + button_spacing,
            button_y,
            button_width,
            button_height,
            "Reset",
            (255, 0, 0),
            (255, 255, 255),
            self.font,
        )

    def update(self, delta: float) -> None:
        """Update the state of the ecosystem.

        Args:
        ----
            delta (float): Time elapsed since the last update.

        """
        self.elapsed_time += delta

        for critter in self.critters:
            critter.update(delta, self.activity)

        if self.interactive:
            self._handle_standard_spawning(delta)

        self._clean_up_entities()

        self.cloud_manager.update(delta)

        self.speech_bubbles = [bubble for bubble in self.speech_bubbles if not bubble.is_expired()]
        for bubble in self.speech_bubbles:
            bubble.update(delta)

    def _handle_standard_spawning(self, delta: float) -> None:
        """Handle the standard spawning of entities based on activity level.

        Args:
        ----
            delta (float): Time elapsed since the last update.

        """
        if random.random() < self.activity * delta:
            self.spawn_critter()

    def _clean_up_entities(self) -> None:
        """Remove dead entities from the ecosystem."""
        self.critters = [critter for critter in self.critters if critter.alive]

    def draw(self) -> pygame.Surface:
        """Draw the current state of the ecosystem.

        Returns
        -------
            pygame.Surface: The surface with the drawn ecosystem.

        """
        sky_color = self.interpolate_color(self.sky_colors[0], self.sky_colors[1], self.activity)
        self.surface.fill(sky_color)

        self.cloud_manager.draw(self.surface)

        ground_color = self.interpolate_color(self.ground_colors[0], self.ground_colors[1], self.activity)
        ground_height = int(self.height * 0.35)

        # Create gradient for ground
        gradient_surface = pygame.Surface((self.width, ground_height))
        for y in range(ground_height):
            alpha = y / ground_height
            color = self.interpolate_color(ground_color, (50, 100, 50), alpha)
            pygame.draw.line(gradient_surface, color, (0, y), (self.width, y))

        self.surface.blit(gradient_surface, (0, self.height - ground_height))

        for bubble in self.speech_bubbles:
            bubble.draw(self.surface)

        for critter in self.critters:
            critter.draw(self.surface)

        self.word_cloud.draw(self.surface)

        return self.surface

    def post_update(self) -> None:
        """Perform post-update operations, such as frame capturing for GIF generation."""
        if self.generate_gifs:
            frame = pygame.surfarray.array3d(self.surface)
            frames = self.shared_frames.get_array()
            index = self.current_frame_index.value
            frames[index] = frame
            self.current_frame_index.value = (index + 1) % self.frames_per_gif
            self.frame_count += 1

            if self.frame_count % self.frames_per_gif == 0:
                self.frame_count_queue.put(self.frame_count)

    def interpolate_color(
        self, color1: tuple[int, int, int], color2: tuple[int, int, int], t: float
    ) -> tuple[int, int, int]:
        """Interpolate between two colors.

        Args:
        ----
            color1 (tuple[int, int, int]): The first color.
            color2 (tuple[int, int, int]): The second color.
            t (float): Interpolation factor between 0 and 1.

        Returns:
        -------
            tuple[int, int, int]: The interpolated color.

        """
        return tuple(int(c1 + (c2 - c1) * t) for c1, c2 in zip(color1, color2, strict=False))

    def reset(self) -> None:
        """Reset the ecosystem to its initial state."""
        self.critters.clear()
        self.activity = 1
        self.elapsed_time = 0

    @staticmethod
    def _gif_generation_process(
        shared_frames: SharedNumpyArray,
        current_frame_index: multiprocessing.Value,
        frame_count_queue: multiprocessing.Queue,
        gif_info_queue: multiprocessing.Queue,
        fps: int,
    ) -> None:
        """Process for generating GIFs from captured frames.

        Args:
        ----
            shared_frames (SharedNumpyArray): Shared array containing frame data.
            current_frame_index (multiprocessing.Value): Current frame index.
            frame_count_queue (multiprocessing.Queue): Queue for frame count information.
            gif_info_queue (multiprocessing.Queue): Queue for generated GIF information.
            fps (int): Frames per second for the GIF.

        """
        frames = shared_frames.get_array()

        def optimize_frame(frame: np.ndarray) -> Image.Image:
            return Image.fromarray(frame.transpose(1, 0, 2)).quantize(method=Image.MEDIANCUT, colors=256)

        with ThreadPoolExecutor() as executor:
            while True:
                frame_count = frame_count_queue.get()
                if frame_count is None:
                    break

                start_index = current_frame_index.value
                ordered_frames = np.roll(frames, -start_index, axis=0)

                optimized_frames = list(executor.map(optimize_frame, ordered_frames))

                duration = int(1000 / fps)

                with io.BytesIO() as gif_buffer:
                    optimized_frames[0].save(
                        gif_buffer,
                        format="GIF",
                        save_all=True,
                        append_images=optimized_frames[1:],
                        optimize=False,
                        duration=[duration] * (len(optimized_frames)),
                        loop=0,
                    )

                    gif_data = gif_buffer.getvalue()

                gif_info_queue.put((gif_data, time.time()))

    def cleanup(self) -> None:
        """Clean up resources used by the ecosystem."""
        if pygame.get_init():
            pygame.quit()
        if hasattr(self, "gif_process"):
            # Signal to stop the gif generation process
            self.frame_count_queue.put(None)

            self.gif_process.join()

    def spawn_critter(self) -> None:
        """Spawn a new critter in the ecosystem."""
        critter_type = random.choice([Frog, Bird, Snake])
        new_critter = critter_type(
            member_id=random.randint(1, 1000000),
            x=random.randint(0, self.width),
            y=self.height - 20,
            width=self.width,
            height=self.height,
        )
        new_critter.spawn()
        self.critters.append(new_critter)


class Button:
    """Represents a clickable button in the user interface."""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str,
        color: tuple[int, int, int],
        text_color: tuple[int, int, int],
        font: pygame.font.Font,
    ) -> None:
        """Initialize a Button.

        Args:
        ----
            x (int): X-coordinate of the button.
            y (int): Y-coordinate of the button.
            width (int): Width of the button.
            height (int): Height of the button.
            text (str): Text to display on the button.
            color (tuple[int, int, int]): Color of the button.
            text_color (tuple[int, int, int]): Color of the text.
            font (pygame.font.Font): Font for the button text.

        """
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.text_color = text_color
        self.font = font

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the button on the given surface.

        Args:
        ----
            surface (pygame.Surface): Surface to draw the button on.

        """
        pygame.draw.rect(surface, self.color, self.rect)
        text_surface = self.font.render(self.text, True, self.text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)

    def is_clicked(self, position: tuple[int, int]) -> bool:
        """Check if the button is clicked.

        Args:
        ----
            position (tuple[int, int]): Position of the mouse click.

        Returns:
        -------
            bool: True if the button is clicked, False otherwise.

        """
        return self.rect.collidepoint(position)


class EcosystemManager:
    """Manages the ecosystem simulation and handles user interactions."""

    def __init__(
        self,
        width: int = 1152,
        height: int = 648,
        generate_gifs: bool = False,
        fps: int = 30,
        interactive: bool = True,
    ) -> None:
        """Initialize the EcosystemManager.

        Args:
        ----
            width (int): Width of the ecosystem window.
            height (int): Height of the ecosystem window.
            generate_gifs (bool): Whether to generate GIFs of the simulation.
            fps (int): Frames per second for the simulation.
            interactive (bool): Whether the ecosystem is interactive or not.

        """
        self.width = width
        self.height = height
        self.generate_gifs = generate_gifs
        self.fps = fps
        self.interactive = interactive
        self.process = None
        self.command_queue = multiprocessing.Queue()
        self.gif_queue = multiprocessing.Queue()
        self.running = False

        self.user_frogs = {}
        self.last_activity = {}
        self.fake_user_ids = []

    def start(self, show_controls: bool = True) -> None:
        """Start the ecosystem simulation.

        Args:
        ----
            show_controls (bool): Whether to show UI controls.

        """
        if self.process and self.process.is_alive():
            return

        self.running = True

        def run_and_catch_exceptions(show_controls):
            try:
                self._run_ecosystem(show_controls)
            except Exception as e:
                print(f"Exception in _run_ecosystem: {e}")
                import traceback

                traceback.print_exc()

        self.process = multiprocessing.Process(target=run_and_catch_exceptions, args=(show_controls,))
        self.process.start()

    def stop(self) -> None:
        """Stop the ecosystem simulation."""
        self.running = False
        self.command_queue.put(("stop", None))
        if self.process:
            self.process.join()

    def _run_ecosystem(self, show_controls: bool) -> None:
        """Run the ecosystem simulation loop.

        Args:
        ----
            show_controls (bool): Whether to show UI controls.

        """
        print("Initializing Pygame")
        pygame.init()
        print("Pygame initialized")

        if self.interactive:
            screen = pygame.display.set_mode((self.width, self.height))
            pygame.display.set_caption(f"Ecosystem Visualization {multiprocessing.current_process().name}")
        else:
            pygame.display.set_mode((1, 1), pygame.HIDDEN)
            screen = pygame.Surface((self.width, self.height))

        ecosystem = Ecosystem(
            self.width, self.height, generate_gifs=self.generate_gifs, fps=self.fps, interactive=self.interactive
        )
        ecosystem.setup_ui()

        clock = pygame.time.Clock()

        last_message_time = time.time()
        message_interval = 2.0  # Send a message every 2 seconds

        if self.interactive:
            self._spawn_initial_critters(ecosystem)

        while self.running:
            delta = clock.tick(self.fps) / 1000.0

            if self.interactive:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif show_controls and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._handle_mouse_click(ecosystem, event.pos)

                # Simulate random messages
                current_time = time.time()
                if current_time - last_message_time >= message_interval:
                    self._simulate_random_message(ecosystem)
                    last_message_time = current_time

            ecosystem.update(delta)
            screen.blit(ecosystem.draw(), (0, 0))
            ecosystem.post_update()

            if self.interactive and show_controls:
                self._draw_controls(ecosystem, screen)

            if self.interactive:
                pygame.display.flip()

            if ecosystem.generate_gifs and not ecosystem.gif_info_queue.empty():
                gif_data, timestamp = ecosystem.gif_info_queue.get()
                self.gif_queue.put((gif_data, timestamp))

            while not self.command_queue.empty():
                command, args = self.command_queue.get()
                if command == "stop":
                    self.running = False
                elif command == "process_event":
                    self._process_event(ecosystem, args)
                elif command == "set_online_critters":
                    self._set_online_critters(ecosystem, args)

        pygame.quit()
        ecosystem.cleanup()

    def _handle_mouse_click(self, ecosystem: Ecosystem, pos: tuple[int, int]) -> None:
        """Handle mouse click events in the ecosystem.

        Args:
        ----
            ecosystem (Ecosystem): The ecosystem instance.
            pos (tuple[int, int]): Position of the mouse click.

        """
        if ecosystem.activity_slider.collidepoint(pos):
            ecosystem.activity = (pos[0] - ecosystem.activity_slider.x) / ecosystem.activity_slider.width
        elif ecosystem.spawn_critter_button.is_clicked(pos):
            ecosystem.spawn_critter()
        elif ecosystem.reset_button.is_clicked(pos):
            ecosystem.reset()

    def _draw_controls(self, ecosystem: Ecosystem, screen: pygame.Surface) -> None:
        """Draw UI controls on the screen.

        Args:
        ----
            ecosystem (Ecosystem): The ecosystem instance.
            screen (pygame.Surface): Surface to draw the controls on.

        """
        pygame.draw.rect(screen, (200, 200, 200), ecosystem.activity_slider)
        pygame.draw.rect(
            screen,
            (0, 255, 0),
            (
                ecosystem.activity_slider.x,
                ecosystem.activity_slider.y,
                ecosystem.activity_slider.width * ecosystem.activity,
                ecosystem.activity_slider.height,
            ),
        )

        ecosystem.spawn_critter_button.draw(screen)
        ecosystem.reset_button.draw(screen)

        activity_text = ecosystem.font.render(f"Activity: {ecosystem.activity:.2f}", True, (0, 0, 0))
        screen.blit(activity_text, (ecosystem.activity_slider.x, ecosystem.activity_slider.y - 20))

        stats_text = ecosystem.font.render(
            f"Critters: {len(ecosystem.critters)}",
            True,
            (0, 0, 0),
        )
        screen.blit(stats_text, (25, ecosystem.activity_slider.y + 70))

    def process_event(self, event: DiscordEvent, user_info: UserInfo) -> None:
        """Process a Discord event in the ecosystem.

        Args:
        ----
            event (DiscordEvent): The Discord event to process.
            user_info (UserInfo): User information including avatar and role color.

        """
        self.command_queue.put(("process_event", (event, user_info)))

    def _process_event(self, ecosystem: Ecosystem, event_data: tuple[DiscordEvent, UserInfo]) -> None:
        """Process a Discord event within the ecosystem process.

        Args:
        ----
            ecosystem (Ecosystem): The ecosystem instance.
            event_data (tuple[DiscordEvent, UserInfo]): The Discord event and user info to process.

        """
        event, user_info = event_data
        current_time = time.time()
        user_id = event.member.id

        if event.type in ("TYPING", "MESSAGE"):
            self._handle_user_activity(ecosystem, user_id, current_time, event.type == "TYPING", user_info)

            if event.type == "MESSAGE":
                critter = self.user_frogs.get(user_id)
                if critter:
                    speech_bubble = SpeechBubble(critter, event.content, duration=5, bg_color=user_info.role_color)
                    ecosystem.speech_bubbles.append(speech_bubble)

        self._remove_inactive_users(ecosystem, current_time)

    def _handle_user_activity(
        self, ecosystem: Ecosystem, user_id: int, current_time: float, is_typing: bool, user_info: UserInfo
    ) -> None:
        """Handle user activity in the ecosystem.

        Args:
        ----
            ecosystem (Ecosystem): The ecosystem instance.
            user_id (int): ID of the user.
            current_time (float): Current timestamp.
            is_typing (bool): Whether the user is typing.
            user_info (UserInfo): User information including avatar and role color.

        """
        if user_id not in self.user_frogs:
            self._spawn_new_critter(ecosystem, user_id, user_info)
        elif is_typing:
            self.user_frogs[user_id].move()

        self.last_activity[user_id] = current_time
        self._remove_inactive_users(ecosystem, current_time)

    def set_online_critters(self, online_members: list[UserInfo]) -> None:
        """Set the online critters based on the list of online members' info.

        Args:
        ----
            online_members (List[UserInfo]): List of UserInfo objects for online members.

        """
        self.command_queue.put(("set_online_critters", online_members))

    def _set_online_critters(self, ecosystem: Ecosystem, online_members: list[UserInfo]) -> None:
        """Set the online critters within the ecosystem process.

        Args:
        ----
            ecosystem (Ecosystem): The ecosystem instance.
            online_members (List[UserInfo]): List of UserInfo objects for online members.

        """
        for user_info in online_members:
            self._spawn_new_critter(ecosystem, user_info.user_id, user_info)
            print(f"{user_info.user_id}'s critter spawned")

    def _spawn_new_critter(self, ecosystem: Ecosystem, user_id: int, user_info: UserInfo | None = None) -> None:
        if user_id not in self.user_frogs:
            critter_type = random.choice([Frog, Bird, Snake])

            avatar_data = user_info.avatar_data if user_info else None

            critter = critter_type(
                user_id,
                random.randint(0, ecosystem.width),
                ecosystem.height - 20,
                ecosystem.width,
                ecosystem.height,
                avatar=avatar_data,
            )
            critter.spawn()
            self.user_frogs[user_id] = critter
            ecosystem.critters.append(critter)

    def _remove_inactive_users(self, ecosystem: Ecosystem, current_time: float) -> None:
        """Remove inactive users from the ecosystem.

        Args:
        ----
            ecosystem (Ecosystem): The ecosystem instance.
            current_time (float): Current timestamp.

        """
        one_minute = 60
        inactive_users = [
            user_id for user_id, last_time in self.last_activity.items() if current_time - last_time > one_minute
        ]
        for user_id in inactive_users:
            self._remove_critter(ecosystem, user_id)

    def _remove_critter(self, ecosystem: Ecosystem, user_id: int) -> None:
        if user_id in self.user_frogs:
            critter = self.user_frogs.pop(user_id)
            ecosystem.critters.discard(critter)
        self.last_activity.pop(user_id, None)

    def get_latest_gif(self) -> tuple[bytes, float] | None:
        """Get the latest generated GIF.

        Returns
        -------
            tuple[bytes, float] | None: Tuple containing GIF data and timestamp, or None if no GIF is available.

        """
        if not self.gif_queue.empty():
            return self.gif_queue.get()
        return None

    def _spawn_initial_critters(self, ecosystem: Ecosystem) -> None:
        num_critters = random.randint(5, 15)  # Spawn between 5 and 15 critters
        for _ in range(num_critters):
            user_id = random.randint(1, 1000000)
            self.fake_user_ids.append(user_id)
            self._spawn_new_critter(ecosystem, user_id)

    async def _simulate_random_message(self, ecosystem: Ecosystem) -> None:
        if not self.fake_user_ids:
            return

        guild_id = random.randint(1, 1000000)
        channel_id = random.randint(1, 1000000)

        async def simulate():
            db = Database("ecocord")
            await db.initialize()
            user_info = await db.get_random_user_info(guild_id)

            if user_info:
                content = "Hello, ecosystem!"
                event = DiscordEvent(
                    type="MESSAGE",
                    content=content,
                    timestamp=datetime.now(UTC),
                    guild=SerializableGuild(guild_id, "Simulated Guild", 0),
                    channel=SerializableTextChannel(channel_id, "simulated-channel"),
                    member=SerializableMember(
                        user_info.user_id,
                        f"SimulatedUser_{user_info.user_id}",
                        f"SimulatedUser_{user_info.user_id}",
                        guild_id,
                        user_info.avatar_data,
                        user_info.role_color,
                    ),
                )
                self._process_event(ecosystem, (event, user_info))
            else:
                print("No user info found in the database.")

        await simulate()
