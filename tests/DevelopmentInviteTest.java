package ru.kurostreet.counterzombiemobile;
public final class DevelopmentInviteTest {
    public static void main(String[] args) {
        String code="abcdefghijklmnopqrstuvwx12345678";
        String url="https://counter-zombie.ru/api/v1/development/invite/"+code;
        if(!DevelopmentInvite.parse(code).equals(code)||!DevelopmentInvite.parse(" "+url+" ").equals(code))throw new AssertionError("valid invite");
        String[] bad={null,"",code+"x","http://counter-zombie.ru/api/v1/development/invite/"+code,
            url+"?x=1",url+"#x",url+"/",url.replace("counter-zombie.ru","counter-zombie.ru.evil.test"),
            url.replace("counter-zombie.ru","user@counter-zombie.ru"),url.replace("counter-zombie.ru","counter-zombie.ru:123"),
            "intent://activate/#Intent;end",url.replace(code,"..%2F"+code)};
        for(String value:bad)if(!DevelopmentInvite.parse(value).isEmpty())throw new AssertionError("unsafe invite accepted");
        System.out.println("DevelopmentInviteTest OK");
    }
}
