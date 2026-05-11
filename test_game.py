"""方程式戰士 unit tests

跑法：
    cd 方程式戰士
    python -m unittest test_game.py -v

或：
    python test_game.py

注意：用 SDL_VIDEODRIVER=dummy 避免測試時開啟視窗。
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import unittest
import math
import pygame
from unittest.mock import MagicMock

pygame.init()
pygame.display.set_mode((1, 1))  # MathProjectile 需要 display 才能 convert_alpha

import game
from game import (
    PowerType, AimState, Equation, EquationController,
    MathProjectile, Player, Enemy, World, PlayerMode,
    clamp_degree, degree_to_fire_power, placement_zone_left_third, round_hp,
    build_sigma_shot_schedule,
    sigmoid_heal_from_damage,
)


class TestEquationEvaluate(unittest.TestCase):
    """Equation.evaluate 數值正確性"""

    def test_linear_basic(self):
        self.assertEqual(Equation.evaluate(PowerType.LINEAR, {'a': 2}, 5), 10)
        self.assertEqual(Equation.evaluate(PowerType.LINEAR, {'a': -1}, 7), -7)
        self.assertEqual(Equation.evaluate(PowerType.LINEAR, {'a': 0.5}, 10), 5)

    def test_linear_zero(self):
        self.assertEqual(Equation.evaluate(PowerType.LINEAR, {'a': 3}, 0), 0)

    def test_quadratic_vertex_at_origin(self):
        # f(x) = a x^2，頂點在原點
        params = {'a': 1, 'h': 0, 'k': 0}
        self.assertEqual(Equation.evaluate(PowerType.QUADRATIC, params, 3), 9)
        self.assertEqual(Equation.evaluate(PowerType.QUADRATIC, params, -2), 4)

    def test_quadratic_shifted_vertex(self):
        # f(x) = 0.5(x - 100)^2 + 50
        params = {'a': 0.5, 'h': 100, 'k': 50}
        # 頂點處
        self.assertEqual(Equation.evaluate(PowerType.QUADRATIC, params, 100), 50)
        # 偏離頂點 10
        self.assertEqual(
            Equation.evaluate(PowerType.QUADRATIC, params, 110),
            0.5 * 100 + 50,
        )
        # x = 0
        self.assertEqual(
            Equation.evaluate(PowerType.QUADRATIC, params, 0),
            0.5 * 10000 + 50,
        )

    def test_cubic_returns_zero_for_now(self):
        # 三次函數預留，當前回 0
        self.assertEqual(Equation.evaluate(PowerType.CUBIC, {'a': 1}, 5), 0)


class TestEquationFormatStr(unittest.TestCase):
    def test_linear_format(self):
        s = Equation.format_str(PowerType.LINEAR, {'a': 2.5})
        self.assertIn("2.50", s)
        self.assertIn("x", s)

    def test_linear_negative_a(self):
        s = Equation.format_str(PowerType.LINEAR, {'a': -1.23})
        self.assertIn("-1.23", s)

    def test_quadratic_format_includes_vertex(self):
        s = Equation.format_str(PowerType.QUADRATIC, {'a': 0.5, 'h': 100, 'k': -30})
        self.assertIn("0.500", s)
        # h = 100 → "x - 100"
        self.assertIn("100", s)
        # k = -30 → "- 30"
        self.assertIn("- 30", s)

    def test_cubic_format_says_todo(self):
        s = Equation.format_str(PowerType.CUBIC, {})
        self.assertIn("TODO", s)


class TestGameplayHelpers(unittest.TestCase):
    def test_round_hp_two_decimals(self):
        self.assertEqual(round_hp(9.999), 10.0)
        self.assertEqual(round_hp(3.14159), 3.14)

    def test_clamp_degree(self):
        self.assertEqual(clamp_degree(-5), 0)
        self.assertEqual(clamp_degree(5), 3)

    def test_degree_to_fire_power(self):
        self.assertIsNone(degree_to_fire_power(0))
        self.assertEqual(degree_to_fire_power(1), PowerType.LINEAR)
        self.assertEqual(degree_to_fire_power(2), PowerType.QUADRATIC)
        self.assertIsNone(degree_to_fire_power(3))

    def test_placement_zone_left_third(self):
        x, y, w, h = placement_zone_left_third(800, 640)
        self.assertEqual((x, y), (0, 0))
        self.assertEqual(w, 533)
        self.assertEqual(h, 640)


class TestEquationControllerStateMachine(unittest.TestCase):
    """EquationController 的 IDLE ↔ AIMING 狀態切換"""

    def setUp(self):
        # 模擬 player：只需要 rect.center, is_aiming
        self.player = MagicMock()
        self.player.rect = pygame.Rect(0, 0, 40, 40)
        self.player.rect.center = (400, 320)
        self.player.is_aiming = False
        self.player.polynomial_degree = 1
        self.player.game_mode = PlayerMode.FUNCTION
        self.proj_group = pygame.sprite.Group()
        self.ctrl = EquationController(self.player, self.proj_group)

    def test_initial_state_is_idle(self):
        self.assertEqual(self.ctrl.state, AimState.IDLE)
        self.assertIsNone(self.ctrl.power)

    def test_keydown_1_enters_aiming_linear(self):
        self.ctrl.on_keydown(pygame.K_1)
        self.assertEqual(self.ctrl.state, AimState.AIMING)
        self.assertEqual(self.ctrl.power, PowerType.LINEAR)
        self.assertTrue(self.player.is_aiming)

    def test_keydown_1_enters_aiming_quadratic_when_degree_2(self):
        self.player.polynomial_degree = 2
        self.ctrl.on_keydown(pygame.K_1)
        self.assertEqual(self.ctrl.state, AimState.AIMING)
        self.assertEqual(self.ctrl.power, PowerType.QUADRATIC)

    def test_keydown_1_degree_3_does_not_enter_aiming(self):
        self.player.polynomial_degree = 3
        self.ctrl.on_keydown(pygame.K_1)
        self.assertEqual(self.ctrl.state, AimState.IDLE)

    def test_degree_zero_aiming_pop_no_projectile(self):
        self.player.polynomial_degree = 0
        pops = []
        self.player.request_pop_sound = lambda: pops.append(1)
        self.ctrl.on_keydown(pygame.K_1)
        self.assertEqual(self.ctrl.state, AimState.AIMING)
        self.assertIsNone(self.ctrl.power)
        self.ctrl.on_keyup(pygame.K_1)
        self.assertEqual(self.ctrl.state, AimState.IDLE)
        self.assertEqual(len(pops), 1)
        self.assertEqual(len(self.proj_group), 0)

    def test_keyup_returns_to_idle_and_fires(self):
        self.ctrl.on_keydown(pygame.K_1)
        # 模擬有 mouse pos 讓 update 算出 a
        self.ctrl.update(mouse_pos=(500, 320))
        self.ctrl.on_keyup(pygame.K_1)
        self.assertEqual(self.ctrl.state, AimState.IDLE)
        self.assertIsNone(self.ctrl.power)
        self.assertFalse(self.player.is_aiming)
        self.assertEqual(len(self.proj_group), 1)  # 發射了一發


class TestEquationControllerLinearAiming(unittest.TestCase):
    """LINEAR 模式下：直接指向滑鼠（vector 運動），垂直情況也要對"""

    def setUp(self):
        self.player = MagicMock()
        self.player.rect = pygame.Rect(0, 0, 40, 40)
        self.player.rect.center = (400, 320)
        self.player.is_aiming = False
        self.player.polynomial_degree = 1
        self.player.game_mode = PlayerMode.FUNCTION
        self.ctrl = EquationController(self.player, pygame.sprite.Group())
        self.ctrl.on_keydown(pygame.K_1)

    def test_mouse_right_above_player_slope_positive(self):
        # mouse 在玩家右上 → facing=+1, slope = dy/dx > 0
        self.ctrl.update(mouse_pos=(500, 220))
        self.assertEqual(self.ctrl.facing, 1)
        params = self.ctrl.current_params()
        self.assertFalse(params['vertical'])
        self.assertGreater(params['a'], 0)

    def test_mouse_right_below_player_slope_negative(self):
        self.ctrl.update(mouse_pos=(500, 420))
        self.assertEqual(self.ctrl.facing, 1)
        params = self.ctrl.current_params()
        self.assertLess(params['a'], 0)

    def test_mouse_left_decides_facing(self):
        self.ctrl.update(mouse_pos=(300, 220))
        self.assertEqual(self.ctrl.facing, -1)

    def test_horizontal_when_mouse_at_player_height(self):
        # 滑鼠跟玩家同高 → 純水平，slope = 0
        self.ctrl.update(mouse_pos=(500, 320))
        params = self.ctrl.current_params()
        self.assertFalse(params['vertical'])
        self.assertAlmostEqual(params['a'], 0)

    def test_vertical_when_mouse_directly_above(self):
        # 滑鼠在玩家正上方 → vertical 旗標亮起，不會 div by zero
        self.ctrl.update(mouse_pos=(400, 100))
        params = self.ctrl.current_params()
        self.assertTrue(params['vertical'])
        # 單位向量應該是純 y 方向
        dx_n, dy_n = self.ctrl._linear_unit_dir()
        self.assertAlmostEqual(dx_n, 0)
        self.assertAlmostEqual(dy_n, 1)

    def test_vertical_when_mouse_directly_below(self):
        self.ctrl.update(mouse_pos=(400, 600))
        params = self.ctrl.current_params()
        self.assertTrue(params['vertical'])
        dx_n, dy_n = self.ctrl._linear_unit_dir()
        self.assertAlmostEqual(dx_n, 0)
        self.assertAlmostEqual(dy_n, -1)

    def test_unit_vector_is_normalized(self):
        # 任意方向 → 單位向量 norm = 1
        self.ctrl.update(mouse_pos=(550, 220))
        dx_n, dy_n = self.ctrl._linear_unit_dir()
        norm = (dx_n ** 2 + dy_n ** 2) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=6)


class TestEquationControllerQuadraticAiming(unittest.TestCase):
    """QUADRATIC 模式：mouse 設頂點，scroll 設 a"""

    def setUp(self):
        self.player = MagicMock()
        self.player.rect = pygame.Rect(0, 0, 40, 40)
        self.player.rect.center = (400, 320)
        self.player.is_aiming = False
        self.player.polynomial_degree = 2
        self.player.game_mode = PlayerMode.FUNCTION
        self.ctrl = EquationController(self.player, pygame.sprite.Group())
        self.ctrl.on_keydown(pygame.K_1)

    def test_mouse_xy_sets_vertex(self):
        # mouse 完全控制頂點 (h, k)。注意：MOUSE_QUANTIZE=8 → 用 8 倍數
        self.ctrl.update(mouse_pos=(496, 224))  # dx=96, dy_world=96
        self.assertEqual(self.ctrl.quad_h, 96)
        self.assertEqual(self.ctrl.quad_k, 96)

    def test_mouse_y_below_player_negative_k(self):
        self.ctrl.update(mouse_pos=(496, 496))
        self.assertLess(self.ctrl.quad_k, 0)

    def test_a_auto_computed_from_constraint(self):
        # a = -k / h^2 (確保曲線通過玩家)
        self.ctrl.update(mouse_pos=(496, 224))  # h=96, k=96
        self.assertAlmostEqual(self.ctrl.quad_a, -96 / (96 * 96))

    def test_curve_passes_through_player(self):
        # 數學保證：f(0) = 0，子彈從玩家飛出
        self.ctrl.update(mouse_pos=(500, 220))
        params = self.ctrl.current_params()
        y_at_player = Equation.evaluate(PowerType.QUADRATIC, params, 0)
        self.assertAlmostEqual(y_at_player, 0)

    def test_curve_vertex_at_mouse(self):
        # 數學保證：f(h) = k，曲線頂點剛好在滑鼠
        self.ctrl.update(mouse_pos=(500, 220))
        params = self.ctrl.current_params()
        y_at_h = Equation.evaluate(PowerType.QUADRATIC, params, params['h'])
        self.assertAlmostEqual(y_at_h, params['k'])

    def test_scroll_has_no_effect(self):
        # Option X 設計：scroll 對 quadratic 無作用 (a 由幾何約束唯一決定)
        self.ctrl.update(mouse_pos=(500, 220))
        a0, h0, k0 = self.ctrl.quad_a, self.ctrl.quad_h, self.ctrl.quad_k
        self.ctrl.on_mousewheel(5)
        self.assertEqual(self.ctrl.quad_a, a0)
        self.assertEqual(self.ctrl.quad_h, h0)
        self.assertEqual(self.ctrl.quad_k, k0)

    def test_facing_follows_vertex_x(self):
        self.ctrl.update(mouse_pos=(300, 320))
        self.assertEqual(self.ctrl.facing, -1)

    def test_clamp_h_when_mouse_too_vertical(self):
        # 滑鼠剛好在玩家正上方 → |h| 會被 clamp，避免 a 爆炸
        self.ctrl.update(mouse_pos=(400, 200))  # dx=0, dy=120
        self.assertGreaterEqual(abs(self.ctrl.quad_h), self.ctrl.QUAD_H_MIN)
        # a 不應該是 inf 或 NaN
        self.assertTrue(math.isfinite(self.ctrl.quad_a))


class TestMathProjectile(unittest.TestCase):
    """projectile 路徑符合公式"""

    def test_projectile_linear_horizontal(self):
        # 純水平：direction = (1, 0)
        proj = MathProjectile(
            origin=(100, 100),
            power=PowerType.LINEAR,
            params={'a': 0.0, 'vertical': False},
            facing=1,
            direction=(1.0, 0.0),
        )
        self.assertEqual(proj.rect.center, (100, 100))
        # 5 步：world_x += 6 each
        for _ in range(5):
            dx, dy = proj.direction
            proj.world_x += proj.SPEED_PX * dx
            proj.world_y += proj.SPEED_PX * dy
            proj.rect.center = (
                int(proj.origin[0] + proj.world_x),
                int(proj.origin[1] - proj.world_y),
            )
        self.assertEqual(proj.world_x, 30)
        self.assertEqual(proj.world_y, 0)
        self.assertEqual(proj.rect.center, (130, 100))

    def test_projectile_linear_vertical_up(self):
        # 純垂直向上：direction = (0, 1)
        proj = MathProjectile(
            origin=(100, 100),
            power=PowerType.LINEAR,
            params={'a': 0.0, 'vertical': True},
            facing=1,
            direction=(0.0, 1.0),
        )
        for _ in range(5):
            dx, dy = proj.direction
            proj.world_x += proj.SPEED_PX * dx
            proj.world_y += proj.SPEED_PX * dy
            proj.rect.center = (
                int(proj.origin[0] + proj.world_x),
                int(proj.origin[1] - proj.world_y),
            )
        # world_x 沒動，world_y = 30，螢幕往上 30 → centery = 70
        self.assertEqual(proj.world_x, 0)
        self.assertEqual(proj.world_y, 30)
        self.assertEqual(proj.rect.center, (100, 70))

    def test_projectile_linear_diagonal(self):
        # 對角 45°：direction = (√2/2, √2/2)
        import math as _m
        d = _m.sqrt(2) / 2
        proj = MathProjectile(
            origin=(100, 100),
            power=PowerType.LINEAR,
            params={'a': 1.0, 'vertical': False},
            facing=1,
            direction=(d, d),
        )
        for _ in range(5):
            dx, dy = proj.direction
            proj.world_x += proj.SPEED_PX * dx
            proj.world_y += proj.SPEED_PX * dy
        # 5 步速度 6 沿 45° → world_x ≈ world_y ≈ 30 / √2 * √2 = 30 * d ≈ 21.21
        expected = 5 * 6 * d
        self.assertAlmostEqual(proj.world_x, expected, places=4)
        self.assertAlmostEqual(proj.world_y, expected, places=4)

    def test_projectile_follows_quadratic(self):
        # 頂點在 (50, 0) 相對玩家
        proj = MathProjectile(
            origin=(100, 100),
            power=PowerType.QUADRATIC,
            params={'a': 0.01, 'h': 50, 'k': 0},
            facing=1,
        )
        # 起始 (world_x=0)，y = 0.01 * (0-50)^2 = 25 (向上)，screen_y = 100 - 25 = 75
        self.assertEqual(proj.rect.center, (100, 75))


class TestPlayerHpAndDegree(unittest.TestCase):
    def test_take_damage_rounds_hp(self):
        p = Player(100, 100)
        self.assertEqual(p.max_health, 10.0)
        p.take_damage(3.141)
        self.assertEqual(p.health, 6.86)

    def test_apply_degree_delta_clamps(self):
        p = Player(100, 100)
        p.polynomial_degree = 3
        p.apply_degree_delta(5)
        self.assertEqual(p.polynomial_degree, 3)
        p.polynomial_degree = 0
        p.apply_degree_delta(-3)
        self.assertEqual(p.polynomial_degree, 0)


class TestSigmaSchedule(unittest.TestCase):
    def test_n0_expands_ten_zeros(self):
        sched = build_sigma_shot_schedule(0, 1000, 250, 10)
        self.assertEqual(len(sched), 10)
        self.assertTrue(all(v == 0 for _, v in sched))

    def test_n2_has_zero_burst_then_1_and_2(self):
        sched = build_sigma_shot_schedule(2, 0, 100, 10)
        vals = [v for _, v in sched]
        self.assertEqual(vals, [0, 1, 2])


class TestSigmoidHeal(unittest.TestCase):
    def test_positive_and_bounded(self):
        h = sigmoid_heal_from_damage(100, heal_max=5.0, alpha=0.05)
        self.assertGreater(h, 0)
        self.assertLessEqual(h, 5.0)


class TestWorldCSVLoad(unittest.TestCase):
    def test_load_level1(self):
        # 測試現實 csv 能正確 parse
        w = World()
        w.process_csv(1, base_dir=os.path.dirname(os.path.abspath(__file__)))
        # level1 應該有玩家 spawn、一個敵人、一個出口
        self.assertEqual(len(w.enemy_spawns), 1)
        self.assertIsNotNone(w.exit_pos)
        # 應該有地板（多個 obstacle）
        self.assertGreater(len(w.obstacle_list), 30)

    def test_load_level2(self):
        w = World()
        w.process_csv(2, base_dir=os.path.dirname(os.path.abspath(__file__)))
        # level2 有 3 個敵人 + 出口 + 健康箱
        self.assertEqual(len(w.enemy_spawns), 3)
        self.assertIsNotNone(w.exit_pos)
        self.assertEqual(len(w.health_box_positions), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
