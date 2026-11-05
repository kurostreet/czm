#pragma once
#include <cstring>
#include <cstddef>

namespace CzmServerView {
enum Kind { Cards, Text, Form, Friends, Account };
inline bool ProfileCodeCommand(const char *command) {
    return command && !std::strcmp(command, "czm_profile_migrate");
}
inline bool ProfileCode(const char *text) {
    return std::strlen(text) == 32 && std::strspn(text, "0123456789abcdefABCDEF") == 32;
}
inline bool FormCommand(const char *command) {
    static const char *allowed[] = {"czm_admin_msg", "czm_say_all", "czm_poll", "czm_news", "czm_promo"};
    for (const char *value : allowed) if (command && !std::strcmp(command, value)) return true;
    return false;
}
inline Kind ParseKind(const char *kind, const char *command) {
    if (!std::strcmp(kind, "form") && (FormCommand(command) || ProfileCodeCommand(command))) return Form;
    if (!std::strcmp(kind, "friends") && !std::strcmp(command, "@friends")) return Friends;
    if (!std::strcmp(kind, "account") && !std::strcmp(command, "@account")) return Account;
    return Text;
}
inline int Characters(const char *text) {
    int count = 0;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) if ((*p & 0xc0) != 0x80) ++count;
    return count;
}
inline void Backspace(char *text) {
    std::size_t size = std::strlen(text);
    if (!size) return;
    --size;
    while (size && ((unsigned char)text[size] & 0xc0) == 0x80) --size;
    text[size] = 0;
}
// Console arguments use one quoted string. Text cannot terminate it or add a command.
inline bool Append(char *text, std::size_t capacity, int byte) {
    if (byte < 32 || byte > 255 || byte == 127 || byte == '"' || byte == '\\' || byte == ';' || byte == '^') return false;
    const std::size_t size = std::strlen(text);
    if ((byte & 0xc0) == 0x80) {
        std::size_t lead = size;
        while (lead && ((unsigned char)text[lead - 1] & 0xc0) == 0x80) --lead;
        if (!lead) return false;
        --lead;
        const unsigned char first = (unsigned char)text[lead];
        const std::size_t expected = first >= 0xf0 ? 4 : first >= 0xe0 ? 3 : first >= 0xc2 ? 2 : 1;
        if (size - lead >= expected) return false;
    } else if (byte >= 128 && (byte < 0xc2 || byte > 0xf4)) return false;
    if (size + 5 >= capacity || (((byte & 0xc0) != 0x80) && Characters(text) >= 180)) return false;
    text[size] = (char)byte; text[size + 1] = 0;
    return true;
}
}
