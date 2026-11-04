#ifndef CZM_AIM_H
#define CZM_AIM_H
namespace CzmAim {
struct Target {
 int index, health, maximum;
 float received;
 bool Live(float now) const { return index>=1&&index<=32&&health>0&&maximum>0&&now>=received&&now-received<1.1f; }
};
inline float Fraction(int health,int maximum) { if(health<=0||maximum<=0)return 0;return health>=maximum?1.0f:(float)health/maximum; }
inline void Color(float fraction,int &r,int &g,int &b) {
 fraction=fraction<0?0:(fraction>1?1:fraction);
 r=fraction>.5f?(int)(255*(1-fraction)*2):255;g=fraction>.5f?220:(int)(440*fraction);b=65;
}
}
#endif
