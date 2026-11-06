// Server weapon metadata shared by the HUD receiver and menu library.
#pragma once
#include <cstdio>
#include <cstring>
namespace CzmWeapons {
struct Meta {
 bool valid,primary,queued,automatic,purchase;
 int page,pages,selected,remember,price,balance,notice;
};
inline const char *Text(const char *value) {
 if(!value) return "";
 int serial,slots,n=0;
 if(std::sscanf(value,"%d %d%n",&serial,&slots,&n)==2&&value[n]=='\n')return value+n+1;
 return value;
}
inline bool Wire(const char *value) { return std::strncmp(Text(value),"#czmw1\t",7)==0; }
inline Meta Parse(const char *value) {
 Meta m={};char kind[16];int q,a,n=0;
 if(std::sscanf(Text(value),"#czmw1\t%15[^\t]\t%d\t%d\t%d\t%d\t%d\t%d%n",kind,&m.page,&m.pages,&q,&m.selected,&m.remember,&a,&n)!=7)return m;
 if((std::strcmp(kind,"primary")&&std::strcmp(kind,"secondary"))||m.page<0||m.pages<1||m.pages>128||m.page>=m.pages||(q!=0&&q!=1)||(a!=0&&a!=1))return m;
 const char *tail=Text(value)+n;
 int price,balance,notice,end=0;
 if(std::sscanf(tail,"\tbuy\t%d\t%d\t%d%n",&price,&balance,&notice,&end)==3 &&
    (tail[end]=='\n'||tail[end]==0) && price>=0 && balance>=0 && notice>=0 && notice<=4) {
  m.purchase=true;m.price=price;m.balance=balance;m.notice=notice;
 }
 m.valid=true;m.primary=std::strcmp(kind,"primary")==0;m.queued=q!=0;m.automatic=a!=0;return m;
}
inline bool WeaponText(const char *value) {
 const char *s=Text(value);if(Wire(s))return true;
 char title[192];size_t n=0;
 for(;*s&&*s!='\n'&&n+1<sizeof(title);s++) { if(*s=='\\'&&s[1]&&std::strchr("yrwd",s[1])){s++;continue;}title[n++]=*s; }
 title[n]=0;
 return std::strstr(title,"Primary Weapon")||std::strstr(title,"Secondary Weapon")||std::strstr(title,"Главное оружие")||std::strstr(title,"Основное оружие")||std::strstr(title,"Доп. оружие")||std::strstr(title,"Дополнительное оружие");
}
inline bool Classic(const char *value,float style) { return style==0&&WeaponText(value); }
inline bool HideAutomatic(const char *value,float automatic) { Meta m=Parse(value);return m.valid&&m.automatic&&automatic==0; }
}
