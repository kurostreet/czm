package ru.kurostreet.counterzombiemobile;

import java.net.URI;

/** Data only: accepts a CZM invitation, never launches a supplied URI or Intent. */
final class DevelopmentInvite {
    static String parse(String value) {
        String text = value == null ? "" : value.trim();
        if (text.matches("[A-Za-z0-9_-]{32}")) return text;
        try {
            URI uri = new URI(text);
            String prefix = "/api/v1/development/invite/";
            if (!"https".equals(uri.getScheme()) || !"counter-zombie.ru".equals(uri.getHost())
                    || uri.getPort() != -1 || uri.getUserInfo() != null || uri.getQuery() != null
                    || uri.getFragment() != null || !uri.getPath().startsWith(prefix)) return "";
            String code = uri.getPath().substring(prefix.length());
            return code.matches("[A-Za-z0-9_-]{32}") ? code : "";
        } catch (Exception e) { return ""; }
    }
    private DevelopmentInvite() {}
}
