/* Pending email sign-in metadata; codes and credentials are never saved here. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

final class EmailLoginState {
    static final long LIFETIME_MS = 10 * 60 * 1000, RESEND_MS = 60 * 1000;
    final String email;
    final long expiresAt, resendAt;

    private EmailLoginState(String email, long expiresAt, long resendAt) {
        this.email = email; this.expiresAt = expiresAt; this.resendAt = resendAt;
    }

    static EmailLoginState requested(String email, long now) {
        return new EmailLoginState(email, now + LIFETIME_MS, now + RESEND_MS);
    }

    static EmailLoginState restore(String email, long expiresAt, long resendAt, long now) {
        if (email == null || email.isEmpty() || email.length() > 254 || !email.equals(email.trim())
                || email.indexOf('@') <= 0 || expiresAt <= now || expiresAt > now + LIFETIME_MS
                || resendAt != expiresAt - LIFETIME_MS + RESEND_MS) return null;
        for (int i = 0; i < email.length(); ++i) if (Character.isISOControl(email.charAt(i))) return null;
        return new EmailLoginState(email, expiresAt, resendAt);
    }

    long resendDelay(long now) { return Math.max(0, Math.min(RESEND_MS, resendAt - now)); }
}
