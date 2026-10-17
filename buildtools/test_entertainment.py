"""No-GUI service-level checks for changing the live wheel rules."""
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

    def test_two_unique_winners_then_switch_to_elimination(self):
        for expected in (4,3):
            self.wheel.spin_roulette()
            self.assertEqual(len(self.wheel.snapshot()['roulette']['entries']), expected+1)
            self.assertEqual(self.wheel.snapshot()['roulette']['result'],'')
            end=self.finish()
            self.assertEqual(end['result_status'],'ПОБЕДИТЕЛЬ')
            self.assertEqual(len(end['entries']),expected)
        self.wheel.set_manual_selection_mode('elimination')
        self.assertEqual(len(self.wheel.snapshot()['roulette']['entries']),3)
        self.wheel.spin_roulette()
        self.assertEqual(len(self.wheel.snapshot()['roulette']['entries']),3)
        end=self.finish()
        self.assertEqual(end['result_status'],'ВЫБЫВШИЙ')
        self.assertEqual(len(end['entries']),2)
        self.wheel.spin_roulette()
        end=self.finish()
        self.assertEqual(end['result_status'],'ПОБЕДИТЕЛЬ')
        self.assertEqual(len(end['entries']),1)
        self.assertEqual(end['result'],end['entries'][0]['label'])

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
