"""LVL MOD of the Survival server, ported from the Kontra server (LVL_MOD_v82).

The API keeps every number: levels, tokens, what a player owns and wears, the battle pass, the
market. Game servers report what happened in the game (play time, kills, rounds) and pass on
what a player chose in the game menu; the site calls the same functions. A game server never
decides a price or a balance, it only shows the result.

Rules from the Kontra configuration:
* level: +1 for every 10 minutes in the game and for every 10 kills, plus bought levels;
* tokens: a human killing a zombie +1, surviving a round as a human +3, every 10 minutes +2;
  the tokens boost doubles them, the level boost doubles the levels earned while it runs;
* shop: 8 categories of things to wear, upgrades, the weapon crate, the battle pass;
* transfers: from level 10, at most 100 tokens a day;
* market: up to 3 offers for 7 days, the seller pays 5%.

Every action that spends tokens carries an operation id from its caller; repeating it returns
the first result and spends nothing twice.
"""
import json
import secrets
import sqlite3
import time

from . import accounts
from .db import now

LVL_TIME = 600
LVL_KILLS = 10
TOK_KILL, TOK_SURVIVE, TOK_TIME = 1, 3, 2

PRICE_LVL10, LVL10_AMOUNT = 1000, 10
BOOST_HOURS, PRICE_BOOST_LVL, PRICE_BOOST_TOK = 3, 1500, 250

PAY_MIN_LVL, PAY_DAILY_LIMIT = 10, 100
MARKET_DAYS, MARKET_MAX, MARKET_TAX = 7, 3, 5
MAP_TOP_REWARDS = (15, 10, 5)

BP_PRICE, BP_DAYS, BP_DAILY = 12000, 31, 1000
BP_FINAL_LVL, BP_FINAL_TOK, BP_PREFIX = 200, 50000, "battlepass"
BP_TASKS = [
    ("k50", "kills", 50, 100, "Убить 50 зомби", "Kill 50 zombies"),
    ("k100", "kills", 100, 200, "Убить 100 зомби", "Kill 100 zombies"),
    ("k200", "kills", 200, 400, "Убить 200 зомби", "Kill 200 zombies"),
    ("k500", "kills", 500, 1000, "Убить 500 зомби", "Kill 500 zombies"),
    ("t1", "time", 3600, 50, "Отыграть 1 час", "Play 1 hour"),
    ("t3", "time", 10800, 150, "Отыграть 3 часа", "Play 3 hours"),
    ("t6", "time", 21600, 300, "Отыграть 6 часов", "Play 6 hours"),
    ("t12", "time", 43200, 600, "Отыграть 12 часов", "Play 12 hours"),
    ("t24", "time", 86400, 1200, "Отыграть 24 часа", "Play 24 hours"),
    ("w10", "ctwin", 10, 20, "Выиграть 10 раундов за людей", "Win 10 rounds as a human"),
    ("w20", "ctwin", 20, 40, "Выиграть 20 раундов за людей", "Win 20 rounds as a human"),
    ("w40", "ctwin", 40, 80, "Выиграть 40 раундов за людей", "Win 40 rounds as a human"),
    ("w80", "ctwin", 80, 160, "Выиграть 80 раундов за людей", "Win 80 rounds as a human"),
    ("w100", "ctwin", 100, 200, "Выиграть 100 раундов за людей", "Win 100 rounds as a human"),
    ("sp1k", "spent", 1000, 100, "Потратить 1000 токенов", "Spend 1000 tokens"),
    ("sp5k", "spent", 5000, 500, "Потратить 5000 токенов", "Spend 5000 tokens"),
    ("sp10k", "spent", 10000, 1000, "Потратить 10000 токенов", "Spend 10000 tokens"),
    ("d7", "days", 7, 3000, "Отметиться 7 дней", "Check in 7 days"),
    ("d14", "days", 14, 6000, "Отметиться 14 дней", "Check in 14 days"),
    ("d31", "days", 31, 10000, "Отметиться 31 день", "Check in 31 days"),
    ("g1k", "sent", 1000, 200, "Отправить игроку 1000 токенов", "Send a player 1000 tokens"),
    ("g2k", "sent", 2000, 400, "Отправить игроку 2000 токенов", "Send a player 2000 tokens"),
    ("g4k", "sent", 4000, 800, "Отправить игроку 4000 токенов", "Send a player 4000 tokens"),
    ("g5k", "sent", 5000, 1000, "Отправить игроку 5000 токенов", "Send a player 5000 tokens"),
]

