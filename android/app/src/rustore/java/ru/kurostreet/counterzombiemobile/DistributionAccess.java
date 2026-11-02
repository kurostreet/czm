package ru.kurostreet.counterzombiemobile;

/** RuStore is a supported distribution; it has no external test activation. */
final class DistributionAccess {
    static boolean changed(){return false;}
    static void show(String key,String nick,boolean ru){}
    static void help(String key,String nick,boolean ru){}
    private DistributionAccess(){}
}
