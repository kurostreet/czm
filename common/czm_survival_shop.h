#pragma once

#include <climits>
#include <cstring>

namespace CzmSurvivalShop
{
enum Tab { Primary, Pistols, Equipment };
enum Status { Draft, Pending, Purchased, Guest };
enum PurchaseMode { Unavailable, BuyNow, BuyNext };
enum Action { Item = 1, Section, Page, Skip, Confirm, Cancel, Remember, Close, Select = 12 };
enum Notice { NoNotice, NoCredits, SignIn, Locked, Failed, Changed, Refunded, EquipmentBought, EquipmentOwned,
	LoadoutDelivered, LoadoutReserved, LoadoutReplaced };
enum { MaxRows = 6, CanConfirm = 1, CanRemember = 2, CanBuyGear = 4 };

struct Row
{
	int index, weapon, price;
	bool enabled;
};

struct View
{
	int token, tab, page, pages, balance, total, status;
	int remember, primary, pistol, locked, notice, flags;
	bool roundPurchase;
	int preview, mode, currentPrimary, currentPistol, nextPrimary, nextPistol, reserved, windowMs;
	int count;
	Row rows[MaxRows];
};

inline bool RoundWire( const char *text )
{
	return text && std::strncmp( text, "#czms2\t", 7 ) == 0;
}

inline bool Wire( const char *text )
{
	return RoundWire( text ) || ( text && std::strncmp( text, "#czms1\t", 7 ) == 0 );
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
	const bool round = RoundWire( text );
	const char *p = text + 7;
	int v[13];
	if( !Fields( p, v, 13 ) || !v[0] || v[1] > Equipment || v[2] >= v[3] || v[3] > 128 ||
		v[5] > 2000000 || v[6] > Guest || v[7] > 1 || v[8] > 30 || v[9] > 30 ||
		v[10] > 3 || v[11] > ( round ? LoadoutReplaced : EquipmentOwned ) || v[12] > ( round ? 7 : 3 ))
		return false;

	View menu = {};
	menu.token = v[0]; menu.tab = v[1]; menu.page = v[2]; menu.pages = v[3];
	menu.balance = v[4]; menu.total = v[5]; menu.status = v[6]; menu.remember = v[7];
	menu.primary = v[8]; menu.pistol = v[9]; menu.locked = v[10]; menu.notice = v[11]; menu.flags = v[12];
	menu.roundPurchase = round;
	if( round )
	{
		if( std::strncmp( p, "#round\t", 7 ) != 0 ) return false;
		p += 7;
		int fields[8];
		if( !Fields( p, fields, 8 ) || fields[0] > 30 || fields[1] > BuyNext || fields[2] > 30 || fields[3] > 30 ||
			fields[4] > 30 || fields[5] > 30 || fields[6] > 2000000 || fields[7] > 30000 )
			return false;
		menu.preview = fields[0]; menu.mode = fields[1];
		menu.currentPrimary = fields[2]; menu.currentPistol = fields[3];
		menu.nextPrimary = fields[4]; menu.nextPistol = fields[5]; menu.reserved = fields[6];
		menu.windowMs = fields[7];
	}
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
