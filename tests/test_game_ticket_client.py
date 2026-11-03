"""The CZM ticket reaches our servers only: every place in the menu that connects to a server
first calls CZM_PrepareConnect, which puts the ticket in userinfo for our addresses and clears it
for any other one."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MENU = ROOT / "czm/menu"


class GameTicketClientTests(unittest.TestCase):
    def test_every_connect_is_prepared(self):
        sites = 0
        for path in sorted(MENU.glob("*.cpp")):
            source = path.read_text()
            for match in re.finditer(r'ClientCmdF?\(\s*false\s*,\s*"connect ', source):
                sites += 1
                before = source[max(0, match.start() - 240):match.start()]
                self.assertIn("CZM_PrepareConnect(", before, f"{path.name}: a connect without CZM_PrepareConnect")
        self.assertGreaterEqual(sites, 6)

    def test_ticket_goes_only_to_its_address_and_leaves_userinfo(self):
        source = (MENU / "CzmOnline.cpp").read_text()
        prepare = source[source.index("void CZM_PrepareConnect("):]
        prepare = prepare[:prepare.index("\n}\n")]
        self.assertIn("!strcmp( s_tickets[i].address, address )", prepare)
        self.assertIn('setinfo _czm \\"%s\\"', prepare)
        self.assertIn("s_ticketClearAt = ticket[0] ? now + 60.0 : 0.0;", prepare)
        frame = source[source.index("static void TicketFrame("):source.index("void CZM_PrepareConnect(")]
        self.assertIn('setinfo _czm \\"\\"', frame)
        # a ticket of another profile or for an old address is never kept
        self.assertIn("t.identity != s_online.identity", frame)
        self.assertIn("t.requestIdentity == s_online.identity", frame)
        self.assertIn('"/api/v1/game/ticket"', frame)


if __name__ == "__main__":
    unittest.main()
