"""The CZM ticket reaches our servers only: every place in the menu that connects to a server
first calls CZM_PrepareConnect, which puts the ticket in userinfo for our addresses and clears it
for any other one."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MENU = ROOT / "czm/menu"


class GameTicketClientTests(unittest.TestCase):
    def test_configured_endpoint_remains_trusted_when_home_cards_are_hidden(self):
        from test_loading_errors import function
        from test_server_menu_transport import run_cpp, CPP_MENU
        menu = (MENU / 'CzmMenu.cpp').read_text()
        online = (MENU / 'CzmOnline.cpp').read_text()
        code = CPP_MENU + r'''
#define CZM_OFFICIAL_COUNT 2
struct CzmServer { char address[64]; };
static CzmServer s_official[2];static bool s_officialOn=false;
static void CZM_OfficialLoad(){}
static const char *connected="203.0.113.10:27016";
namespace EngFuncs {static const char *GetCvarString(const char*){return connected;}}
'''
        for src, sig in [(menu, 'CzmServer *CZM_ConfiguredServer('),
                         (menu, 'CzmServer *CZM_OfficialServer('),
                         (online, 'int CZM_OfficialSlotNow(')]:
            code += function(src, sig) + '\n'
        code += r'''
int main(){
 strcpy(s_official[0].address,"203.0.113.10:27016");
 assert(CZM_ConfiguredServer(0)&&!CZM_OfficialServer(0)&&CZM_OfficialSlotNow()==0);
 assert(!CZM_ConfiguredServer(-1)&&!CZM_ConfiguredServer(2)&&!CZM_ConfiguredServer(1));
 connected="198.51.100.4:27015";assert(CZM_OfficialSlotNow()==-1);
 connected="";assert(CZM_OfficialSlotNow()==-1);
 s_officialOn=true;assert(CZM_OfficialServer(0)==CZM_ConfiguredServer(0));
}
'''
        run_cpp(code)
        frame = online[online.index('static void TicketFrame('):online.index('void CZM_PrepareConnect(')]
        self.assertIn('CZM_ConfiguredServer( i )', frame)

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

    def test_panel_opens_only_our_site_and_only_from_our_servers(self):
        source = (MENU / "CzmOnline.cpp").read_text()
        opener = source[source.index("static void CZM_PanelOpen_f("):source.index("ADD_COMMAND( czm_panel")]
        # another server cannot make the game open a browser
        self.assertIn("CL_IsActive( ) && !CZM_OnOfficialServer( )", opener)
        self.assertIn('"/api/v1/auth/web-link"', opener)
        frame = source[source.index("static void PanelFrame("):]
        frame = frame[:frame.index("\n}\n")]
        self.assertIn('"https://counter-zombie.ru/panel#login="', frame)
        self.assertIn("!strncmp( url, prefix, sizeof( prefix ) - 1 )", frame)
        self.assertIn("EngFuncs::ShellExecute( url", frame)


if __name__ == "__main__":
    unittest.main()
