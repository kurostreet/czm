"""Our own servers: the owner sets them in the admin panel, every game shows the cards and the golden frame."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MENU = ROOT / "czm/menu"


def read(name):
    return (MENU / name).read_text()


class OfficialServersTests(unittest.TestCase):
    def test_hello_brings_the_slots_and_an_older_service_keeps_the_cache(self):
        online = read("CzmOnline.cpp")
        self.assertIn('j.Get( 0, "official" )', online)
        self.assertRegex(online, r'if\( j\.Type\( official \) == CzmJson::T_OBJECT \)\s*CZM_OfficialSet\(')
        menu = read("CzmMenu.cpp")
        self.assertIn('#define CZM_OFFICIAL_FILE "official_servers.lst"', menu)

    def test_only_an_address_reaches_the_console(self):
        menu = read("CzmMenu.cpp")
        body = menu[menu.index("static void CZM_OfficialSlot"):menu.index("static void CZM_OfficialLoad")]
        self.assertIn('strspn( address, "0123456789abcdefABCDEF.:[]" ) != strlen( address )', body)
        connect = menu[menu.index("void CZM_ConnectOfficial"):menu.index("// a point on the rounded-rectangle border")]
        self.assertIn("CZM_ServerBlocked( server->address )", connect)

    def test_the_frame_follows_the_address_everywhere(self):
        servers = read("CzmServers.cpp")
        row = servers[servers.index("void CCzmServers::DrawRow"):servers.index("void CCzmServers::DrawEmpty")]
        self.assertIn("CZM_IsOfficial( e.address )", row)
        self.assertIn("CZM_GoldComet(", row)
        self.assertIn("CZM_OfficialBadge(", row)
        # the marks from the right: star, heart, verified shield, then our golden badge first of all
        order = [row.index(k) for k in ("icon_star_on.png", "icon_heart_on.png", "CzmStyle::Verified(", "CZM_OfficialMark(")]
        self.assertEqual(order, sorted(order))
        self.assertNotRegex(row, re.compile(r"CZM_IsOfficial\(\s*e\.name"))
        refresh = servers[servers.index("void CCzmServers::Refresh"):servers.index("void CCzmServers::SetFavorite")]
        self.assertIn("CZM_OfficialServer( i )", refresh)
        main = read("CzmMain.cpp")
        tile = main[main.index("void CCzmMainMenu::DrawTile"):]
        self.assertIn("CZM_IsOfficial( server->address )", tile)

    def test_cards_show_soon_without_an_address_and_join_with_one(self):
        main = read("CzmMain.cpp")
        card = main[main.index("void CCzmMainMenu::DrawOfficial"):main.index("void CCzmMainMenu::DrawTitle")]
        self.assertIn('"Скоро открытие"', card)
        self.assertIn('"Coming soon"', card)
        self.assertIn('"SURVIVAL"', card)
        self.assertIn('"ESCAPE"', card)
        self.assertIn("CZM_GoldComet(", card)
        self.assertIn("CZM_ConnectOfficial( hit - HIT_OFFICIAL )", main)
        self.assertIn("if( CZM_OfficialEnabled( ))", main)

    def test_admin_panel_page(self):
        admin = (ROOT / "android/app/src/main/java/ru/kurostreet/counterzombiemobile/CzmAdmin.java").read_text()
        self.assertIn('"official"', admin)
        self.assertIn('data("action","official_servers","enabled",on[0],"survival"', admin)
        server = (ROOT / "server/czm/czm/admin.py").read_text()
        self.assertIn('kind=="official_servers"', server)
        self.assertIn('section=="official"', server)
        api = (ROOT / "server/czm/czm/api.py").read_text()
        self.assertIn('"official": official.state(conn)', api)
        self.assertIn("czm/official.py", (ROOT / "server/czm/deploy/install.sh").read_text())


if __name__ == "__main__":
    unittest.main()
