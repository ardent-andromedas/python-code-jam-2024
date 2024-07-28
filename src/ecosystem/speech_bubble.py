from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from .critter import Critter


class SpeechBubble:
    """A class representing a speech bubble for a critter."""

    def __init__(
        self,
        critter: Critter,
        content: str,
        duration: float = 5.0,
        bg_color: str = "#FFFFFF",
        text_color: tuple[int, int, int] = (0, 0, 0),
        border_color: tuple[int, int, int] = (0, 0, 0),
        font_size: int = 28,
        padding: int = 20,
        border_radius: int = 20,
        max_width: int = 400,
    ) -> None:
        """Initialize the SpeechBubble."""
        self.critter = critter
        self.content = content
        self.duration = duration
        self.creation_time = time.time()
        self.bg_color = self.hex_to_rgb(bg_color)
        self.text_color = text_color
        self.border_color = border_color
        self.font_size = font_size
        self.padding = padding
        self.border_radius = border_radius
        self.max_width = max_width
        self.opacity = 51

        self.font = pygame.font.Font(None, font_size)
        self.surface = None
        self.position = (self.critter.x, self.critter.y)
        self._create_surface()

    def hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Convert hex color string to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def _create_surface(self) -> None:
        words = self.content.split()
        lines = []
        current_line = []
        for word in words:
            test_line = " ".join([*current_line, word])
            if self.font.size(test_line)[0] <= self.max_width - 2 * self.padding:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))

        text_surfaces = [self.font.render(line, True, self.text_color) for line in lines]
        max_width = max(surface.get_width() for surface in text_surfaces)
        total_height = sum(surface.get_height() for surface in text_surfaces)

        self.bubble_body = pygame.Surface(
            (max_width + 2 * self.padding, total_height + 2 * self.padding), pygame.SRCALPHA
        )
        pygame.draw.rect(
            self.bubble_body,
            (*self.bg_color, self.opacity),
            self.bubble_body.get_rect(),
            border_radius=self.border_radius,
        )

        y_offset = self.padding
        for surface in text_surfaces:
            self.bubble_body.blit(surface, (self.padding, y_offset))
            y_offset += surface.get_height()

        self._draw_bubble()

    def _draw_bubble(self) -> None:
        bubble_width, bubble_height = self.bubble_body.get_size()

        self.surface = pygame.Surface((bubble_width, bubble_height), pygame.SRCALPHA)

        bubble_rect = pygame.Rect(0, 0, bubble_width, bubble_height)
        pygame.draw.rect(self.surface, (*self.bg_color, self.opacity), bubble_rect, border_radius=self.border_radius)

        pygame.draw.rect(self.surface, self.border_color, bubble_rect, width=2, border_radius=self.border_radius)

        self.surface.blit(self.bubble_body, (0, 0))

    def update(self, delta: float) -> None:
        critter_x, critter_y = self.critter.x, self.critter.y
        bubble_width, bubble_height = self.surface.get_size()
        screen_width, screen_height = pygame.display.get_surface().get_size()

        x = critter_x - bubble_width // 2
        y = critter_y - bubble_height - 20

        x = max(0, min(x, screen_width - bubble_width))
        y = max(0, min(y, screen_height - bubble_height))

        self.position = (x, y)

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.surface, self.position)

    def is_expired(self) -> bool:
        return time.time() - self.creation_time > self.duration
