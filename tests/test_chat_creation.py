import base64
import concurrent.futures
import json
import io
import unittest
from unittest.mock import patch
import server

IMAGE='data:image/webp;base64,'+base64.b64encode(b'RIFF0000WEBPexample').decode()
def event(user='42', text='!draw a neon cat'):
    return {'chatter_user_id':user,'chatter_user_name':'Viewer','message':{'text':text}}
class ChatCreationTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear()
        created=server.dispatch('POST','/api/rooms')
        self.path='/api/rooms/'+created['code']; self.key=created['key']; self.room=server.ROOMS[created['code']]
        self.room['chat_enabled']=True
    def send(self, ev=None, msg='message-1'):
        server.chat_command(self.room,ev or event(),msg)
    def test_private_moderated_creation_and_placement(self):
        with patch('server.moderate_text',return_value=False) as text, patch('server.generate_chat_art',return_value=IMAGE) as generate, patch('server.moderate',return_value=False) as image:
            self.send()
        text.assert_called_once_with('a neon cat','Viewer');generate.assert_called_once_with('a neon cat');image.assert_called_once_with(IMAGE,'a neon cat','Viewer')
        self.assertEqual(server.dispatch('GET',self.path)['approved'],[])
        pending=server.dispatch('GET',self.path+'/review',key=self.key)['pending']
        self.assertEqual((pending[0]['creator'],pending[0]['behavior']),('Viewer','still'))
        with self.assertRaises(server.Error):server.dispatch('POST',self.path+'/placement/1',{'x':55,'y':40})
        server.dispatch('POST',self.path+'/placement/1',{'x':55,'y':40},self.key)
        server.dispatch('POST',self.path+'/approve/1',key=self.key)
        self.assertEqual(server.dispatch('GET',self.path)['approved'][0]['x'],55)
    def test_flagged_prompts_and_images_warn_three_times(self):
        with patch('server.moderate_text',side_effect=[True,False,True]) as txt, patch('server.generate_chat_art',return_value=IMAGE), patch('server.moderate',return_value=True):
            for i in range(3):
                self.send(msg=str(i));self.room['chat_users']['42']['next_at']=0
            self.send(msg='four')
            self.assertEqual(txt.call_count,3)
        self.assertEqual(self.room['chat_users']['42']['warnings'],3)
        self.assertEqual(self.room['pending'],[]);self.assertEqual(self.room['chat_attempts'],1)
    def test_cooldown_duplicate_and_invalid_command(self):
        with patch('server.moderate_text',return_value=False) as mod, patch('server.generate_chat_art',return_value=IMAGE), patch('server.moderate',return_value=False):
            self.send();self.send();self.send(msg='different');self.send(event(text='hello'),msg='other')
            self.assertEqual(mod.call_count,1)
        self.assertEqual(self.room['chat_attempts'],1)
    def test_cap_is_atomic_with_concurrent_users(self):
        with patch('server.moderate_text',return_value=False), patch('server.generate_chat_art',return_value=IMAGE), patch('server.moderate',return_value=False):
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
                list(pool.map(lambda n:self.send(event(str(n)),str(n)),range(15)))
        self.assertEqual(self.room['chat_attempts'],10);self.assertEqual(len(self.room['pending']),10)
        self.assertEqual(server.dispatch('GET',self.path)['approved'],[])
    def test_failure_and_pause_never_publish(self):
        with patch('server.moderate_text',return_value=False), patch('server.generate_chat_art',side_effect=server.Error(503,'failure')):
            self.send()
        self.assertEqual(self.room['chat_users']['42']['warnings'],0);self.assertEqual(self.room['pending'],[])
        self.room['paused']=True
        with patch('server.moderate_text') as mod:self.send(event('99'),'other');mod.assert_not_called()

    def test_provider_request_uses_approved_model_and_transparency(self):
        data=base64.b64encode(b'RIFF0000WEBPexample').decode()
        response=io.BytesIO(json.dumps({'data':[{'b64_json':data}]}).encode())
        with patch.dict('os.environ',{'OPENAI_API_KEY':'test'}), patch('urllib.request.urlopen',return_value=response) as call:
            self.assertTrue(server.generate_chat_art('moon').startswith('data:image/webp;base64,'))
        payload=json.loads(call.call_args.args[0].data)
        self.assertEqual((payload['model'],payload['quality'],payload['background']),('gpt-image-1.5','low','transparent'))

    def test_eventsub_welcome_and_chat_notification(self):
        self.room['twitch']={'user_id':'123','access_token':'a'}
        messages=[
            {'metadata':{'message_type':'session_welcome'},'payload':{'session':{'id':'session'}}},
            {'metadata':{'message_type':'notification','message_id':'event-1'},'payload':{'subscription':{'type':'channel.chat.message'},'event':dict(event(),broadcaster_user_id='123')}},
            {'metadata':{'message_type':'revocation'},'payload':{}},
        ]
        class FakeSocket:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def recv(self,timeout): return json.dumps(messages.pop(0))
        class ImmediateThread:
            def __init__(self,target,args=(),daemon=False): self.target,self.args=target,args
            def start(self): self.target(*self.args)
        with patch('websockets.sync.client.connect',return_value=FakeSocket()), patch('server.twitch_token',return_value=(self.room['twitch'],'client')), patch('server.twitch_request',return_value={}) as sub, patch('server.threading.Thread',ImmediateThread), patch('server.moderate_text',return_value=False), patch('server.generate_chat_art',return_value=IMAGE), patch('server.moderate',return_value=False):
            server.eventsub_loop(self.room)
        self.assertEqual(sub.call_args.kwargs['json_body']['type'],'channel.chat.message')
        self.assertEqual(self.room['pending'][0]['creator'],'Viewer')
        self.assertFalse(self.room['chat_enabled'])

if __name__=='__main__':unittest.main()