# Things to wear. "model" is the player model the game puts on; the Kontra names that have no
# model of their own yet wear the nearest stock one until their models are added.
CATEGORIES = {
    "prefix": {"ru": "Префиксы", "en": "Prefixes", "items": [
        {"id": "noob", "ru": "НУБ", "en": "NOOB"}, {"id": "bot", "ru": "БОТ", "en": "BOT"},
        {"id": "pro", "ru": "ПРО", "en": "PRO"}, {"id": "king", "ru": "КИНГ", "en": "KING"},
        {"id": "boss", "ru": "БОСС", "en": "BOSS"}, {"id": "legend", "ru": "ЛЕГЕНДА", "en": "LEGEND"},
        {"id": "master", "ru": "МАСТЕР", "en": "MASTER"}, {"id": "guru", "ru": "ГУРУ", "en": "GURU"},
        {"id": "titan", "ru": "ТИТАН", "en": "TITAN"}, {"id": "lord", "ru": "ЛОРД", "en": "LORD"},
        {"id": "demon", "ru": "ДЕМОН", "en": "DEMON"}, {"id": "warrior", "ru": "ВОИН", "en": "WARRIOR"},
        # the battle pass reward: never sold in the shop, may be resold on the market
        {"id": "battlepass", "ru": "BATTLE PASS", "en": "BATTLE PASS", "shop": False},
    ], "price": 2500},
    "prefcolor": {"ru": "Цвет префикса", "en": "Prefix colour", "items": [
        {"id": "#FF0000", "ru": "Красный", "en": "Red"}, {"id": "#FFFF00", "ru": "Жёлтый", "en": "Yellow"},
        {"id": "#00FF00", "ru": "Зелёный", "en": "Green"}, {"id": "#0088FF", "ru": "Синий", "en": "Blue"},
        {"id": "#00FFFF", "ru": "Голубой", "en": "Cyan"}, {"id": "#FF8800", "ru": "Оранжевый", "en": "Orange"},
        {"id": "#FF66CC", "ru": "Розовый", "en": "Pink"}, {"id": "#AA00FF", "ru": "Фиолетовый", "en": "Purple"},
        {"id": "#FFD700", "ru": "Золотой", "en": "Gold"}, {"id": "#FFFFFF", "ru": "Белый", "en": "White"},
    ], "price": 2500},
    "skin": {"ru": "Скины людей", "en": "Human skins", "items": [
        {"id": "sas", "ru": "Sas", "en": "Sas", "model": "sas"},
        {"id": "gsg9", "ru": "Gsg9", "en": "Gsg9", "model": "gsg9"},
        {"id": "gsg9_admin", "ru": "Gsg9 admin", "en": "Gsg9 admin", "model": "gsg9"},
        {"id": "gign", "ru": "Gign", "en": "Gign", "model": "gign"},
        {"id": "sas_custom", "ru": "Sas custom", "en": "Sas custom", "model": "sas"},
        {"id": "elite_arctic", "ru": "Elite arctic", "en": "Elite arctic", "model": "arctic"},
        {"id": "leet", "ru": "Leet", "en": "Leet", "model": "leet"},
        {"id": "leet_pirate", "ru": "Leet pirate", "en": "Leet pirate", "model": "leet"},
        {"id": "professional", "ru": "Professional", "en": "Professional", "model": "urban"},
        {"id": "survivor", "ru": "Survivor", "en": "Survivor", "model": "terror", "price": 10000},
    ], "price": 5000},
    "skincolor": {"ru": "Свечение скина", "en": "Skin glow", "items": [
        {"id": "#0044FF", "ru": "Синий", "en": "Blue"}, {"id": "#0000FF", "ru": "Тёмно-синий", "en": "Navy"},
        {"id": "#00AAFF", "ru": "Голубой", "en": "Light blue"}, {"id": "#00FFFF", "ru": "Морской", "en": "Cyan"},
        {"id": "#00FFAA", "ru": "Бирюзовый", "en": "Teal"}, {"id": "#00CC00", "ru": "Зелёный", "en": "Green"},
        {"id": "#00FF00", "ru": "Лайм", "en": "Lime"}, {"id": "#FFFF00", "ru": "Жёлтый", "en": "Yellow"},
        {"id": "#FFD700", "ru": "Золотой", "en": "Gold"}, {"id": "#FFFFFF", "ru": "Белый", "en": "White"},
    ], "price": 2500},
    "crit": {"ru": "Критический выстрел", "en": "Critical shot", "items": [
        {"id": "fire", "ru": "Зажигательная пуля", "en": "Incendiary bullet", "price": 5300},
        {"id": "freeze", "ru": "Замораживающая пуля", "en": "Freezing bullet", "price": 5600},
        {"id": "dmg2", "ru": "Урон ×2 пуля", "en": "Damage ×2 bullet", "price": 5400},
    ], "price": 5300},
    "minimap": {"ru": "Мини-карта", "en": "Minimap", "items": [
        {"id": "minimap", "ru": "Мини-карта", "en": "Minimap", "price": 7000},
    ], "price": 7000},
    "wsound": {"ru": "Звуки оружия", "en": "Weapon sounds", "items": [
        {"id": "gold_ak_guitar", "ru": "Золотой АК47 — гитара", "en": "Golden AK47 — guitar"},
        {"id": "minigun_mg", "ru": "Миниган", "en": "Minigun"},
        {"id": "gold_deagle_laser", "ru": "Золотой дигл — лазер", "en": "Golden Deagle — laser"},
        {"id": "knife_starwars", "ru": "Нож — Star Wars", "en": "Knife — Star Wars"},
    ], "price": 6500},
    "knife": {"ru": "Ножи людей", "en": "Human knives", "items": [
        {"id": "glass", "ru": "Стеклянный нож", "en": "Glass knife"},
        {"id": "katana", "ru": "Катана", "en": "Katana"},
        {"id": "axe", "ru": "Топор", "en": "Axe"},
        # head administrators only, free, never sold or passed on
        {"id": "sickle", "ru": "Серп", "en": "Sickle", "price": 0, "admin": True, "shop": False},
    ], "price": 5000},
}

UPGRADES = {
    "lvl10": {"ru": f"+{LVL10_AMOUNT} LVL", "en": f"+{LVL10_AMOUNT} LVL", "price": PRICE_LVL10},
    "lvl_boost": {"ru": f"LVL ×2 на {BOOST_HOURS} ч", "en": f"LVL ×2 for {BOOST_HOURS} h", "price": PRICE_BOOST_LVL},
    "tok_boost": {"ru": f"Токены ×2 на {BOOST_HOURS} ч", "en": f"Tokens ×2 for {BOOST_HOURS} h", "price": PRICE_BOOST_TOK},
}

