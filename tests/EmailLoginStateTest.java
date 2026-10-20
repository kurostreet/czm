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
        PasswordChangeState change=PasswordChangeState.requested(7,original.email,sent);
        PasswordChangeState resume=PasswordChangeState.restore(change.owner,change.mail.email,change.mail.expiresAt,change.mail.resendAt,sent+25000);
        check(resume!=null&&resume.belongsTo(7,original.email),"restore the password change for its verified account");
        check(!resume.belongsTo(8,original.email)&&!resume.belongsTo(7,"changed@example.com"),"never restore after account or email change");
        check(resume.mail.resendDelay(sent+25000)==35000,"password resend delay survives recreation");
        check(PasswordChangeState.restore(0,original.email,change.mail.expiresAt,change.mail.resendAt,sent)==null,"reject a guest password change");
        check(PasswordChangeState.restore(7,original.email,change.mail.expiresAt,change.mail.resendAt,sent+600000)==null,"expire a pending password change");
        System.out.println("EMAIL_LOGIN_RESTORE_OK");
    }
}
