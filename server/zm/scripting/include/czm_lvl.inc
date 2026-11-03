// Counter Zombie Mobile, Survival server: what czm_lvl.amxx tells the effect plugins.
#if defined _czm_lvl_included
	#endinput
#endif
#define _czm_lvl_included

#pragma reqlib czm_lvl

// Whether the player has a LVL MOD profile loaded (a CZM player).
native bool:czm_lvl_ready(id);

// What the player wears in a shop category ("skin", "knife", "crit", "wsound", ...); "" when nothing.
native czm_lvl_item(id, const cat[], out[], len);

// Seconds left for a weapon crate item ("gold", "mini", "arm50", "arm100", "invis", "blind", "gas"), 0 when none.
native czm_lvl_crate(id, const name[]);

// Invisibility charges left in the crate; czm_lvl_use_charge() spends one (returns 0 when none).
native czm_lvl_charges(id);
native czm_lvl_use_charge(id);

// Tokens from an airdrop: the API checks the amount and adds the tokens boost.
native czm_lvl_reward(id, amount);

// The player's LVL MOD state changed (joined, bought, the site changed something).
forward czm_lvl_changed(id);
