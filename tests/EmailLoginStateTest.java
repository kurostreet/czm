package ru.kurostreet.counterzombiemobile;

public final class EmailLoginStateTest {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        long sent = 1700000000000L;
        EmailLoginState original = EmailLoginState.requested("player@example.com", sent);
        // Only these three metadata fields survive a destroyed Activity/process.
        EmailLoginState restored = EmailLoginState.restore(original.email, original.expiresAt, original.resendAt, sent + 25000);
        check(restored != null && restored.email.equals(original.email), "resume the same address");
        check(restored.expiresAt == sent + 600000, "resume must not renew the code's lifetime");
        check(restored.resendDelay(sent + 25000) == 35000, "keep the resend cooldown across restarts");
        check(restored.resendDelay(sent + 65000) == 0, "allow an explicit resend after the cooldown");
        check(EmailLoginState.restore(original.email, original.expiresAt, original.resendAt, sent + 600000) == null, "drop expired requests");
        check(EmailLoginState.restore(original.email, original.expiresAt, original.resendAt, sent - 1) == null, "drop requests after clock rollback");
        check(EmailLoginState.restore("", original.expiresAt, original.resendAt, sent) == null, "do not restore an empty request");
        check(EmailLoginState.restore("player\n@example.com", original.expiresAt, original.resendAt, sent) == null, "reject control characters");
        check(EmailLoginState.restore(original.email, original.expiresAt, original.resendAt + 1, sent) == null, "reject inconsistent metadata");
        EmailLoginState resent = EmailLoginState.requested(original.email, sent + 65000);
        check(resent.resendDelay(sent + 65000) == 60000 && resent.expiresAt == sent + 665000, "a new request renews both deadlines");
        System.out.println("EMAIL_LOGIN_RESTORE_OK");
    }
}
