"""Only the owner's private bot can assign roles or approve/undo moderation."""
import base64
import io
from types import SimpleNamespace
import unittest

from aiogram.exceptions import TelegramAPIError
from PIL import Image
from czm import accounts, bot, community, db, moderator_guard
from czm.config import get_settings
import test_moderation as baseline


class Message:
    def __init__(self, user=42, chat="private"):
        self.from_user=SimpleNamespace(id=user);self.chat=SimpleNamespace(type=chat)
        self.answers=[];self.markups=[]

    async def answer(self, text, **kwargs):
        self.answers.append(text);self.markups.append(kwargs.get("reply_markup"))

    async def edit_reply_markup(self, **kwargs):
        self.markups.append(kwargs.get("reply_markup"))


class Sender:
    def __init__(self):
        self.sent=[];self.deleted=[];self.fail_document=False

    async def _send(self, kind, owner, **kwargs):
        self.sent.append((kind,owner,kwargs));return SimpleNamespace(message_id=len(self.sent))

    async def send_message(self, owner, text, **kwargs):
        return await self._send("text",owner,text=text,**kwargs)

    async def send_photo(self, owner, photo, **kwargs):
        return await self._send("photo",owner,photo=photo,**kwargs)

    async def send_document(self, owner, document, **kwargs):
        if self.fail_document:
            self.fail_document=False;raise TelegramAPIError(method=None,message="retry")
        return await self._send("document",owner,document=document,**kwargs)

    async def delete_message(self, owner, message):
        self.deleted.append((owner,message))


class CommunityBotTests(unittest.IsolatedAsyncioTestCase):
    request=baseline.ModerationTests.request
    act=baseline.ModerationTests.act
    chat=baseline.ModerationTests.chat

    def setUp(self):
        baseline.ModerationTests.setUp(self)
        with db.db() as c:
            community.grant(c,self.ids[1],"moderator")
            community.grant(c,self.ids[2],"tester")
        self.sender=Sender()
        self.owner=bot.OwnerBot(self.sender,get_settings().model_copy(update={"bot_owner_ids":"42"}))

    async def send(self, method, command, args="", user=42, chat="private"):
        message=Message(user,chat)
        await getattr(self.owner,method)(message,SimpleNamespace(command=command,args=args))
        return message

    async def test_role_and_moderator_commands_require_owner_in_private_chat(self):
        cases=[("on_role","role",f"{self.ids[3]} tester"),("on_unrole","unrole",f"{self.ids[1]} moderator"),
               ("on_moderators","moderators",""),("on_moderator","moderator",str(self.ids[1])),
               ("on_mod_control","mod_pause",str(self.ids[1])),("on_mod_control","mod_undo",str(self.ids[1]))]
        for method,command,args in cases:
            self.assertEqual((await self.send(method,command,args,user=7)).answers,[])
            self.assertEqual((await self.send(method,command,args,chat="group")).answers,[])
        with db.db() as c:
            self.assertFalse(community.has(c,self.ids[3],"tester"))
            self.assertFalse(moderator_guard.paused(c,self.ids[1]))
        result=await self.send("on_role","role",f"{self.ids[3]} tester")
        self.assertIn("tester",result.answers[0])
        await self.send("on_role","role",f"{self.ids[3]} support")
        with db.db() as c:self.assertFalse(community.has(c,self.ids[3],"support"))

    async def test_ten_actions_notify_owner_and_undo_needs_his_confirmation(self):
        for i in range(10):
            self.assertEqual(self.act("warn",target=2,actor=1,reason="Причина <spam>").status_code,200)
        await self.owner.notify_moderation()
        self.assertEqual(len(self.sender.sent),10)
        self.assertTrue(all(s[1]==42 for s in self.sender.sent))
        self.assertIn("&lt;spam&gt;",self.sender.sent[0][2]["text"])
        self.assertIn("права приостановлены",self.sender.sent[-1][2]["text"])
        await self.owner.notify_moderation();self.assertEqual(len(self.sender.sent),10)
        preview=await self.send("on_mod_control","mod_undo",str(self.ids[1]))
        callback=preview.markups[-1].inline_keyboard[0][0].callback_data
        async def answer(*args,**kwargs):pass
        query=SimpleNamespace(from_user=SimpleNamespace(id=7),message=preview,data=callback,answer=answer)
        await self.owner.on_callback(query)
        with db.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM warnings WHERE seen=0").fetchone()[0],10)
        query.from_user.id=42;await self.owner.on_callback(query)
        with db.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM warnings WHERE seen=0").fetchone()[0],0)
            self.assertTrue(moderator_guard.paused(c,self.ids[1]))
        await self.send("on_mod_control","mod_resume",str(self.ids[1]))
        with db.db() as c:self.assertFalse(moderator_guard.paused(c,self.ids[1]))

    async def test_ticket_parts_retry_independently_and_account_deletion_removes_copies(self):
        photo=io.BytesIO();Image.new("RGB",(8,8),"red").save(photo,format="PNG")
        with db.db() as c:
            ticket=community.ticket(c,self.keys[2],"Bug <UI>","Steps",base64.b64encode(photo.getvalue()).decode(),
                base64.b64encode(b"log text").decode(),"report.txt","bot-ticket-nonce-001")
        self.sender.fail_document=True
        await self.owner.notify_tickets()
        self.assertEqual([s[0] for s in self.sender.sent],["text","photo"])
        with db.db() as c:self.assertEqual(community.tickets_pending(c,42)[0]["parts"],3)
        await self.owner.notify_tickets()
        self.assertEqual([s[0] for s in self.sender.sent],["text","photo","document"])
        with db.db() as c:
            accounts.delete_account(c,self.keys[2],"Password123","test-ip")
            self.assertIsNone(c.execute("SELECT id FROM tester_tickets WHERE id=?",(ticket["id"],)).fetchone())
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(),[])
        await self.owner.notify_tickets()
        self.assertEqual(self.sender.deleted,[(42,1),(42,2),(42,3)])


if __name__=="__main__":unittest.main()
