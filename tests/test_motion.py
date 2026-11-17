import unittest
from core.mood import event_color, lerp_color, pick_mood
from ui.animations import ANIM_STYLES, Sp
from ui.motion import Motion, SCENARIOS, scenario_for


def simulate(name, w0, h0, w1, h1, style='liquid', secs=1.6):
    m, sw, sh, t = Motion(), Sp(w0), Sp(h0), 0.0
    m.start(name, 0.0)
    k, d = ANIM_STYLES[style][:2]
    ws, hs = [], []
    while t < secs:
        kw, dw, kh, dh, wg, hg = m.params(t, k, d)
        if wg:
            sw.tgt = w1
        if hg:
            sh.tgt = h1
        sw.step(kw, dw, 0.016)
        sh.step(kh, dh, 0.016)
        ws.append(sw.x)
        hs.append(sh.x)
        t += 0.016
    return ws, hs


def over(xs, x0, x1):
    return ((max(xs) - x1) if x1 > x0 else (x0 and (x1 - min(xs)))) / abs(x1 - x0)


class MotionTest(unittest.TestCase):
    def test_open_overshoot_bounded_and_settles(self):
        ws, hs = simulate('open', 236, 36, 710, 396)
        self.assertLess(over(ws, 236, 710), 0.10)        # не вылетает за окно (его ширина W+80)
        self.assertLess(over(hs, 36, 396), 0.10)
        self.assertAlmostEqual(ws[-1], 710, delta=0.5)
        self.assertAlmostEqual(hs[-1], 396, delta=0.5)

    def test_height_starts_after_width(self):
        ws, hs = simulate('open', 236, 36, 710, 396, secs=0.04)
        self.assertGreater(ws[-1], 236 + 20)
        self.assertEqual(hs[-1], 36)                      # высота ещё ждёт: капсула сначала тянется в стороны

    def test_close_has_no_rebound(self):
        ws, hs = simulate('close', 710, 396, 236, 36)
        self.assertGreater(min(hs), 36 - 36 * 0.04)       # не уходит ниже высоты «таблетки»
        self.assertGreater(min(ws), 236 - 236 * 0.04)

    def test_media_is_slow_and_soft(self):
        ws, _ = simulate('media', 236, 36, 310, 36)
        o, _ = simulate('open', 236, 36, 310, 36)
        self.assertLess(ws[6], o[6])                      # на 100 мс музыка раскрыта меньше, чем при открытии
        self.assertLess(over(ws, 236, 310), 0.05)

    def test_every_style_settles(self):
        for style in ANIM_STYLES:
            for name in SCENARIOS:
                ws, hs = simulate(name, 236, 36, 480, 170, style, 2.5)
                self.assertAlmostEqual(ws[-1], 480, delta=0.6, msg=(style, name))
                self.assertAlmostEqual(hs[-1], 170, delta=0.6, msg=(style, name))

    def test_scenario_choice(self):
        self.assertEqual(scenario_for('idle', 'open'), 'open')
        self.assertEqual(scenario_for('open', 'idle'), 'close')
        self.assertEqual(scenario_for('idle', 'notif'), 'notif')
        self.assertEqual(scenario_for('idle', 'idle', 'media'), 'media')


class MoodTest(unittest.TestCase):
    def test_priority(self):
        st = {'recording': True, 'timer': True, 'playing': True, 'cover': (10, 200, 30)}
        self.assertEqual(pick_mood(st)[0], 'recording')
        st['recording'] = False
        self.assertEqual(pick_mood(st)[0], 'timer')
        st['timer'] = False
        self.assertEqual(pick_mood(st), ('music', (10, 200, 30), 0.7))
        st['card_prio'] = 'important'
        self.assertEqual(pick_mood(st)[0], 'important')
        st['toast_col'] = (1, 2, 3)
        self.assertEqual(pick_mood(st)[0], 'event')
        self.assertEqual(pick_mood({})[0], 'none')

    def test_event_colors(self):
        self.assertEqual(event_color('Bluetooth'), (90, 190, 255))
        self.assertEqual(event_color('Таймер'), (255, 159, 10))
        self.assertEqual(event_color('Bluetooth', ok=False), (255, 69, 58))
        self.assertIsNone(event_color('Громкость'))

    def test_lerp_is_frame_rate_independent(self):
        a = (0.0, 0.0, 0.0)
        one = lerp_color(a, (100, 100, 100), 0.032)
        two = lerp_color(lerp_color(a, (100, 100, 100), 0.016), (100, 100, 100), 0.016)
        self.assertAlmostEqual(one[0], two[0], places=6)


if __name__ == '__main__':
    unittest.main()
