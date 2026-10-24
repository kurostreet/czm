"""Unread counters follow events and acknowledge only the displayed records."""
import unittest
from unittest.mock import patch
import test_social as fixtures
from czm import db, social, service


class NotificationTests(unittest.TestCase):
    setUp = fixtures.SocialTests.setUp
    request = fixtures.SocialTests.request
    follow = fixtures.SocialTests.follow

    def counts(self, actor=0):
        return self.request('GET', 'social/summary', actor).json()['counts']

    def notice(self, actor, kind, offset=0):
        result=self.request('GET', f'social/people/{kind}?offset={offset}', actor)
        self.assertEqual(result.status_code,200,result.text)
        return result.json()['people'][0]['notice']

    def read(self, actor, kind, ids):
        result=self.request('POST','social/notifications/read',actor,json={'kind':kind,'ids':ids})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()['counts']

    def test_new_friend_follower_and_following_are_distinct(self):
        self.follow(0,1)
        event=self.notice(1,'followers');self.assertGreater(event,0)
        self.assertEqual(self.counts(1)['requests'],1)
        self.read(2,'followers',[event]);self.read(1,'friends',[event])
        self.assertEqual(self.counts(1)['requests'],1)
        self.read(1,'followers',[event]);self.assertEqual(self.counts(1)['requests'],0)
        self.assertEqual(self.counts(1)['followers'],1)
        self.follow(1,0)
        self.assertEqual(self.counts(0)['new_friends'],1)
        self.assertEqual(self.counts(1)['new_friends'],0)
        friend_event=self.notice(0,'friends')
        self.read(0,'friends',[friend_event])
        self.assertEqual((self.counts(0)['new_friends'],self.counts(0)['friends']),(0,1))
        self.follow(1,0,'unfollow')
        self.assertEqual((self.counts(0)['following_updates'],self.counts(0)['following']),(1,1))
        self.follow(0,1,'block')
        self.assertEqual(self.counts(0)['following_updates'],0)

    def test_late_ack_cannot_clear_a_new_request_from_same_person(self):
        self.follow(0,1);old=self.notice(1,'followers')
        self.follow(0,1,'unfollow');self.follow(0,1)
        new=self.notice(1,'followers');self.assertGreater(new,old)
        self.read(1,'followers',[old])
        self.assertEqual(self.counts(1)['requests'],1)
        self.assertEqual(self.notice(1,'followers'),new)
        self.read(1,'followers',[new]);db.init()
        self.assertEqual(self.counts(1)['requests'],0)

    def test_ack_only_clears_loaded_page(self):
        self.follow(0,1);self.follow(2,1)
        with patch.object(social,'PAGE_SIZE',1):
            first=self.notice(1,'followers');second=self.notice(1,'followers',1)
        self.read(1,'followers',[first]);self.assertEqual(self.counts(1)['requests'],1)
        self.read(1,'followers',[second]);self.assertEqual(self.counts(1)['requests'],0)

    def test_chat_rooms_self_messages_and_bounded_reads(self):
        for actor in (0,1):self.request('POST','social/presence',actor,json={})
        with db.db() as c:
            def message(room,who):
                return c.execute('INSERT INTO messages(room,player,text,created) VALUES(?,?,?,?)',
                                 (room,self.ids[who],'Test',db.now())).lastrowid
            first=message('global',0);message('ru',0);message('en',1);last=message('global',0)
        before=self.counts(1)
        self.assertEqual((before['chat_global'],before['chat_ru'],before['chat_en']),(2,1,0))
        r=self.request('POST','chat/global/read',1,json={'through':first}).json()['counts']
        self.assertEqual((r['chat_global'],r['chat_ru']),(1,1))
        self.assertGreater(r['revision'],before['revision'])
        r=self.request('POST','chat/global/read',1,json={'through':last+9999}).json()['counts']
        self.assertEqual((r['chat_global'],r['chat_ru']),(0,1))
        self.request('POST','chat/global/read',1,json={'through':first})
        self.assertEqual(self.counts(1)['chat_global'],0)
        self.assertEqual(self.counts(0)['chat_en'],1)
        self.assertEqual(self.request('POST','chat/unknown/read',1,json={'through':last}).status_code,404)

    def test_chat_message_ids_do_not_restart_after_retention(self):
        with db.db() as c:
            first=c.execute('INSERT INTO messages(id,room,player,text,created) VALUES(1000,?,?,?,?)',
                            ('global',self.ids[0],'Old',db.now())).lastrowid
            c.execute('DELETE FROM messages')
            player=c.execute('SELECT * FROM players WHERE id=?',(self.ids[0],)).fetchone()
            result=service.post_message(c,player,'global','A new message')
            self.assertGreater(result['id'],first)

if __name__=='__main__':unittest.main()
