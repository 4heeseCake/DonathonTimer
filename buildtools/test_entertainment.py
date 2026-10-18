"""No-GUI checks: delayed wheel result, switching rules and winner retention."""
import random
import unittest
from types import SimpleNamespace
from src.donathon.entertainment import EntertainmentService


class FakeStorage:
    def __init__(self):
        self.data = {}

    def get_setting(self, key):
        return self.data.get(key)

    def set_setting(self, key, value):
        self.data[key] = value


class FakeState:
    def __init__(self):
        self.profile = SimpleNamespace(id=1)

    def add_listener(self, callback):
        pass


class RouletteModesTests(unittest.TestCase):
    def setUp(self):
        self.storage=FakeStorage()
        self.wheel=EntertainmentService(FakeState(),self.storage,object(),object())
        self.wheel._rng=random.Random(48)
        self.wheel.configure_manual('Тест', ['А','Б','В','Г','Д'], 'winner')

    def finish(self):
        self.wheel._data['roulette']['spin_ends_at']=0
        return self.wheel.snapshot()['roulette']

    def test_winner_stays_until_next_spin_and_is_remembered(self):
        self.wheel.spin_roulette()
        during=self.wheel.snapshot()['roulette']
        self.assertTrue(during['spinning'])
        self.assertEqual(len(during['entries']),5)
        self.assertEqual(during['result'],'')
        self.assertEqual(during['last_winner'],'')
        first=self.finish()
        self.assertEqual(first['result_status'],'ПОБЕДИТЕЛЬ')
        self.assertEqual(first['last_winner'], first['result'])
        self.assertIn(first['result'], [x['label'] for x in first['entries']])
        self.assertEqual(len(first['entries']),5)
        self.wheel.spin_roulette()
        next_spin=self.wheel.snapshot()['roulette']
        self.assertTrue(next_spin['spinning'])
        self.assertEqual(len(next_spin['entries']),4)
        self.assertEqual(next_spin['result'],'')
        self.assertNotIn(first['result'],[x['label'] for x in next_spin['entries']])
        self.assertEqual(next_spin['last_winner'], first['result'])
        second=self.finish()
        self.assertEqual(second['last_winner'],second['result'])
        self.assertEqual(len(second['entries']),4)

    def test_switch_to_elimination_excludes_old_winner_on_next_spin(self):
        self.wheel.spin_roulette()
        first=self.finish()
        old_winner=first['result']
        self.wheel.set_manual_selection_mode('elimination')
        self.assertIn(old_winner,[e['label'] for e in self.wheel.snapshot()['roulette']['entries']])
        self.wheel.spin_roulette()
        self.assertNotIn(old_winner,[e['label'] for e in self.wheel.snapshot()['roulette']['entries']])
        after=self.finish()
        self.assertEqual(after['result_status'],'ВЫБЫВШИЙ')
        self.assertEqual(len(after['entries']),3)
        self.assertEqual(after['last_winner'],old_winner)

    def test_elimination_ends_with_one_winner(self):
        self.wheel.set_manual_selection_mode('elimination')
        for remain in (4,3,2,1):
            self.wheel.spin_roulette()
            self.assertEqual(len(self.wheel.snapshot()['roulette']['entries']),remain+1)
            after=self.finish()
            self.assertEqual(len(after['entries']),remain)
            self.assertEqual(after['result_status'],'ПОБЕДИТЕЛЬ' if remain==1 else 'ВЫБЫВШИЙ')
        self.assertEqual(after['last_winner'],after['entries'][0]['label'])

    def test_mode_switch_does_not_reset_survivors(self):
        self.wheel.set_manual_selection_mode('elimination')
        self.wheel.spin_roulette()
        self.finish()
        before=[x['label'] for x in self.wheel.snapshot()['roulette']['entries']]
        self.wheel.set_manual_selection_mode('winner')
        after=[x['label'] for x in self.wheel.snapshot()['roulette']['entries']]
        self.assertEqual(before,after)
        self.assertEqual(self.wheel.snapshot()['roulette']['manual_mode'],'winner')
        reloaded=EntertainmentService(FakeState(),self.storage,object(),object())
        self.assertEqual(reloaded.snapshot()['roulette']['manual_mode'],'winner')


if __name__=='__main__':
    unittest.main()