# The weapon crate: temporary help for a human, 30 minutes from the purchase (Kontra CRATE_*).
CRATE_SECONDS = 1800
CRATE_INVIS_CHARGES = 3
CRATE = {
    "gold": {"ru": "Золотой АК47 и дигл", "en": "Golden AK47 and Deagle", "price": 300},
    "mini": {"ru": "Миниган и гранаты", "en": "Minigun and grenades", "price": 500},
    "arm50": {"ru": "50 брони каждый раунд", "en": "50 armour every round", "price": 50},
    "arm100": {"ru": "100 брони каждый раунд", "en": "100 armour every round", "price": 100},
    "invis": {"ru": "Авто-невидимость ×3", "en": "Auto invisibility ×3", "price": 150},
    "blind": {"ru": "Ослепляющий нож", "en": "Blinding knife", "price": 200},
    "gas": {"ru": "Противогаз", "en": "Gas mask", "price": 80},
}
# Airdrop packs a game server may hand out (Kontra AIR_TOKEN_TABLE)
AIRDROP_TOKENS = (10, 25, 50, 75, 100, 150, 250, 500)

SCHEMA = """
CREATE TABLE IF NOT EXISTS survival_players (
 player INTEGER PRIMARY KEY, nick TEXT NOT NULL DEFAULT '',
 time_sec INTEGER NOT NULL DEFAULT 0, kills INTEGER NOT NULL DEFAULT 0, deaths INTEGER NOT NULL DEFAULT 0,
 matches INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0,
 bonus_lvl INTEGER NOT NULL DEFAULT 0, lvl_boost_until INTEGER NOT NULL DEFAULT 0,
 tok_boost_until INTEGER NOT NULL DEFAULT 0, owned TEXT NOT NULL DEFAULT '{}', equipped TEXT NOT NULL DEFAULT '{}',
 bp TEXT NOT NULL DEFAULT '{}', crate TEXT NOT NULL DEFAULT '{}', pay_day TEXT NOT NULL DEFAULT '', pay_today INTEGER NOT NULL DEFAULT 0,
 first_seen INTEGER NOT NULL DEFAULT 0, last_seen INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS survival_players_lvl ON survival_players(bonus_lvl, time_sec, kills);
CREATE TABLE IF NOT EXISTS survival_ops (
 op TEXT PRIMARY KEY, player INTEGER NOT NULL, result TEXT NOT NULL, time INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS survival_reports (batch TEXT PRIMARY KEY, time INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS survival_promos (
 code TEXT PRIMARY KEY, kind TEXT NOT NULL, amount INTEGER NOT NULL, created INTEGER NOT NULL,
 actor INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS survival_promo_uses (
 code TEXT NOT NULL, player INTEGER NOT NULL, time INTEGER NOT NULL, PRIMARY KEY (code, player)
);
CREATE TABLE IF NOT EXISTS survival_market (
 id INTEGER PRIMARY KEY AUTOINCREMENT, seller INTEGER NOT NULL, cat TEXT NOT NULL, item TEXT NOT NULL,
 price INTEGER NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'open',
 buyer INTEGER NOT NULL DEFAULT 0, closed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS survival_market_open ON survival_market(state, expires);
CREATE TABLE IF NOT EXISTS survival_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER NOT NULL, player INTEGER NOT NULL, kind TEXT NOT NULL,
 amount INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS survival_log_player ON survival_log(player, id);
CREATE TABLE IF NOT EXISTS survival_live (server TEXT PRIMARY KEY, data TEXT NOT NULL, time INTEGER NOT NULL);
"""


def migrate(conn: sqlite3.Connection):
    have = {r[1] for r in conn.execute("PRAGMA table_info(survival_players)")}
    if "crate" not in have:
        try:
            conn.execute("ALTER TABLE survival_players ADD COLUMN crate TEXT NOT NULL DEFAULT '{}'")
        except sqlite3.OperationalError as error:  # the other process was first
            if "duplicate column" not in str(error):
                raise


class Error(accounts.AuthError):
    """A refused action; the code is what the game and the site translate."""


# ---------------------------------------------------------------- the catalog

def item(cat: str, item_id: str) -> dict | None:
    for entry in CATEGORIES.get(cat, {}).get("items", []):
        if entry["id"].lower() == (item_id or "").lower():
            return entry
    return None


def price(cat: str, entry: dict) -> int:
    return entry.get("price", CATEGORIES[cat]["price"])


def sellable(cat: str, entry: dict) -> bool:
    return not entry.get("admin")


def catalog() -> dict:
    cats = []
    for key, cat in CATEGORIES.items():
        cats.append({"key": key, "ru": cat["ru"], "en": cat["en"], "items": [
            {"id": e["id"], "ru": e["ru"], "en": e["en"], "price": price(key, e), "shop": e.get("shop", True),
             **({"model": e["model"]} if "model" in e else {}), **({"admin": True} if e.get("admin") else {})}
            for e in cat["items"]]})
    return {
        "categories": cats,
        "upgrades": [{"id": k, **v} for k, v in UPGRADES.items()],
        "crate": {"seconds": CRATE_SECONDS, "items": [{"id": k, **v} for k, v in CRATE.items()]},
        "battlepass": {"price": BP_PRICE, "days": BP_DAYS, "daily": BP_DAILY, "final": {
            "lvl": BP_FINAL_LVL, "tokens": BP_FINAL_TOK, "prefix": BP_PREFIX},
            "tasks": [{"id": t[0], "kind": t[1], "goal": t[2], "reward": t[3], "ru": t[4], "en": t[5]} for t in BP_TASKS]},
        "pay": {"min_lvl": PAY_MIN_LVL, "daily": PAY_DAILY_LIMIT, "amounts": [10, 50, 100]},
        "market": {"days": MARKET_DAYS, "max": MARKET_MAX, "tax": MARKET_TAX},
    }


