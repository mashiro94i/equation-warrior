"""純函式：power + params + x → y。無 pygame 依賴，最容易測"""
from .enums import PowerType


class Equation:
    """無狀態核心：拿 power + params + x → y"""

    @staticmethod
    def evaluate(power, params, x):
        """
        power: PowerType
        params: dict
            LINEAR    -> {'a'}
            QUADRATIC -> {'a','h','k'}  (頂點式 y = a(x-h)^2 + k)
            CUBIC     -> 預留
        x: world x (相對玩家原點)
        return: world y (數學慣例：向上為正)
        """
        if power == PowerType.LINEAR:
            return params['a'] * x
        if power == PowerType.QUADRATIC:
            return params['a'] * (x - params['h']) ** 2 + params['k']
        if power == PowerType.CUBIC:
            # TODO: 兩種形式 ax^3 vs ax^3 - bx (有/無極值)
            return 0
        return 0

    @staticmethod
    def format_str(power, params):
        if power == PowerType.LINEAR:
            if params.get('vertical'):
                return "f(x): vertical (x = 0)"
            return f"f(x) = {params['a']:.2f}x"
        if power == PowerType.QUADRATIC:
            a = params['a']
            h = params['h']
            k = params['k']
            h_part = f"x - {h:.0f}" if h >= 0 else f"x + {-h:.0f}"
            k_part = f"+ {k:.0f}" if k >= 0 else f"- {-k:.0f}"
            return f"f(x) = {a:.3f}({h_part})^2 {k_part}"
        if power == PowerType.CUBIC:
            return "f(x) = TODO (cubic 尚未實作)"
        return ""
