"""A registered SUPPORT account must also be explicitly allowed by the server."""
import os
import json
import unittest
from unittest.mock import patch
from czm import admin,community,db,moderation,moderator_guard,server_moderation,service
from czm.config import get_settings
import test_community as baseline

class HeadAdminTests(unittest.TestCase):
    request=baseline.CommunityTests.request
    act=baseline.CommunityTests.act
    chat=baseline.CommunityTests.chat

    def setUp(self):
        baseline.CommunityTests.setUp(self)
        env=patch.dict(os.environ,{"CZM_ADMIN_PLAYER_IDS":str(self.ids[0])})
        env.start();self.addCleanup(env.stop);get_settings.cache_clear();self.addCleanup(get_settings.cache_clear)
        self.sequence=0

    def change(self,action,actor=0,**fields):
        self.sequence+=1
        return self.request("POST","admin/action",actor,json={"action":action,"nonce":f"head-admin-change-{self.sequence:04d}",**fields})

    def test_allowlist_does_not_turn_a_moderator_or_tester_into_head_admin(self):
        for i in range(1,4):
            for section in ("overview","players","moderators","servers","history"):
                self.assertEqual(self.request("GET","admin/"+section,i).status_code,403)
            self.assertEqual(self.change("role_grant",i,target=self.ids[i],role="moderator").status_code,403)
        self.assertEqual(self.client.get("/api/v1/admin/overview").status_code,401)
        with patch.dict(os.environ,{"CZM_ADMIN_PLAYER_IDS":",".join(map(str,self.ids))}):
            get_settings.cache_clear()
            for i in range(1,4):self.assertEqual(self.request("GET","admin/overview",i).status_code,403)
        get_settings.cache_clear()

    def test_support_without_configuration_has_no_global_management_access(self):
        with patch.dict(os.environ,{"CZM_ADMIN_PLAYER_IDS":""}):
            get_settings.cache_clear()
            self.assertEqual(self.request("GET","admin/overview").status_code,403)
            hello=self.request("POST","hello",json={"key":self.keys[0]}).json()
            self.assertFalse(hello["capabilities"]["admin"])
        get_settings.cache_clear()
        self.assertEqual(self.request("GET","admin/overview").status_code,200)
        self.assertTrue(self.request("POST","hello",json={"key":self.keys[0]}).json()["capabilities"]["admin"])

    def test_role_changes_are_logged_idempotent_and_cannot_issue_support(self):
        body={"action":"role_grant","target":self.ids[2],"role":"moderator","nonce":"head-role-repeat-0001"}
        first=self.request("POST","admin/action",json=body);self.assertEqual(first.status_code,200,first.text)
        self.assertTrue(self.request("POST","admin/action",json=body).json()["repeated"])
        self.assertEqual(self.request("POST","admin/action",json={**body,"role":"server_owner"}).status_code,409)
        with db.db() as c:
            self.assertTrue(community.has(c,self.ids[2],"moderator"))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM admin_actions").fetchone()[0],1)
        self.assertEqual(self.change("role_grant",target=self.ids[2],role="support").status_code,400)
        self.assertEqual(self.change("role_revoke",target=self.ids[2],role="moderator").status_code,200)

    def test_player_lookup_and_pagination_do_not_expose_email_or_auth_secrets(self):
        with db.db() as c:
            c.execute("UPDATE accounts SET email='private@example.com' WHERE player=?",(self.ids[0],))
            for i in range(23):service.hello(c,f"admin-page-guest-{i:03d}","device",f"Page guest {i}","","ru","test")
        page=self.request("GET","admin/players").json()
        self.assertEqual(len(page["players"]),20);self.assertEqual(page["next"],20)
        detail=self.request("GET",f"admin/player?target={self.ids[0]}").json()
        self.assertNotIn("private@example.com",json.dumps([page,detail]))
        self.assertNotIn("key_hash",json.dumps([page,detail]))
        exact=self.request("GET",f"admin/players?query={self.ids[0]}").json()["players"]
        self.assertEqual(exact[0]["id"],self.ids[0])
        self.assertEqual(self.request("GET","admin/players?query=%25%27%20OR%201%3D1").json()["players"],[])

    def test_server_control_requires_a_reason_and_preserves_report_cooldowns(self):
        address="8.8.8.8:27015"
        self.assertEqual(self.change("server_ban",server=address).status_code,400)
        result=self.change("server_ban",server=address,reason="Review required")
        self.assertTrue(result.json()["blocked"])
        self.assertTrue(self.request("GET","admin/server?query="+address).json()["blocked"])
        self.assertFalse(self.change("server_unban",server=address).json()["blocked"])
        with db.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM server_moderation_log").fetchone()[0],2)
        self.assertEqual(self.change("server_ban",server="127.0.0.1:27015",reason="x").status_code,400)

    def test_head_actions_use_moderation_and_notify_owner_with_a_reason(self):
        target=self.ids[2]
        self.assertEqual(self.change("warn",target=target).status_code,400)
        self.assertEqual(self.change("warn",target=target,reason="Review warning").status_code,200)
        with db.db() as c:
            events=moderator_guard.pending(c,42)
            self.assertEqual(len(events),1);self.assertEqual(events[0]["reason"],"Review warning")
        refused=self.change("ban",target=self.ids[0],minutes=60,reason="Cannot ban chief")
        self.assertEqual(refused.status_code,400)
        with db.db() as c:self.assertIsNone(service.active_ban(c,service.player_by_key(c,self.keys[0])))

    def test_previewed_undo_rejects_changed_history_and_leaves_moderator_paused(self):
        self.chat(2,"Restore this message")
        with db.db() as c:message=c.execute("SELECT MAX(id) FROM messages").fetchone()[0]
        self.act("delete_message",target=2,actor=1,message=message,reason="Mistake")
        self.change("mod_pause",target=self.ids[1])
        info=self.request("GET",f"admin/moderator?target={self.ids[1]}").json()
        self.assertEqual(self.change("mod_undo",target=self.ids[1],batch=info["batch"],expected_log=999).status_code,409)
        result=self.change("mod_undo",target=self.ids[1],batch=info["batch"],expected_log=info["reviewable"]["last_log"])
        self.assertEqual(result.status_code,200,result.text)
        with db.db() as c:
            self.assertEqual(c.execute("SELECT deleted FROM messages WHERE id=?",(message,)).fetchone()[0],0)
            self.assertTrue(moderator_guard.paused(c,self.ids[1]))
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(),[])

    def test_owner_can_remove_project_associations_but_ordinary_owners_cannot(self):
        address="8.8.8.8:27015"
        with db.db() as c:community.owner_change(c,self.keys[3],address)
        self.assertEqual(self.change("owner_server_remove",3,target=self.ids[3],server=address).status_code,403)
        self.assertEqual(self.change("owner_server_remove",target=self.ids[3],server=address).status_code,200)
        with db.db() as c:self.assertEqual(community.server_owners(c)["owners"],[])

    def test_revoking_head_configuration_invalidates_even_a_cached_retry(self):
        body={"action":"role_grant","target":self.ids[2],"role":"moderator","nonce":"head-cached-rights-01"}
        self.assertEqual(self.request("POST","admin/action",json=body).status_code,200)
        with patch.dict(os.environ,{"CZM_ADMIN_PLAYER_IDS":""}):
            get_settings.cache_clear()
            self.assertEqual(self.request("POST","admin/action",json=body).status_code,403)
        get_settings.cache_clear()

    def test_sanctions_are_paginated_and_visible_on_the_selected_player(self):
        target=self.ids[2]
        for i in range(23):self.assertEqual(self.change("mute_text",target=target,minutes=60,reason=f"Reason {i}").status_code,200)
        first=self.request("GET","admin/sanctions").json();self.assertEqual(len(first["sanctions"]),20);self.assertEqual(first["next"],20)
        second=self.request("GET","admin/sanctions?offset=20").json();self.assertEqual(len(second["sanctions"]),3);self.assertEqual(second["next"],-1)
        detail=self.request("GET",f"admin/player?target={target}").json();self.assertEqual(len(detail["sanctions"]),23)
        sanction=first["sanctions"][0]["id"]
        self.assertEqual(self.change("lift",sanction=sanction,target=target).status_code,200)
        self.assertEqual(len(self.request("GET",f"admin/player?target={target}").json()["sanctions"]),22)

    def test_all_history_undo_includes_reviewed_batches_and_requires_the_current_preview(self):
        target=self.ids[1]
        self.act("mute_text",target=2,actor=1,minutes=60,reason="First batch")
        self.assertEqual(self.change("mod_resume",target=target).status_code,200)
        self.act("mute_voice",target=2,actor=1,minutes=60,reason="Second batch")
        self.assertEqual(self.change("mod_pause",target=target).status_code,200)
        info=self.request("GET",f"admin/moderator?target={target}").json();self.assertEqual(info["reviewable"]["count"],2)
        result=self.change("mod_undo",target=target,all_history=True,expected_log=info["reviewable"]["last_log"])
        self.assertEqual(result.status_code,200,result.text)
        with db.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM bans WHERE moderator=? AND lifted IS NULL",(target,)).fetchone()[0],0)
            self.assertTrue(moderator_guard.paused(c,target))
