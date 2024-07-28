import io
import random

import pygame
from pygame import Color, Surface, Vector2

from ecosystem.critter import Critter


class Snake(Critter):
    """Represents a snake in the ecosystem.

    The snake moves towards a target, grows in length, and can spawn or despawn.
    """

    def __init__(self, member_id: int, x: int, y: int, width: int, height: int, avatar=None) -> None:
        """Initialize a new Snake instance.

        Args:
        ----
            member_id (int): The unique identifier for the snake.
            x (int): Initial x-coordinate of the snake's head.
            y (int): Initial y-coordinate of the snake's head.
            width (int): Width of the game area.
            height (int): Height of the game area.
            avatar (bytes): The avatar data for the snake.

        """
        super().__init__(member_id, x, y, width, height)
        self.segments = [Vector2(x, y)]
        self.direction = Vector2(1, 0)
        self.min_y = int(self.height * 0.65)
        self.max_y = int(self.height * 0.80)
        self.speed = 2
        self.length = 50
        self.color = self.generate_color()
        self.target = self.get_new_target()
        self.state = "inactive"
        self.scale = 0.1

        self.avatar = avatar
        self.avatar_surface = None
        if self.avatar:
            try:
                avatar_io = io.BytesIO(self.avatar)
                avatar_image = pygame.image.load(avatar_io)
                self.avatar_surface = pygame.transform.scale(avatar_image, (64, 64)).convert_alpha()
            except Exception as e:
                print(f"Failed to create avatar surface for frog {member_id}: {e}")

    def generate_color(self) -> Color:
        """Generate a random color for the snake.

        Returns
        -------
            Color: A pygame Color object with random RGB values.

        """
        return pygame.Color(random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))

    def get_new_target(self) -> Vector2:
        """Generate a new random target position for the snake.

        Returns
        -------
            Vector2: A new target position within the game area.

        """
        return Vector2(random.randint(0, self.width), random.randint(self.min_y, self.max_y))

    def update(self, delta: float, activity: float) -> None:
        """Update the snake's position and state.

        Args:
        ----
            delta (float): Time elapsed since the last update.
            activity (float): Activity level affecting the snake's speed.

        """
        if self.state == "inactive":
            return

        if self.state == "spawn":
            self.scale = min(1.0, self.scale + delta)
            if self.scale == 1.0:
                self.state = "active"
        elif self.state == "despawn":
            self.scale = max(0.0, self.scale - delta)
            if self.scale == 0.0:
                self.alive = False
                self.state = "inactive"
                return

        head = self.segments[0]
        to_target = self.target - head
        if to_target.length() < 10:
            self.target = self.get_new_target()

        to_target = self.target - head
        self.direction = to_target.normalize()
        new_head = head + self.direction * self.speed * activity * delta * 60

        new_head.y = max(min(new_head.y, self.max_y), self.min_y)

        self.segments.insert(0, new_head)
        if len(self.segments) > self.length:
            self.segments.pop()

    def draw(self, surface: Surface) -> None:
        """Draw the snake on the given surface.

        Args:
        ----
            surface (Surface): The pygame Surface to draw on.

        """
        for i, segment in enumerate(self.segments):
            radius = int((10 * (1 - i / len(self.segments)) + 5) * self.scale)
            alpha = int(255 * (1 - i / len(self.segments)))
            color = (self.color.r, self.color.g, self.color.b, alpha)

            # Create a surface for the snake segment
            segment_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)

            # Draw the avatar with 50% opacity if available
            if self.avatar_surface:
                avatar_scaled = pygame.transform.scale(self.avatar_surface, (radius * 2, radius * 2))
                avatar_scaled.set_alpha(128)  # 50% opacity
                segment_surface.blit(avatar_scaled, (0, 0))

            # Draw the snake segment shape
            pygame.draw.circle(segment_surface, color, (radius, radius), radius)

            # Create a mask from the segment shape
            mask = pygame.mask.from_surface(segment_surface)
            mask_surface = mask.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0))

            # Combine the avatar and the segment shape using the mask
            segment_surface.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            # Draw the combined segment surface on the main surface
            surface.blit(segment_surface, (int(segment.x - radius), int(segment.y - radius)))

        head = self.segments[0]
        eye_offset = self.direction.normalize() * 8 * self.scale
        left_eye = head + eye_offset.rotate(90)
        right_eye = head + eye_offset.rotate(-90)

        eye_radius = int(4 * self.scale)
        pupil_radius = int(2 * self.scale)
        pygame.draw.circle(surface, (255, 255, 255), (int(left_eye.x), int(left_eye.y)), eye_radius)
        pygame.draw.circle(surface, (255, 255, 255), (int(right_eye.x), int(right_eye.y)), eye_radius)
        pygame.draw.circle(surface, (0, 0, 0), (int(left_eye.x), int(left_eye.y)), pupil_radius)
        pygame.draw.circle(surface, (0, 0, 0), (int(right_eye.x), int(right_eye.y)), pupil_radius)

    def activate(self) -> None:
        self.state = "spawn"
        self.scale = 0.1

    def deactivate(self) -> None:
        self.state = "despawn"

    def spawn(self) -> None:
        self.alive = True
        self.activate()
        self.segments = [Vector2(random.randint(0, self.width), random.randint(self.min_y, self.max_y))]
        self.color = self.generate_color()

    def despawn(self) -> None:
        self.deactivate()
