import base64
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import server

ENV={'TWITCH_CLIENT_ID':'local-client','TWITCH_CLIENT_SECRET':'local-secret'}
VALID={'client_id':'local-client','user_id':'123','login':'streamer','scopes':['user:read:chat','user:write:chat']}
class TwitchFlowTest(unittest.TestCase):
    def setUp(self):
        server.ROOMS.clear(); server.OAUTH_STATES.clear()
        room=server.dispatch('POST','/api/rooms')
        self.path='/api/rooms/'+room['code']; self.key=room['key']; self.code=room['code']
        self.viewer=server.dispatch('POST',self.path+'/join')['viewer_token']
        self.env=patch.dict('os.environ',ENV,clear=True);self.env.start();self.addCleanup(self.env.stop)

    def connect(self):
        url=server.dispatch('POST',self.path+'/twitch/start',key=self.key)['url']
        params=parse_qs(urlsplit(url).query)
        self.assertEqual(params['scope'],['user:read:chat user:write:chat'])
        self.assertEqual(params['redirect_uri'],[server.TWITCH_REDIRECT])
        with patch('server.twitch_request',side_effect=[{'access_token':'access','refresh_token':'refresh'},VALID]):
            server.twitch_callback(params['state'][0], 'code')
        return params['state'][0]

    def test_connect_and_secret_is_private(self):
        state=self.connect()
        info=server.dispatch('GET',self.path+'/review',key=self.key)['twitch']
        self.assertEqual(info,{'connected':True,'login':'streamer','announcements':False})
        self.assertNotIn('twitch',server.dispatch('GET',self.path))
        with self.assertRaises(server.Error): server.twitch_callback(state,'code')
        with self.assertRaises(server.Error): server.dispatch('POST',self.path+'/twitch/start')

    def test_wrong_state_or_scope_cannot_connect(self):
        with self.assertRaises(server.Error): server.twitch_callback('wrong','code')
        url=server.dispatch('POST',self.path+'/twitch/start',key=self.key)['url']
        state=parse_qs(urlsplit(url).query)['state'][0]
        with patch('server.twitch_request',side_effect=[{'access_token':'a','refresh_token':'r'},dict(VALID,scopes=[])]):
            with self.assertRaises(server.Error): server.twitch_callback(state,'code')
        self.assertFalse(server.dispatch('GET',self.path+'/review',key=self.key)['twitch']['connected'])

    def test_manual_room_message_sends_only_when_requested(self):
        self.connect()
        with patch('server.twitch_request',side_effect=[VALID,{'data':[{'is_sent':True}]}]) as req:
            server.dispatch('POST',self.path+'/twitch/share',key=self.key)
        message=req.call_args.kwargs['json_body']['message']
        self.assertIn(self.code,message);self.assertIn('only available',message)
        self.assertNotIn('access',message)
        with self.assertRaises(server.Error): server.dispatch('POST',self.path+'/twitch/share')

    def test_manual_invitation_uses_configured_viewer_link(self):
        self.connect()
        with patch.dict('os.environ', {'PUBLIC_VIEWER_ORIGIN':'https://demo.trycloudflare.com'}), patch('server.twitch_request',side_effect=[VALID,{'data':[{'is_sent':True}]}]) as req:
            review=server.dispatch('GET',self.path+'/review',key=self.key)
            self.assertEqual(review['viewer_url'],f'https://demo.trycloudflare.com/?room={self.code}')
            server.dispatch('POST',self.path+'/twitch/share',key=self.key)
        message=req.call_args.kwargs['json_body']['message']
        self.assertIn(f'https://demo.trycloudflare.com/?room={self.code}',message)
        self.assertNotIn(self.key,message)

    def test_announcement_off_on_and_failed_send_preserves_approval(self):
        self.connect()
        image='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()
        body={'image':image,'description':'moon','creator':'viewer123','behavior':'glow','x':2,'y':4}
        with patch('server.moderate',return_value=False):
            server.dispatch('POST',self.path+'/submissions',body,viewer_token=self.viewer)
            server.dispatch('POST',self.path+'/submissions',body,viewer_token=self.viewer)
        with patch('server.twitch_send') as send:
            server.dispatch('POST',self.path+'/approve/1',key=self.key)
            send.assert_not_called()
        server.dispatch('POST',self.path+'/twitch/announcements',{'enabled':True},self.key)
        with patch('server.twitch_send',side_effect=server.Error(503,'no')):
            result=server.dispatch('POST',self.path+'/approve/2',key=self.key)
        self.assertIn('chat_error',result)
        self.assertEqual(len(server.dispatch('GET',self.path)['approved']),2)

    def test_refresh_token_and_dropped_message(self):
        self.connect()
        with patch('server.twitch_request',side_effect=[server.Error(503,'expired'),{'access_token':'new','refresh_token':'newrefresh'},VALID,{'data':[{'is_sent':False}]}]):
            with self.assertRaises(server.Error):server.dispatch('POST',self.path+'/twitch/share',key=self.key)
        room=server.ROOMS[self.code]
        self.assertEqual(room['twitch']['refresh_token'],'newrefresh')

if __name__=='__main__':unittest.main()
