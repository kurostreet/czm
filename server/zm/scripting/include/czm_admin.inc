// Counter Zombie Mobile, Survival server: what czm_admin.amxx gives the other plugins.
#if defined _czm_admin_included
	#endinput
#endif
#define _czm_admin_included

enum
{
	CZM_STAFF_NONE = 0,
	CZM_STAFF_MODERATOR,
	CZM_STAFF_ADMIN
}

#if defined CZM_ADMIN_PLUGIN
	#endinput
#endif
#pragma reqlib czm_admin

// The player's place in the staff (CZM_STAFF_*), from the API; guests are never staff.
native czm_staff(id);

// Whether the player is muted now (chat and voice).
native bool:czm_muted(id);

// A ban or a mute ("ban" | "mute") for that many seconds (0 = forever, staff only). by 0 is the
// players' vote, else the staff member who gives it. The API keeps it, this server enforces it.
native czm_sanction(target, const kind[], seconds, const reason[], by = 0);

// Opens the admin menu (staff only).
native czm_admin_menu(id);

// Kontra's privilege of the player: 0 none, 1 VIP+, 2 PREMIUM, 3 DELUXE, 4 TESTER.
native czm_privilege(id);

// Its name as shown in chat ("VIP+"), empty when there is none.
native czm_privilege_name(id, out[], len);
