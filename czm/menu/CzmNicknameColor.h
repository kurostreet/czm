/* Shared nickname color contract. Empty or malformed values keep the caller's role/default color. */
#pragma once
#include <math.h>
#include <stdio.h>

namespace CzmNicknameColor {
inline int HexDigit(char c) {
    if(c>='0'&&c<='9')return c-'0';
    if(c>='a'&&c<='f')return c-'a'+10;
    if(c>='A'&&c<='F')return c-'A'+10;
    return -1;
}
inline bool Valid(const char *hex) {
    if(!hex||hex[0]!='#')return false;
    for(int i=1;i<=6;i++)if(!hex[i]||HexDigit(hex[i])<0)return false;
    return hex[7]==0;
}
inline unsigned Parse(const char *hex,unsigned fallback) {
    if(!Valid(hex))return fallback;
    const unsigned r=(HexDigit(hex[1])<<4)|HexDigit(hex[2]);
    const unsigned g=(HexDigit(hex[3])<<4)|HexDigit(hex[4]);
    const unsigned b=(HexDigit(hex[5])<<4)|HexDigit(hex[6]);
    return r|(g<<8)|(b<<16)|0xff000000u;
}
inline void Hex(unsigned color,char out[8]) {
    snprintf(out,8,"#%02X%02X%02X",color&255u,(color>>8)&255u,(color>>16)&255u);
}
inline float Clamp(float v,float lo=0.0f,float hi=1.0f) { return v<lo?lo:v>hi?hi:v; }
inline unsigned Hsv(float hue,float saturation,float value) {
    hue=hue-floorf(hue);saturation=Clamp(saturation);value=Clamp(value);
    const float scaled=hue*6.0f;const int sector=(int)scaled;
    const float f=scaled-sector,p=value*(1-saturation),q=value*(1-saturation*f),t=value*(1-saturation*(1-f));
    float r=0,g=0,b=0;
    switch(sector%6){
    case 0:r=value;g=t;b=p;break;case 1:r=q;g=value;b=p;break;
    case 2:r=p;g=value;b=t;break;case 3:r=p;g=q;b=value;break;
    case 4:r=t;g=p;b=value;break;default:r=value;g=p;b=q;break;
    }
    return (unsigned)(r*255+.5f)|((unsigned)(g*255+.5f)<<8)|((unsigned)(b*255+.5f)<<16)|0xff000000u;
}
inline void ToHsv(unsigned color,float &hue,float &saturation,float &value) {
    const float r=(color&255u)/255.0f,g=((color>>8)&255u)/255.0f,b=((color>>16)&255u)/255.0f;
    const float high=r>g?(r>b?r:b):(g>b?g:b),low=r<g?(r<b?r:b):(g<b?g:b),delta=high-low;
    value=high;saturation=high>0?delta/high:0;hue=0;
    if(delta>0){
        if(high==r)hue=(g-b)/delta;else if(high==g)hue=2+(b-r)/delta;else hue=4+(r-g)/delta;
        hue/=6;if(hue<0)hue+=1;
    }
}
}