# ---------------------------------------------------------------- players

def _row(conn, player: int):
    return conn.execute("SELECT * FROM survival_players WHERE player=?", (player,)).fetchone()


def ensure(conn: sqlite3.Connection, player: int, nick: str = "") -> sqlite3.Row:
    if not conn.execute("SELECT 1 FROM players WHERE id=?", (player,)).fetchone():
        raise Error("player", 404)
    t = now()
    conn.execute("INSERT INTO survival_players(player, nick, first_seen, last_seen) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(player) DO NOTHING", (player, (nick or "")[:32], t, t))
    if nick:
        conn.execute("UPDATE survival_players SET nick=? WHERE player=? AND nick<>?", (nick[:32], player, nick[:32]))
    return _row(conn, player)


def natural_lvl(time_sec: int, kills: int) -> int:
    return time_sec // LVL_TIME + kills // LVL_KILLS


def lvl(row) -> int:
    return max(1, natural_lvl(row["time_sec"], row["kills"]) + row["bonus_lvl"])


def _json(text: str) -> dict:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _bp_active(bp: dict, t: int) -> bool:
    return bool(bp.get("until", 0) > t)


def _today(t: int) -> str:
    # the day turns at midnight Moscow time, as on the Kontra server
    return time.strftime("%Y%m%d", time.gmtime(t + 3 * 3600))


def state(conn, player: int, t: int | None = None) -> dict:
    row = _row(conn, player)
    if row is None:
        raise Error("player", 404)
    t = t or now()
    bp = _json(row["bp"])
    owned = _json(row["owned"])
    level = lvl(row)
    matches = row["matches"]
    return {
        "id": row["player"], "nick": row["nick"], "lvl": level, "tokens": row["tokens"],
        "kills": row["kills"], "deaths": row["deaths"], "time": row["time_sec"], "matches": matches,
        "wins": row["wins"], "wr": round(row["wins"] * 100 / matches) if matches else 0,
        "kd": round(row["kills"] / row["deaths"], 2) if row["deaths"] else float(row["kills"]),
        "next_lvl_kills": LVL_KILLS - row["kills"] % LVL_KILLS,
        "next_lvl_time": LVL_TIME - row["time_sec"] % LVL_TIME,
        "boosts": {"lvl": max(0, row["lvl_boost_until"] - t), "tokens": max(0, row["tok_boost_until"] - t)},
        "owned": {cat: sorted(owned.get(cat, [])) for cat in CATEGORIES},
        "equipped": _json(row["equipped"]),
        "battlepass": {
            "active": _bp_active(bp, t), "left": max(0, bp.get("until", 0) - t),
            "daily": _bp_active(bp, t) and bp.get("daily") != _today(t),
            "progress": {k: bp.get(k, 0) for k in ("kills", "time", "ctwin", "spent", "sent", "days")},
            "claimed": sorted(bp.get("claimed", [])), "final": sorted(bp.get("final", [])),
        },
        "pay": {"today": row["pay_today"] if row["pay_day"] == _today(t) else 0, "limit": PAY_DAILY_LIMIT},
        "crate": _crate_state(_json(row["crate"]), t),
        "first_seen": row["first_seen"], "revision": row["revision"],
    }


