/* Only the owner and delivery metadata survive recreation; never a password or code. GPL-3.0-or-later. */
package ru.kurostreet.counterzombiemobile;

final class PasswordChangeState {
    final int owner;
    final EmailLoginState mail;
    private PasswordChangeState(int owner, EmailLoginState mail) { this.owner=owner; this.mail=mail; }
    static PasswordChangeState requested(int owner, String email, long now) {
        if (owner <= 0) throw new IllegalArgumentException();
        return new PasswordChangeState(owner, EmailLoginState.requested(email, now));
    }
    static PasswordChangeState restore(int owner, String email, long expires, long resend, long now) {
        EmailLoginState mail=EmailLoginState.restore(email, expires, resend, now);
        return owner > 0 && mail != null ? new PasswordChangeState(owner, mail) : null;
    }
    boolean belongsTo(int player, String email) { return owner==player && mail.email.equals(email); }
}
