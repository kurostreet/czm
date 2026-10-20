"""/tester in the owner's bot: the number of Google Play beta testers shown on the site."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from czm import bot, db, website
from czm.config import get_settings


class FakeMessage:
    def __init__(self, user_id):
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


class TesterCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"CZM_DATA_DIR": temp.name, "CZM_BOT_OWNER_IDS": "42"})
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        db.init()
        self.owner = bot.OwnerBot(None, get_settings())

    def testers(self):
        with db.db() as conn:
            return website.stats(conn)["play_beta_testers"]

    async def send(self, args, user=42):
        message = FakeMessage(user)
        await self.owner.on_tester(message, SimpleNamespace(args=args))
        return message.answers

    async def test_owner_sets_and_reads_the_count(self):
        self.assertIn("ещё не указано", (await self.send(""))[0])
        self.assertIn("7 из 50", (await self.send("7"))[0])
        self.assertEqual(self.testers(), 7)
        self.assertIn("50 из 50", (await self.send(" 50 "))[0])
        self.assertIn("тестировщиков: 50", (await self.send(None))[0])

    async def test_wrong_numbers_and_strangers_change_nothing(self):
        await self.send("6")
        for args in ("-1", "abc", "7.5", "1000001"):
            self.assertIn("Так: /tester", (await self.send(args))[0])
        self.assertEqual(await self.send("9", user=7), [])
        self.assertEqual(self.testers(), 6)


if __name__ == "__main__":
    unittest.main()
