"""UI 元件：HealthBar、TextButton、ScreenFade"""
import pygame

from .constants import (
    BLACK, DARK_GRAY, GREEN, RED, SCREEN_HEIGHT, SCREEN_WIDTH, WHITE,
)


class HealthBar:
    def __init__(self, x, y, max_health):
        self.x = x
        self.y = y
        self.max_health = max_health

    def draw(self, surface, health):
        ratio = max(0, health / self.max_health)
        pygame.draw.rect(surface, BLACK, (self.x - 2, self.y - 2, 154, 24))
        pygame.draw.rect(surface, RED, (self.x, self.y, 150, 20))
        pygame.draw.rect(surface, GREEN, (self.x, self.y, int(150 * ratio), 20))


class TextButton:
    def __init__(self, x, y, text, font, w=220, h=60):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.font = font
        self.clicked = False

    def draw(self, surface):
        pygame.draw.rect(surface, DARK_GRAY, self.rect)
        pygame.draw.rect(surface, WHITE, self.rect, 2)
        img = self.font.render(self.text, True, WHITE)
        surface.blit(img, img.get_rect(center=self.rect.center))

    def is_click(self, mouse_pos=None, pressed=None):
        action = False
        pos = mouse_pos if mouse_pos is not None else pygame.mouse.get_pos()
        if pressed is None:
            pressed = pygame.mouse.get_pressed()[0]
        if self.rect.collidepoint(pos):
            if pressed and not self.clicked:
                self.clicked = True
                action = True
        if not pressed:
            self.clicked = False
        return action


class ScreenFade:
    def __init__(self, color, speed):
        self.color = color
        self.speed = speed
        self.counter = 0

    def reset(self):
        self.counter = 0

    def fade_in(self, surface):
        """從中央向外打開 (黑→透)"""
        c = self.counter
        pygame.draw.rect(surface, self.color, (0 - c, 0, SCREEN_WIDTH // 2, SCREEN_HEIGHT))
        pygame.draw.rect(surface, self.color, (SCREEN_WIDTH // 2 + c, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.draw.rect(surface, self.color, (0, 0 - c, SCREEN_WIDTH, SCREEN_HEIGHT // 2))
        pygame.draw.rect(surface, self.color, (0, SCREEN_HEIGHT // 2 + c, SCREEN_WIDTH, SCREEN_HEIGHT))
        self.counter += self.speed
        return self.counter >= SCREEN_HEIGHT

    def fade_out(self, surface):
        """從上往下覆蓋"""
        pygame.draw.rect(surface, self.color, (0, 0, SCREEN_WIDTH, self.counter))
        self.counter += self.speed
        return self.counter >= SCREEN_HEIGHT
