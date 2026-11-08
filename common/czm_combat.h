/* Runtime combat presentation. Server class IDs are 1..10; zero hides zombie abilities. */
#pragma once
#include <cstdio>
#include <cmath>
#include <algorithm>
namespace CzmCombat {
enum { G, R, E, BUTTONS };
enum { FORT_HUMAN_CT = 4 };
struct State {
    int klass, flags, primary, secondary, charge, active;
    State():klass(0),flags(0),primary(0),secondary(0),charge(0),active(0){}
};
inline bool Parse(const char *text, State &s) {
    State value; char tail;
    if (!text || std::sscanf(text,"%d %d %d %d %d %d %c",&value.klass,&value.flags,
        &value.primary,&value.secondary,&value.charge,&value.active,&tail)!=6 || value.klass<0 || value.klass>10
        || value.flags<0 || value.flags>7 || ((value.flags&FORT_HUMAN_CT) && (value.klass!=0 || value.flags!=FORT_HUMAN_CT))
        || value.primary<0 || value.primary>600 || value.secondary<0 || value.secondary>600
        || value.charge<0 || value.charge>100 || value.active<0 || value.active>100) {s=State();return false;}
    s=value;return true;
}
// This bit is reported by Zombie Plague; a Counter-Strike team alone is not a role.
inline int FortificationMask(const State &s) {
    return s.klass==0 && (s.flags&FORT_HUMAN_CT)?3:0;
}
inline int Mask(int klass) {
    static const int masks[11]={0,1,2,0,1,1,1,5,4,1,3};
    return klass>=0&&klass<=10?masks[klass]:0;
}
inline int Cooldown(const State &s,int button) {
    if (!(Mask(s.klass)&(1<<button))) return 0;
    return button==G&&s.klass==10?s.secondary:button==E&&s.klass==7?0:s.primary;
}
inline const char *Name(const State &s,int button,bool ru) {
    static const char *const names[11][2]={{"",""},{"Ускорение","Sprint"},{"Рывок","Leap"},{"Прыжок","Jump"},
        {"Огонь","Fire"},{"Лёд","Ice"},{"Яд","Poison"},{"Сфера","Orb"},{"Чёрная дыра","Black hole"},
        {"Телепорт","Teleport"},{"Полёт","Fly"}};
    if (s.klass<1||s.klass>10) return "";
    if (s.klass==7) return button==E?(s.flags&1?(ru?"Лёд":"Ice"):(ru?"Огонь":"Fire")):
        (s.flags&1?(ru?"Ледяная сфера":"Ice orb"):(ru?"Огненная сфера":"Fire orb"));
    if (s.klass==10&&button==G) return ru?"Невидимость":"Invisibility";
    return names[s.klass][ru?0:1];
}
// Pixel geometry shared by the drawing and hit testing of the touch-only digit panel.
struct Keypad {
    int x,y,w,h,key,gap,header;
    Keypad(int width,int height) {
        key=(int)std::fmin(height*.105f,width*.17f);gap=(int)std::fmax(5.f,height*.012f);
        header=(int)(height*.075f);w=3*key+4*gap;h=header+4*key+5*gap;x=(width-w)/2;y=(height-h)/2;
    }
    void Cell(int digit,int &cx,int &cy) const {
        int index=digit?digit-1:10;cx=x+gap+(index%3)*(key+gap);cy=y+header+gap+(index/3)*(key+gap);
    }
    int Hit(int px,int py) const {
        if(px>=x+w-header&&px<x+w&&py>=y&&py<y+header)return 10;
        for(int digit=0;digit<=9;digit++){int cx,cy;Cell(digit,cx,cy);if(px>=cx&&px<cx+key&&py>=cy&&py<cy+key)return digit;}
        return -1;
    }
};
}