def _save(conn, player: int, **fields):
    for key in ("owned", "equipped", "bp", "crate"):
        if key in fields:
            fields[key] = json.dumps(fields[key], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE survival_players SET {sets}, revision=revision+1 WHERE player=?", (*fields.values(), player))


def _log(conn, player: int, kind: str, amount: int = 0, detail: str = ""):
    conn.execute("INSERT INTO survival_log(time, player, kind, amount, detail) VALUES (?, ?, ?, ?, ?)",
                 (now(), player, kind, amount, detail[:200]))


def _bp_claim(bp: dict) -> int:
    """Pays every finished battle pass task once; returns the tokens it gave."""
    claimed = set(bp.get("claimed", []))
    gained = 0
    for task_id, kind, goal, reward, *_ in BP_TASKS:
        if task_id not in claimed and bp.get(kind, 0) >= goal:
            claimed.add(task_id)
            gained += reward
    bp["claimed"] = sorted(claimed)
    return gained


# ---------------------------------------------------------------- what the game reports

def report(conn: sqlite3.Connection, batch: str, entries: list[dict]) -> dict:
    """Applies one batch from a game server. A repeated batch changes nothing.

    entry: {"player", "nick", "time", "kills", "zkills", "deaths", "rounds", "wins", "survived", "ctwins"}
    zkills are kills of zombies by a human (they pay tokens), survived are rounds a human lived
    through. Returns {"events": {player: [...]}, "states": {player: state}}.
    """
    t = now()
    if conn.execute("SELECT 1 FROM survival_reports WHERE batch=?", (batch,)).fetchone():
        return {"events": {}, "states": {}, "repeat": True}
    conn.execute("INSERT INTO survival_reports(batch, time) VALUES (?, ?)", (batch, t))
    conn.execute("DELETE FROM survival_reports WHERE time<?", (t - 7 * 86400,))
    events, states = {}, {}
    for entry in entries[:64]:
        player = int(entry.get("player") or 0)
        if player <= 0:
            continue
        try:
            row = ensure(conn, player, str(entry.get("nick") or ""))
        except Error:
            continue
        add = {k: max(0, min(int(entry.get(k) or 0), cap)) for k, cap in
               (("time", 3600), ("kills", 500), ("zkills", 500), ("deaths", 500), ("rounds", 60),
                ("wins", 60), ("survived", 60), ("ctwins", 60))}
        tok_boost = row["tok_boost_until"] > t
        lvl_boost = row["lvl_boost_until"] > t
        before_lvl = lvl(row)
        time_sec, kills = row["time_sec"] + add["time"], row["kills"] + add["kills"]
        gained_natural = natural_lvl(time_sec, kills) - natural_lvl(row["time_sec"], row["kills"])
        bonus = row["bonus_lvl"] + (gained_natural if lvl_boost else 0)
        time_ticks = time_sec // LVL_TIME - row["time_sec"] // LVL_TIME
        mult = 2 if tok_boost else 1
        gain = {"kill": add["zkills"] * TOK_KILL * mult, "survive": add["survived"] * TOK_SURVIVE * mult,
                "time": time_ticks * TOK_TIME * mult}
        bp = _json(row["bp"])
        if _bp_active(bp, t):
            bp["kills"] = bp.get("kills", 0) + add["kills"]
            bp["time"] = bp.get("time", 0) + add["time"]
            bp["ctwin"] = bp.get("ctwin", 0) + add["ctwins"]
            gain["battlepass"] = _bp_claim(bp)
        tokens = row["tokens"] + sum(gain.values())
        _save(conn, player, time_sec=time_sec, kills=kills, deaths=row["deaths"] + add["deaths"],
              matches=row["matches"] + add["rounds"], wins=row["wins"] + add["wins"], tokens=tokens,
              bonus_lvl=bonus, bp=bp, last_seen=t)
        out = [{"type": "tokens", "reason": k, "amount": v} for k, v in gain.items() if v]
        after = state(conn, player, t)
        if after["lvl"] > before_lvl:
            out.append({"type": "level", "lvl": after["lvl"]})
        if out:
            events[player] = out
        states[player] = after
    return {"events": events, "states": states}


def map_end(conn: sqlite3.Connection, batch: str, kills: dict[int, int]) -> list[dict]:
    """The map is over: the three best killers get 15, 10 and 5 tokens. Returns the top."""
    if conn.execute("SELECT 1 FROM survival_reports WHERE batch=?", (batch,)).fetchone():
        return []
    conn.execute("INSERT INTO survival_reports(batch, time) VALUES (?, ?)", (batch, now()))
    top = sorted(((int(p), int(k)) for p, k in kills.items() if int(k) > 0), key=lambda x: (-x[1], x[0]))
    result = []
    for place, (player, count) in enumerate(top[:10], 1):
        reward = MAP_TOP_REWARDS[place - 1] if place <= len(MAP_TOP_REWARDS) else 0
        row = _row(conn, player)
        if row is None:
            continue
        if reward:
            _save(conn, player, tokens=row["tokens"] + reward)
            _log(conn, player, "map_top", reward, f"place {place}")
        result.append({"place": place, "player": player, "nick": row["nick"], "kills": count, "reward": reward})
    return result


# ---------------------------------------------------------------- actions

def _admin(conn, player: int) -> bool:
    from . import admin
    return bool(admin.allowed(conn, player))


def _spend(row, amount: int):
    if amount < 0 or row["tokens"] < amount:
        raise Error("tokens", 409)


def action(conn: sqlite3.Connection, player: int, op: str, name: str, args: dict, server: bool = False) -> dict:
    """One action of a player, from the game menu or the site. Idempotent by op."""
    op = (op or "").strip()
    if not 8 <= len(op) <= 80:
        raise Error("op")
    done = conn.execute("SELECT player, result FROM survival_ops WHERE op=?", (op,)).fetchone()
    if done:
        if done["player"] != player:
            raise Error("op", 409)
        return json.loads(done["result"])
    handler = ACTIONS.get(name) or (ACTIONS_SERVER.get(name) if server else None)
    if handler is None:
        raise Error("action")
    row = ensure(conn, player)
    t = now()
    detail = handler(conn, row, args or {}, t) or {}
    result = {"ok": True, "action": name, **detail, "state": state(conn, player, t)}
    conn.execute("INSERT INTO survival_ops(op, player, result, time) VALUES (?, ?, ?, ?)",
                 (op, player, json.dumps(result, ensure_ascii=False), t))
    conn.execute("DELETE FROM survival_ops WHERE time<?", (t - 30 * 86400,))
    return result


def _buy(conn, row, args, t):
    cat, entry = args.get("cat", ""), item(args.get("cat", ""), args.get("item", ""))
    if entry is None:
        raise Error("item", 404)
    owned = _json(row["owned"])
    have = set(owned.get(cat, []))
    equipped = _json(row["equipped"])
    if entry["id"] in have:
        equipped[cat] = entry["id"]
        _save(conn, row["player"], equipped=equipped)
        return {"bought": False}
    if entry.get("admin"):
        if not _admin(conn, row["player"]):
            raise Error("admin_only", 403)
        cost = 0
    elif not entry.get("shop", True):
        raise Error("not_for_sale", 409)
    else:
        cost = price(cat, entry)
    _spend(row, cost)
    have.add(entry["id"])
    owned[cat] = sorted(have)
    equipped[cat] = entry["id"]
    bp = _json(row["bp"])
    extra = 0
    if _bp_active(bp, t) and cost:
        bp["spent"] = bp.get("spent", 0) + cost
        extra = _bp_claim(bp)
    _save(conn, row["player"], tokens=row["tokens"] - cost + extra, owned=owned, equipped=equipped, bp=bp)
    _log(conn, row["player"], "buy", -cost, f"{cat}:{entry['id']}")
    return {"bought": True, "price": cost, "battlepass": extra}


def _equip(conn, row, args, t):
    cat = args.get("cat", "")
    if cat not in CATEGORIES:
        raise Error("item", 404)
    equipped = _json(row["equipped"])
    item_id = args.get("item") or ""
    if item_id:
        entry = item(cat, item_id)
        if entry is None or entry["id"] not in _json(row["owned"]).get(cat, []):
            raise Error("not_owned", 409)
        if entry.get("admin") and not _admin(conn, row["player"]):
            raise Error("admin_only", 403)
        equipped[cat] = entry["id"]
    else:
        equipped.pop(cat, None)
    _save(conn, row["player"], equipped=equipped)


def _upgrade(conn, row, args, t):
    kind = args.get("item", "")
    if kind not in UPGRADES:
        raise Error("item", 404)
    cost = UPGRADES[kind]["price"]
    _spend(row, cost)
    fields = {"tokens": row["tokens"] - cost}
    if kind == "lvl10":
        fields["bonus_lvl"] = row["bonus_lvl"] + LVL10_AMOUNT
    else:
        column = "lvl_boost_until" if kind == "lvl_boost" else "tok_boost_until"
        fields[column] = max(row[column], t) + BOOST_HOURS * 3600
    bp = _json(row["bp"])
    if _bp_active(bp, t):
        bp["spent"] = bp.get("spent", 0) + cost
        fields["tokens"] += _bp_claim(bp)
        fields["bp"] = bp
    _save(conn, row["player"], **fields)
    _log(conn, row["player"], "upgrade", -cost, kind)


def _pay(conn, row, args, t):
    target, amount = int(args.get("target") or 0), int(args.get("amount") or 0)
    if amount <= 0:
        raise Error("amount")
    if target == row["player"]:
        raise Error("self")
    if lvl(row) < PAY_MIN_LVL:
        raise Error("pay_lvl", 409)
    today = _today(t)
    sent_today = row["pay_today"] if row["pay_day"] == today else 0
    if sent_today + amount > PAY_DAILY_LIMIT:
        raise Error("pay_limit", 409)
    _spend(row, amount)
    other = _row(conn, target)
    if other is None:
        raise Error("player", 404)
    bp = _json(row["bp"])
    extra = 0
    if _bp_active(bp, t):
        bp["sent"] = bp.get("sent", 0) + amount
        extra = _bp_claim(bp)
    _save(conn, row["player"], tokens=row["tokens"] - amount + extra, pay_day=today,
          pay_today=sent_today + amount, bp=bp)
    _save(conn, target, tokens=other["tokens"] + amount)
    _log(conn, row["player"], "pay", -amount, f"to {target}")
    _log(conn, target, "pay", amount, f"from {row['player']}")
    return {"target": target, "nick": other["nick"], "amount": amount}


def _bp_buy(conn, row, args, t):
    bp = _json(row["bp"])
    if _bp_active(bp, t):
        raise Error("bp_active", 409)
    _spend(row, BP_PRICE)
    _save(conn, row["player"], tokens=row["tokens"] - BP_PRICE, bp={"until": t + BP_DAYS * 86400})
    _log(conn, row["player"], "battlepass", -BP_PRICE)


def _bp_daily(conn, row, args, t):
    bp = _json(row["bp"])
    if not _bp_active(bp, t):
        raise Error("bp_inactive", 409)
    if bp.get("daily") == _today(t):
        raise Error("bp_daily_done", 409)
    bp["daily"] = _today(t)
    bp["days"] = bp.get("days", 0) + 1
    extra = _bp_claim(bp)
    _save(conn, row["player"], tokens=row["tokens"] + BP_DAILY + extra, bp=bp)
    return {"amount": BP_DAILY + extra}


def _bp_final(conn, row, args, t):
    which = args.get("item", "")
    bp = _json(row["bp"])
    if which not in ("lvl", "tokens", "prefix"):
        raise Error("item", 404)
    if set(bp.get("claimed", [])) != {task[0] for task in BP_TASKS}:
        raise Error("bp_tasks", 409)
    final = set(bp.get("final", []))
    if which in final:
        raise Error("bp_final_done", 409)
    final.add(which)
    bp["final"] = sorted(final)
    fields = {"bp": bp}
    if which == "lvl":
        fields["bonus_lvl"] = row["bonus_lvl"] + BP_FINAL_LVL
    elif which == "tokens":
        fields["tokens"] = row["tokens"] + BP_FINAL_TOK
    else:
        owned = _json(row["owned"])
        owned["prefix"] = sorted(set(owned.get("prefix", [])) | {BP_PREFIX})
        fields["owned"] = owned
    _save(conn, row["player"], **fields)


def _promo(conn, row, args, t):
    code = (args.get("code") or "").strip().lower()
    promo = conn.execute("SELECT * FROM survival_promos WHERE code=?", (code,)).fetchone()
    if promo is None:
        raise Error("promo", 404)
    if conn.execute("SELECT 1 FROM survival_promo_uses WHERE code=? AND player=?", (code, row["player"])).fetchone():
        raise Error("promo_used", 409)
    conn.execute("INSERT INTO survival_promo_uses(code, player, time) VALUES (?, ?, ?)", (code, row["player"], t))
    if promo["kind"] == "lvl":
        _save(conn, row["player"], bonus_lvl=row["bonus_lvl"] + promo["amount"])
    else:
        _save(conn, row["player"], tokens=row["tokens"] + promo["amount"])
    _log(conn, row["player"], "promo", promo["amount"], f"{code}:{promo['kind']}")
    return {"kind": promo["kind"], "amount": promo["amount"]}


def _market_sell(conn, row, args, t):
    cat, entry = args.get("cat", ""), item(args.get("cat", ""), args.get("item", ""))
    cost = int(args.get("price") or 0)
    if entry is None or not sellable(cat, entry):
        raise Error("item", 404)
    if not 1 <= cost <= 1_000_000:
        raise Error("price")
    owned = _json(row["owned"])
    if entry["id"] not in owned.get(cat, []):
        raise Error("not_owned", 409)
    expire_market(conn, t)
    if conn.execute("SELECT COUNT(*) FROM survival_market WHERE seller=? AND state='open'", (row["player"],)).fetchone()[0] >= MARKET_MAX:
        raise Error("market_max", 409)
    # the item waits on the market: it leaves the seller until it is sold or taken back
    owned[cat] = [x for x in owned[cat] if x != entry["id"]]
    equipped = _json(row["equipped"])
    if equipped.get(cat) == entry["id"]:
        equipped.pop(cat)
    _save(conn, row["player"], owned=owned, equipped=equipped)
    cur = conn.execute("INSERT INTO survival_market(seller, cat, item, price, created, expires) VALUES (?, ?, ?, ?, ?, ?)",
                       (row["player"], cat, entry["id"], cost, t, t + MARKET_DAYS * 86400))
    return {"listing": cur.lastrowid}


def _give_back(conn, listing, t):
    seller = _row(conn, listing["seller"])
    if seller is not None:
        owned = _json(seller["owned"])
        owned[listing["cat"]] = sorted(set(owned.get(listing["cat"], [])) | {listing["item"]})
        _save(conn, listing["seller"], owned=owned)


def expire_market(conn, t=None):
    t = t or now()
    for listing in conn.execute("SELECT * FROM survival_market WHERE state='open' AND expires<=?", (t,)).fetchall():
        conn.execute("UPDATE survival_market SET state='expired', closed=? WHERE id=?", (t, listing["id"]))
        _give_back(conn, listing, t)


def _market_buy(conn, row, args, t):
    expire_market(conn, t)
    listing = conn.execute("SELECT * FROM survival_market WHERE id=? AND state='open'", (int(args.get("listing") or 0),)).fetchone()
    if listing is None:
        raise Error("listing", 404)
    if listing["seller"] == row["player"]:
        raise Error("self")
    owned = _json(row["owned"])
    if listing["item"] in owned.get(listing["cat"], []):
        raise Error("owned", 409)
    _spend(row, listing["price"])
    owned[listing["cat"]] = sorted(set(owned.get(listing["cat"], [])) | {listing["item"]})
    bp = _json(row["bp"])
    extra = 0
    if _bp_active(bp, t):
        bp["spent"] = bp.get("spent", 0) + listing["price"]
        extra = _bp_claim(bp)
    _save(conn, row["player"], tokens=row["tokens"] - listing["price"] + extra, owned=owned, bp=bp)
    seller = _row(conn, listing["seller"])
    income = listing["price"] - listing["price"] * MARKET_TAX // 100
    if seller is not None:
        _save(conn, listing["seller"], tokens=seller["tokens"] + income)
    conn.execute("UPDATE survival_market SET state='sold', buyer=?, closed=? WHERE id=?", (row["player"], t, listing["id"]))
    _log(conn, row["player"], "market_buy", -listing["price"], f"{listing['cat']}:{listing['item']}")
    _log(conn, listing["seller"], "market_sell", income, f"{listing['cat']}:{listing['item']}")
    return {"listing": listing["id"], "price": listing["price"]}


def _market_withdraw(conn, row, args, t):
    listing = conn.execute("SELECT * FROM survival_market WHERE id=? AND state='open'", (int(args.get("listing") or 0),)).fetchone()
    if listing is None or listing["seller"] != row["player"]:
        raise Error("listing", 404)
    conn.execute("UPDATE survival_market SET state='withdrawn', closed=? WHERE id=?", (t, listing["id"]))
    _give_back(conn, listing, t)
    return {"listing": listing["id"]}


def _crate_state(crate: dict, t: int) -> dict:
    """Seconds left for every crate item the player has, and the invisibility charges left."""
    out = {k: crate[k] - t for k in CRATE if crate.get(k, 0) > t}
    if "invis" in out:
        out["charges"] = crate.get("charges", 0)
        if not out["charges"]:
            out.pop("invis")
    return out


def _crate(conn, row, args, t):
    name = args.get("item", "")
    if name not in CRATE:
        raise Error("item", 404)
    cost = CRATE[name]["price"]
    _spend(row, cost)
    crate = {k: v for k, v in _json(row["crate"]).items() if k == "charges" or v > t}
    crate[name] = max(crate.get(name, 0), t) + CRATE_SECONDS
    if name == "invis":
        crate["charges"] = CRATE_INVIS_CHARGES
    fields = {"tokens": row["tokens"] - cost, "crate": crate}
    bp = _json(row["bp"])
    if _bp_active(bp, t):
        bp["spent"] = bp.get("spent", 0) + cost
        fields["tokens"] += _bp_claim(bp)
        fields["bp"] = bp
    _save(conn, row["player"], **fields)
    _log(conn, row["player"], "crate", -cost, name)


def _crate_use(conn, row, args, t):
    """The game used one invisibility charge."""
    crate = _json(row["crate"])
    if crate.get("invis", 0) <= t or crate.get("charges", 0) <= 0:
        raise Error("crate_empty", 409)
    crate["charges"] -= 1
    _save(conn, row["player"], crate=crate)


def _reward(conn, row, args, t):
    """Tokens a game server hands out for an event in the game (only airdrops so far)."""
    amount = int(args.get("amount") or 0)
    if args.get("kind") != "airdrop" or amount not in AIRDROP_TOKENS:
        raise Error("reward")
    amount *= 2 if row["tok_boost_until"] > t else 1
    _save(conn, row["player"], tokens=row["tokens"] + amount)
    _log(conn, row["player"], "airdrop", amount)
    return {"amount": amount}


# what only a game server may ask for
ACTIONS_SERVER = {"crate_use": _crate_use, "reward": _reward}

ACTIONS = {
    "buy": _buy, "equip": _equip, "upgrade": _upgrade, "pay": _pay,
    "bp_buy": _bp_buy, "bp_daily": _bp_daily, "bp_final": _bp_final, "promo": _promo,
    "market_sell": _market_sell, "market_buy": _market_buy, "market_withdraw": _market_withdraw,
    "crate": _crate,
}


# ---------------------------------------------------------------- lists for the site and the game

def market(conn, viewer: int = 0, t=None) -> dict:
    t = t or now()
    expire_market(conn, t)
    rows = conn.execute("SELECT m.*, s.nick FROM survival_market m LEFT JOIN survival_players s ON s.player=m.seller "
                        "WHERE m.state='open' ORDER BY m.price, m.id LIMIT 200").fetchall()
    def show(r):
        entry = item(r["cat"], r["item"]) or {"ru": r["item"], "en": r["item"]}
        return {"id": r["id"], "seller": r["seller"], "nick": r["nick"] or "", "cat": r["cat"], "item": r["item"],
                "ru": entry["ru"], "en": entry["en"], "price": r["price"], "left": max(0, r["expires"] - t),
                "mine": r["seller"] == viewer}
    return {"listings": [show(r) for r in rows]}


def top(conn, kind: str = "lvl", limit: int = 10) -> list[dict]:
    order = {"lvl": f"(time_sec/{LVL_TIME} + kills/{LVL_KILLS} + bonus_lvl) DESC, kills DESC",
             "kills": "kills DESC", "tokens": "tokens DESC", "time": "time_sec DESC"}.get(kind)
    if order is None:
        raise Error("kind")
    rows = conn.execute(f"SELECT * FROM survival_players ORDER BY {order}, player LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
    return [{"place": i, "id": r["player"], "nick": r["nick"], "lvl": lvl(r), "kills": r["kills"],
             "tokens": r["tokens"], "time": r["time_sec"]} for i, r in enumerate(rows, 1)]


def history(conn, player: int, limit: int = 30) -> list[dict]:
    rows = conn.execute("SELECT * FROM survival_log WHERE player=? ORDER BY id DESC LIMIT ?", (player, limit)).fetchall()
    return [{"time": r["time"], "kind": r["kind"], "amount": r["amount"], "detail": r["detail"]} for r in rows]


def set_live(conn, server: str, data: dict):
    conn.execute("INSERT INTO survival_live(server, data, time) VALUES (?, ?, ?) ON CONFLICT(server) DO UPDATE SET "
                 "data=excluded.data, time=excluded.time", (server, json.dumps(data, ensure_ascii=False), now()))


def live(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM survival_live WHERE time>?", (now() - 90,)).fetchall()
    return [{"server": r["server"], **json.loads(r["data"]), "updated": r["time"]} for r in rows]


# ---------------------------------------------------------------- promo codes (head admins)

def promo_create(conn, code: str, kind: str, amount: int, actor: int) -> dict:
    code = (code or "").strip().lower() or secrets.token_hex(4)
    if kind not in ("tokens", "lvl") or not 1 <= amount <= (1_000_000 if kind == "tokens" else 1000):
        raise Error("promo_bad")
    if not 3 <= len(code) <= 32 or not code.replace("_", "").isalnum():
        raise Error("promo_bad")
    try:
        conn.execute("INSERT INTO survival_promos(code, kind, amount, created, actor) VALUES (?, ?, ?, ?, ?)",
                     (code, kind, amount, now(), actor))
    except sqlite3.IntegrityError:
        raise Error("promo_exists", 409) from None
    return {"code": code, "kind": kind, "amount": amount}


def promo_list(conn) -> list[dict]:
    return [{"code": r["code"], "kind": r["kind"], "amount": r["amount"], "created": r["created"],
             "uses": conn.execute("SELECT COUNT(*) FROM survival_promo_uses WHERE code=?", (r["code"],)).fetchone()[0]}
            for r in conn.execute("SELECT * FROM survival_promos ORDER BY created DESC")]


def promo_delete(conn, code: str):
    conn.execute("DELETE FROM survival_promos WHERE code=?", ((code or "").strip().lower(),))


# ---------------------------------------------------------------- game servers

def server_token(key: str) -> str:
    """What a game server sends in X-CZM-Server: sha256(ticket key "|server"), computed by czm_lvl.amxx."""
    import hashlib
    return hashlib.sha256(f"{key}|server".encode()).hexdigest()


def check_server(token: str | None):
    import hmac
    from . import game_ticket
    if not token or not hmac.compare_digest(token.strip().lower(), server_token(game_ticket._key())):
        raise Error("server", 401)
