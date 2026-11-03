// Counter Zombie Mobile, Survival server: calls to the CZM API from the plugins.
// The game server proves itself with X-CZM-Server = sha256("<ticket key>|server") (survival.check_server).
#if defined _czm_api_included
	#endinput
#endif
#define _czm_api_included

#include <easy_http>

#define CZM_JSON_NONE EzInvalid_JSON
#define CZM_JSON_OK(%1) (%1 != EzInvalid_JSON)

stock g_czmApiToken[65];
stock g_czmApiCvar, g_czmApiMode;

// Call in plugin_cfg: reads the ticket key once. Returns false when the key is missing.
stock bool:czm_api_init()
{
	g_czmApiCvar = get_cvar_pointer("czm_api_url");
	if (!g_czmApiCvar)
		g_czmApiCvar = create_cvar("czm_api_url", "http://127.0.0.1:8200", FCVAR_PROTECTED, "Where the CZM API answers");
	// the server mode: survival or escape, each with its own economy in the API
	g_czmApiMode = get_cvar_pointer("czm_server_name");
	if (!g_czmApiMode)
		g_czmApiMode = create_cvar("czm_server_name", "survival", FCVAR_SERVER, "survival or escape");
	new path[128], key[96], message[128];
	get_localinfo("amxx_configsdir", path, charsmax(path));
	add(path, charsmax(path), "/czm_ticket.key");
	new fh = fopen(path, "rt");
	if (!fh)
		return false;
	fgets(fh, key, charsmax(key));
	fclose(fh);
	trim(key);
	formatex(message, charsmax(message), "%s|server", key);
	hash_string(message, Hash_Sha256, g_czmApiToken, charsmax(g_czmApiToken));
	return true;
}

stock bool:czm_api_ready()
{
	return g_czmApiToken[0] != 0;
}

// GET or POST /api/v1<path>; the callback gets (EzHttpRequest:request), data travels with it.
stock czm_api(const method[], const path[], EzJSON:body, const callback[], const data[] = "", len = 0)
{
	new url[192];
	get_pcvar_string(g_czmApiCvar, url, charsmax(url));
	add(url, charsmax(url), "/api/v1");
	add(url, charsmax(url), path);
	new mode[24];
	get_pcvar_string(g_czmApiMode, mode, charsmax(mode));
	if (mode[0])
	{
		add(url, charsmax(url), contain(path, "?") != -1 ? "&mode=" : "?mode=");
		add(url, charsmax(url), mode);
	}
	new EzHttpOptions:opt = ezhttp_create_options();
	ezhttp_option_set_header(opt, "Content-Type", "application/json");
	ezhttp_option_set_header(opt, "X-CZM-Server", g_czmApiToken);
	ezhttp_option_set_timeout(opt, 8000);
	ezhttp_option_set_connect_timeout(opt, 3000);
	if (len)
		ezhttp_option_set_user_data(opt, data, len);
	if (CZM_JSON_OK(body))
		ezhttp_option_set_body_from_json(opt, body);
	if (equal(method, "GET"))
		ezhttp_get(url, callback, opt);
	else
		ezhttp_post(url, callback, opt);
}

// The JSON answer and the HTTP code (0 when the API did not answer). Free the JSON when it is valid.
stock EzJSON:czm_api_answer(EzHttpRequest:request, &code)
{
	code = 0;
	if (ezhttp_get_error_code(request) != EZH_OK)
		return CZM_JSON_NONE;
	code = ezhttp_get_http_code(request);
	return ezhttp_parse_json_response(request);
}

// "1h 30m", "2d", "forever": how long a ban or a mute still lasts (-1 = forever).
stock czm_api_left(seconds, out[], len, lang)
{
	if (seconds < 0)
		return copy(out, len, lang ? "forever" : "навсегда");
	new days = seconds / 86400, hours = (seconds % 86400) / 3600;
	if (days)
		return formatex(out, len, lang ? "%dd %dh" : "%dд %dч", days, hours);
	if (hours)
		return formatex(out, len, lang ? "%dh %dm" : "%dч %dмин", hours, (seconds % 3600) / 60);
	return formatex(out, len, lang ? "%dm" : "%dмин", max(1, (seconds + 59) / 60));
}
