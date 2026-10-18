"""Mocked speech-worker checks: portable progress protocol and empty audio."""
import io
import json
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
import speech_worker


class FakeStorage:
    records=[]
    def __init__(self, path):
        self.path=path
    def add_speech_segment(self, *args, **kwargs):
        self.records.append(('segment',kwargs))
    def finish_speech_recording(self, *args, **kwargs):
        self.records.append(('finish',args,kwargs))


class WorkerProtocolTests(unittest.TestCase):
    def test_russian_messages_escaped_in_ascii_json(self):
        capture=io.StringIO()
        with patch.object(speech_worker.sys, 'stdout', capture):
            speech_worker.emit('error','Не удалось распознать голос: микрофон выключен',37)
        wire=capture.getvalue()
        wire.encode('ascii')
        payload=json.loads(wire)
        self.assertEqual(payload['code'],'error')
        self.assertEqual(payload['progress'],37)
        self.assertIn('микрофон',payload['text'])

    def _run_with_mocked_model(self, segments):
        class FakeModel:
            def __init__(self,*args,**kwargs):
                pass
            def transcribe(self,*args,**kwargs):
                return (iter(segments), None)

        FakeStorage.records=[]
        with tempfile.TemporaryDirectory() as td:
            audio=Path(td)/'recording.wav'
            with wave.open(str(audio),'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b'\x00\x00'*32000)
            job=Path(td)/'job.json'
            job.write_text(json.dumps({'model':'tiny','db_path':str(Path(td)/'data.db'),
                                       'profile_id':1,'session_id':7,'delete_audio':True,
                                       'recordings':[{'path':str(audio),'id':8,'started_at':1000,'ended_at':1002}]}),encoding='utf-8')
            output=io.StringIO()
            with patch.dict(sys.modules,{'faster_whisper':types.SimpleNamespace(WhisperModel=FakeModel)}), \
                 patch.object(speech_worker,'Storage',FakeStorage), \
                 patch.object(speech_worker.sys,'argv',['worker','--job',str(job)]), \
                 patch.object(speech_worker.sys,'stdout',output):
                code=speech_worker.main()
            return code,[json.loads(line) for line in output.getvalue().splitlines()],audio.exists(),list(FakeStorage.records)

    def test_one_transcribed_segment_reports_done_and_progress(self):
        from types import SimpleNamespace
        code,events,audio_exists,records=self._run_with_mocked_model([
            SimpleNamespace(start=0.4,end=1.8,text='Привет всем')
        ])
        self.assertEqual(code,0)
        self.assertFalse(audio_exists)
        self.assertEqual(events[-1]['code'],'done')
        self.assertEqual(events[-1]['progress'],100)
        self.assertTrue(any(ev.get('progress',0)>=10 for ev in events))
        self.assertEqual(sum(rec[0]=='segment' for rec in records),1)

    def test_no_words_retains_recording_and_reports_error(self):
        code,events,audio_exists,records=self._run_with_mocked_model([])
        self.assertEqual(code,2)
        self.assertTrue(audio_exists)
        self.assertEqual(events[-1]['code'],'error')
        self.assertIn('слов не найдено',events[-1]['text'])
        self.assertEqual(sum(rec[0]=='segment' for rec in records),0)


if __name__=='__main__':
    unittest.main()
