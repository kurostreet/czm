"""Only active, registered project owners can mark catalog servers."""
import unittest
from czm import accounts,community,db,server_moderation
import test_community as baseline

A="8.8.8.8:27015"
B="8.8.8.8:27016"

class ServerOwnerCatalogTests(unittest.TestCase):
    setUp=baseline.CommunityTests.setUp

    def owners(self):
        response=self.client.get("/api/v1/servers/owners")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers["cache-control"],"no-store")
        return response.json()["owners"]

    def test_association_is_public_but_only_administrator_assigned_roles_are_used(self):
        self.assertEqual(self.owners(),[])
        with db.db() as c:
            community.owner_change(c,self.keys[3],A,name="Project server")
            c.execute("INSERT INTO owner_servers VALUES(?,?,?,?)",(self.ids[2],B,"Unassigned",1))
        self.assertEqual(self.owners(),[{"server":A,"owner":self.ids[3]}])
        self.assertEqual(set(self.owners()[0]),{"server","owner"})

    def test_removal_revocation_and_account_deletion_remove_the_badge(self):
        with db.db() as c:community.owner_change(c,self.keys[3],A)
        self.assertEqual(len(self.owners()),1)
        with db.db() as c:community.owner_change(c,self.keys[3],A,True)
        self.assertEqual(self.owners(),[])
        with db.db() as c:
            community.owner_change(c,self.keys[3],A)
            community.revoke(c,self.ids[3],"server_owner")
        self.assertEqual(self.owners(),[])
        with db.db() as c:community.grant(c,self.ids[3],"server_owner","Restored")
        self.assertEqual(len(self.owners()),1)
        with db.db() as c:accounts.delete_account(c,self.keys[3],"Password123","test-ip")
        self.assertEqual(self.owners(),[])

    def test_duplicate_claims_are_deterministic_and_global_restrictions_win(self):
        with db.db() as c:
            community.owner_change(c,self.keys[3],A)
            community.grant(c,self.ids[2],"server_owner","Other project")
            community.owner_change(c,self.keys[2],A)
        entries=self.owners();self.assertEqual(len(entries),1)
        self.assertEqual(entries,self.owners())
        with db.db() as c:server_moderation.set_blocked(c,A,True,"owner","Review")
        self.assertEqual(self.owners(),[])
        with db.db() as c:server_moderation.set_blocked(c,A,False,"owner","")
        self.assertEqual(len(self.owners()),1)
