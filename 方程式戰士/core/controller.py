"""方程式控制器：keydown 進 aiming，update 算參數，keyup 發射"""
import math
import pygame

from .constants import RED, SCREEN_HEIGHT, SCREEN_WIDTH, YELLOW
from .enums import AimState, PlayerMode, PowerType
from .equation import Equation
from .gameplay import degree_to_fire_power
from .projectile import MathProjectile


class EquationController:
    PREVIEW_RANGE_PX = 180     # 只畫這麼長的曲線 (讓玩家算)
    PREVIEW_STEP_PX = 4
    LINEAR_VERTICAL_EPS = 1.0  # |dx| < 此值 → 視為垂直 (顯示用)
    QUAD_H_MIN = 5             # |h| 下限，防 a = -k/h² 爆炸
    QUAD_A_INIT = 0.0
    COOLDOWN_MS = 300
    MOUSE_QUANTIZE = 8         # 滑鼠量化到 8px 格 → 抗抖動 (顯示與曲線都穩)

    FUNCTION_AIM_KEY = pygame.K_1

    def __init__(self, player, projectile_group):
        self.player = player
        self.projectile_group = projectile_group
        self.state = AimState.IDLE
        self.power = None
        self.aim_key = None

        # LINEAR：vector 運動
        self.linear_dx = 1.0
        self.linear_dy = 0.0

        # QUADRATIC：mouse=頂點，a 由「過玩家」約束算
        self.quad_a = self.QUAD_A_INIT
        self.quad_h = 0.0
        self.quad_k = 0.0

        self.facing = 1
        self.last_fire_time = -10000
        self.cubic_msg_until = 0
        self.degree_zero_msg_until = 0

    def _player_degree(self) -> int:
        return int(getattr(self.player, "polynomial_degree", 1))

    # ---- 事件 ----
    def force_idle(self):
        if self.state == AimState.AIMING:
            self._clear_aiming()

    def on_keydown(self, key):
        if getattr(self.player, "game_mode", PlayerMode.FUNCTION) != PlayerMode.FUNCTION:
            return
        if key != self.FUNCTION_AIM_KEY:
            return
        deg = self._player_degree()
        if deg == 3:
            self.cubic_msg_until = pygame.time.get_ticks() + 1500
            return
        if deg == 0:
            self.degree_zero_msg_until = pygame.time.get_ticks() + 1500
        if self.state == AimState.AIMING and self.aim_key == key:
            return
        if pygame.time.get_ticks() - self.last_fire_time < self.COOLDOWN_MS:
            return
        self.power = degree_to_fire_power(deg)
        self.aim_key = key
        self.state = AimState.AIMING
        self.player.is_aiming = True

    def on_keyup(self, key):
        if getattr(self.player, "game_mode", PlayerMode.FUNCTION) != PlayerMode.FUNCTION:
            return
        if self.state != AimState.AIMING or key != self.aim_key:
            return
        if self.power is None:
            # 次方 0：僅啵聲，無子彈
            if hasattr(self.player, "request_pop_sound"):
                self.player.request_pop_sound()
            self._clear_aiming()
            self.last_fire_time = pygame.time.get_ticks()
            return
        self.fire()
        self._clear_aiming()

    def _clear_aiming(self):
        self.state = AimState.IDLE
        self.power = None
        self.aim_key = None
        self.player.is_aiming = False

    def on_mousewheel(self, y_delta):
        # 次方由塊碰自機決定 → 瞄準中滾輪不改 a
        return

    # ---- 每 frame 更新 ----
    def update(self, mouse_pos=None):
        if self.state != AimState.AIMING:
            return
        if self.power is None:
            return
        if mouse_pos is None:
            mx, my = pygame.mouse.get_pos()
        else:
            mx, my = mouse_pos
        px, py = self.player.rect.center
        dx_world = mx - px
        dy_world = -(my - py)  # 螢幕 y 反向 → 數學慣例

        q = self.MOUSE_QUANTIZE
        dx_world = round(dx_world / q) * q
        dy_world = round(dy_world / q) * q

        if self.power == PowerType.LINEAR:
            if dx_world == 0 and dy_world == 0:
                self.linear_dx, self.linear_dy = 1.0, 0.0
            else:
                self.linear_dx = float(dx_world)
                self.linear_dy = float(dy_world)
            self.facing = 1 if self.linear_dx >= 0 else -1
        elif self.power == PowerType.QUADRATIC:
            h = float(dx_world)
            k = float(dy_world)
            if abs(h) < self.QUAD_H_MIN:
                h = self.QUAD_H_MIN if h >= 0 else -self.QUAD_H_MIN
            self.quad_h = h
            self.quad_k = k
            self.quad_a = -k / (h * h)
            self.facing = 1 if self.quad_h >= 0 else -1
        self.player.facing = self.facing

    def current_params(self):
        if self.power == PowerType.LINEAR:
            if abs(self.linear_dx) < self.LINEAR_VERTICAL_EPS:
                return {'a': 0.0, 'vertical': True}
            return {'a': self.linear_dy / self.linear_dx, 'vertical': False}
        if self.power == PowerType.QUADRATIC:
            return {'a': self.quad_a, 'h': self.quad_h, 'k': self.quad_k}
        return {}

    def _linear_unit_dir(self):
        """LINEAR 的單位向量 (dx_norm, dy_norm)，垂直情況也 OK"""
        norm = math.hypot(self.linear_dx, self.linear_dy)
        if norm == 0:
            return (1.0, 0.0)
        return (self.linear_dx / norm, self.linear_dy / norm)

    def fire(self):
        if self.power not in (PowerType.LINEAR, PowerType.QUADRATIC):
            return
        direction = self._linear_unit_dir() if self.power == PowerType.LINEAR else None
        healing = bool(getattr(self.player, "heal_sigmoid_active", False))
        proj = MathProjectile(
            origin=self.player.rect.center,
            power=self.power,
            params=self.current_params(),
            facing=self.facing,
            direction=direction,
            healing_shot=healing,
        )
        self.projectile_group.add(proj)
        self.last_fire_time = pygame.time.get_ticks()
        from . import game_audio

        game_audio.play_shot(at_rect=self.player.rect)

    # ---- 繪製 ----
    def draw_preview(self, surface, world=None):
        if self.state != AimState.AIMING or self.power is None:
            return
        points = []
        if self.power == PowerType.LINEAR:
            dx_n, dy_n = self._linear_unit_dir()
            steps = self.PREVIEW_RANGE_PX // self.PREVIEW_STEP_PX
            for i in range(steps):
                t = i * self.PREVIEW_STEP_PX
                sx = int(self.player.rect.centerx + t * dx_n)
                sy = int(self.player.rect.centery - t * dy_n)
                if self._point_blocked(sx, sy, world):
                    break
                points.append((sx, sy))
        else:  # QUADRATIC
            params = self.current_params()
            for px_step in range(0, self.PREVIEW_RANGE_PX, self.PREVIEW_STEP_PX):
                world_x = px_step * self.facing
                world_y = Equation.evaluate(self.power, params, world_x)
                sx = int(self.player.rect.centerx + world_x)
                sy = int(self.player.rect.centery - world_y)
                if self._point_blocked(sx, sy, world):
                    break
                points.append((sx, sy))

        if len(points) >= 2:
            preview = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            pygame.draw.lines(preview, (255, 230, 80, 200), False, points, 3)
            end = points[-1]
            pygame.draw.circle(preview, (255, 230, 80, 200), end, 5)
            surface.blit(preview, (0, 0))

    @staticmethod
    def _point_blocked(x, y, world):
        if x < 0 or x >= SCREEN_WIDTH or y < 0 or y >= SCREEN_HEIGHT:
            return True
        if world is None:
            return False
        for _img, rect in world.obstacle_list:
            if rect.collidepoint(x, y):
                return True
        return False

    def draw_polynomial_center_msg(self, surface, font):
        """次方 0／3 於螢幕中央提示（與三次方 TODO 相同位置）。"""
        from .enums import PlayerMode

        if getattr(self.player, "game_mode", None) != PlayerMode.FUNCTION:
            return
        now = pygame.time.get_ticks()
        deg = self._player_degree()
        msg = None
        color = RED
        if deg == 3 and now < self.cubic_msg_until:
            msg = "Cubic (deg 3): TODO 尚未實作"
            color = RED
        elif deg == 0:
            msg = "次方 0：啵（無彈道，按住 1 發射）"
            color = YELLOW
        if msg is None:
            return
        text = font.render(msg, True, color)
        rect = text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 100))
        surface.blit(text, rect)


class EquationDisplay:
    def __init__(self, font_eq):
        self.font = font_eq

    def draw(self, surface, controller):
        deg = int(getattr(controller.player, "polynomial_degree", 1))
        if controller.state == AimState.AIMING and controller.power is not None:
            text = Equation.format_str(controller.power, controller.current_params())
            color = YELLOW
        elif controller.state == AimState.AIMING and controller.power is None:
            text = "deg 0: 放開發射「啵」（無彈道）"
            color = YELLOW
        else:
            text = (
                f"[1] 函數圖形  次方={deg}  "
                f"(0=啵 1=線性 2=拋物 3=三次TODO；次方僅能靠微／積分塊碰自己)"
            )
            color = (200, 200, 200)
        img = self.font.render(text, True, color)
        rect = img.get_rect(midbottom=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 12))
        bg = pygame.Surface((rect.width + 24, rect.height + 10), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 190))
        surface.blit(bg, (rect.x - 12, rect.y - 5))
        surface.blit(img, rect)
