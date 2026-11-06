#pragma once

#include <climits>
#include <cstring>

namespace CzmSurvivalShop
{
enum Tab { Primary, Pistols, Equipment };
enum Status { Draft, Pending, Purchased, Guest };
enum Action { Item = 1, Section, Page, Skip, Confirm, Cancel, Remember, Close };
enum Notice { NoNotice, NoCredits, SignIn, Locked, Failed, Changed, Refunded, EquipmentBought, EquipmentOwned };
enum { MaxRows = 6, CanConfirm = 1, CanRemember = 2 };

struct Row
{
	int index, weapon, price;
	bool enabled;
};

struct View
{
	int token, tab, page, pages, balance, total, status;
	int remember, primary, pistol, locked, notice, flags;
	int count;
	Row rows[MaxRows];
};

inline bool Wire( const char *text )
{
	return text && std::strncmp( text, "#czms1\t", 7 ) == 0;
}

// Each field is an unsigned decimal integer with a fixed delimiter. Do not
// accept truncation or overflow from a server-provided ShowMenu.
inline bool Fields( const char *&p, int *out, int count )
{
	for( int i = 0; i < count; ++i )
	{
		if( *p < '0' || *p > '9' ) return false;
		int value = 0;
		do
		{
			const int digit = *p++ - '0';
			if( value > ( INT_MAX - digit ) / 10 ) return false;
			value = value * 10 + digit;
		}
		while( *p >= '0' && *p <= '9' );
		out[i] = value;
		if( i + 1 < count )
		{
			if( *p != '\t' ) return false;
			++p;
		}
	}
	if( *p != '\n' ) return false;
	++p;
	return true;
}

inline bool Parse( const char *text, View &out )
{
	if( !Wire( text )) return false;
	const char *p = text + 7;
	int v[13];
	if( !Fields( p, v, 13 ) || !v[0] || v[1] > Equipment || v[2] >= v[3] || v[3] > 128 ||
		v[5] > 2000000 || v[6] > Guest || v[7] > 1 || v[8] > 30 || v[9] > 30 ||
		v[10] > 3 || v[11] > EquipmentOwned || v[12] > 3 )
		return false;

	View menu = {};
	menu.token = v[0]; menu.tab = v[1]; menu.page = v[2]; menu.pages = v[3];
	menu.balance = v[4]; menu.total = v[5]; menu.status = v[6]; menu.remember = v[7];
	menu.primary = v[8]; menu.pistol = v[9]; menu.locked = v[10]; menu.notice = v[11]; menu.flags = v[12];
	while( std::strncmp( p, "#item\t", 6 ) == 0 )
	{
		p += 6;
		int r[4];
		if( menu.count == MaxRows || !Fields( p, r, 4 ) || r[0] != menu.count ||
			r[1] > 30 || r[2] > 1000000 || r[3] > 1 )
			return false;
		if( menu.tab == Equipment )
		{
			static const int equipment[] = { 4, 25, 9, 0 };
			if( menu.count >= 4 || r[1] != equipment[menu.count] ) return false;
		}
		menu.rows[menu.count++] = { r[0], r[1], r[2], r[3] != 0 };
	}
	if( menu.tab == Equipment && menu.count != 4 ) return false;
	out = menu;
	return true;
}
}
