/* The next-map vote of our servers (czm_mapvote.amxx 1.1.0), shared by the HUD and the menu.
 *
 * The server sends CzmVote, reliable, to clients that report czm_mapvote_ui 1:
 *   1 state  flags, count, own+1, seconds, voters, players, long session
 *   2 rows   (number, votes, map) repeated, most votes first
 *   3 closed long session
 *   4 time   seconds, voters, players, long session
 * A map keeps its number for the whole vote, so the order can change under a finger
 * without a tap voting for another map ("czm_vote_map <number>").
 *
 * The HUD keeps the ballot in the czm_vote cvar as text; the menu draws the window from it:
 *   serial session flags opens seconds own voters players count
 *   number votes map        (count lines)
 * An empty cvar means no vote. */
#pragma once
#include <cstdio>
#include <cstring>

namespace CzmVote {
enum { MAX_ROWS = 64, AUTO = 1, OPEN = 2 };

struct Row { int number, votes; char map[32]; };

struct Ballot {
    int serial, session, flags, opens, seconds, own, voters, players, count;
    Row rows[MAX_ROWS];
    Ballot() { std::memset(this, 0, sizeof(*this)); own = -1; }
};

// Map names come from the server: only plain file-name characters are shown or looked up.
inline bool MapName(const char *src, char *out, size_t size) {
    size_t n = 0;
    if (!src || !*src || !size) return false;
    for (; src[n]; n++) {
        const char c = src[n];
        if (n + 1 >= size || !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
            || c == '_' || c == '-' || c == '.')) return false;
        out[n] = c;
    }
    out[n] = 0;
    return true;
}

inline int Format(const Ballot &b, char *out, size_t size) {
    int n = std::snprintf(out, size, "%d %d %d %d %d %d %d %d %d\n", b.serial, b.session, b.flags, b.opens,
        b.seconds, b.own, b.voters, b.players, b.count);
    for (int i = 0; i < b.count && n > 0 && (size_t)n < size; i++)
        n += std::snprintf(out + n, size - n, "%d %d %s\n", b.rows[i].number, b.rows[i].votes, b.rows[i].map);
    return n;
}

inline bool Parse(const char *text, Ballot &b) {
    Ballot v;
    int used = 0;
    if (!text || std::sscanf(text, "%d %d %d %d %d %d %d %d %d%n", &v.serial, &v.session, &v.flags, &v.opens,
            &v.seconds, &v.own, &v.voters, &v.players, &v.count, &used) != 9
        || v.count < 1 || v.count > MAX_ROWS || v.seconds < 0 || v.seconds > 255 || v.own < -1 || v.own > 255
        || v.voters < 0 || v.players < 0)
        return false;
    const char *p = text + used;
    for (int i = 0; i < v.count; i++) {
        char map[64];
        int n = 0;
        if (*p != '\n' || std::sscanf(p + 1, "%d %d %63s%n", &v.rows[i].number, &v.rows[i].votes, map, &n) != 3
            || v.rows[i].number < 0 || v.rows[i].number > 255 || v.rows[i].votes < 0
            || !MapName(map, v.rows[i].map, sizeof(v.rows[i].map)))
            return false;
        p += 1 + n;
    }
    b = v;
    return true;
}

// The row of map number `number`, -1 when it is not on the ballot.
inline int Find(const Ballot &b, int number) {
    for (int i = 0; i < b.count; i++)
        if (b.rows[i].number == number) return i;
    return -1;
}

// When the window opens by itself: once for a new vote the player's popup setting allows,
// and each time the player asks for it (/votemap). A closed window stays closed otherwise.
struct Opening {
    int session, opens;
    bool seen;
    Opening() : session(0), opens(0), seen(false) {}
    bool Next(const Ballot &b) {
        if (!seen || b.session != session) {
            seen = true; session = b.session; opens = b.opens;
            return (b.flags & AUTO) != 0;
        }
        if (b.opens != opens) { opens = b.opens; return true; }
        return false;
    }
};

// "0:42"
inline void Clock(int seconds, char *out, size_t size) {
    if (seconds < 0) seconds = 0;
    std::snprintf(out, size, "%d:%02d", seconds / 60, seconds % 60);
}
}
