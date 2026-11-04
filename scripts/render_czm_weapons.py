#!/usr/bin/env python3
"""Render installed GoldSrc weapon models and textures without copying models into the repo."""
from pathlib import Path
import json,math,os,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server/zm/tools'))
from render_models import Studio,Camera,project,bounds,raster,downsample,write_png
WEAPONS={1:'p228',3:'scout',5:'xm1014',7:'mac10',8:'aug',10:'elite',11:'fiveseven',12:'ump45',13:'sg550',14:'galil',15:'famas',16:'usp',17:'glock18',18:'awp',19:'mp5',20:'m249',21:'m3',22:'m4a1',23:'tmp',24:'g3sg1',26:'deagle',27:'sg552',28:'ak47',30:'p90'}

def render(path,w=640,h=320):
 model=Studio(str(path));tris=model.triangles(model.pose(0 if model.seqs else None))
 points=list({v[0] for _,vs in tris for v in vs})
 mean=[sum(p[k] for p in points)/len(points) for k in range(3)]
 covariance=[[sum((p[i]-mean[i])*(p[j]-mean[j]) for p in points) for j in range(3)] for i in range(3)]
 axes=[[1.0 if i==j else 0.0 for j in range(3)] for i in range(3)]
 # Jacobi diagonalization aligns the model's long axis and profile plane.
 for _ in range(30):
  i,j=max(((0,1),(0,2),(1,2)),key=lambda ij:abs(covariance[ij[0]][ij[1]]))
  if abs(covariance[i][j])<1e-9:break
  angle=.5*math.atan2(2*covariance[i][j],covariance[j][j]-covariance[i][i]);c,s=math.cos(angle),math.sin(angle)
  for k in range(3):
   ai,aj=covariance[k][i],covariance[k][j];covariance[k][i],covariance[k][j]=c*ai-s*aj,s*ai+c*aj
  for k in range(3):
   ai,aj=covariance[i][k],covariance[j][k];covariance[i][k],covariance[j][k]=c*ai-s*aj,s*ai+c*aj
   ai,aj=axes[k][i],axes[k][j];axes[k][i],axes[k][j]=c*ai-s*aj,s*ai+c*aj
 order=sorted(range(3),key=lambda k:covariance[k][k],reverse=True)
 basis=[[axes[k][axis] for k in range(3)] for axis in order]
 def dot(a,b):return sum(x*y for x,y in zip(a,b))
 plane=[(dot(p,basis[0]),dot(p,basis[1])) for p in points]
 low_x,high_x=min(p[0] for p in plane),max(p[0] for p in plane)
 ends=[[p[1] for p in plane if p[0]<low_x+(high_x-low_x)*.18],[p[1] for p in plane if p[0]>high_x-(high_x-low_x)*.18]]
 if max(ends[0])-min(ends[0])<max(ends[1])-min(ends[1]):
  basis[0]=[-x for x in basis[0]];plane=[(-x,y) for x,y in plane];low_x,high_x=-high_x,-low_x
 muzzle=[y for x,y in plane if x>high_x-(high_x-low_x)*.15]
 middle_y=(min(y for x,y in plane)+max(y for x,y in plane))/2
 if sum(muzzle)/len(muzzle)<middle_y:basis[1]=[-x for x in basis[1]]
 # Art direction for asymmetric stocks/magazines, which can dominate PCA.
 name=path.stem.removeprefix('w_')
 if name in {'p228','scout','mac10','aug','elite','sg550','famas','usp','m3'}:basis[1]=[-x for x in basis[1]]
 if name in {'ump45','p90'}:basis[0]=[-x for x in basis[0]]
 a,b=basis[:2];basis[2]=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
 def rotate(p):
  x,y,z=(dot(p,b) for b in basis)
  if name=='mac10':
   a=math.radians(35);x,y=math.cos(a)*x-math.sin(a)*y,math.sin(a)*x+math.cos(a)*y
  return x,y,z
 tris=[(tex,[(rotate(p),rotate(n),u,v) for p,n,u,v in vs]) for tex,vs in tris]
 pts=[v[0] for _,vs in tris for v in vs]
 low=[min(p[k] for p in pts) for k in range(3)];high=[max(p[k] for p in pts) for k in range(3)]
 center=[(a+b)/2 for a,b in zip(low,high)];back=(0,-.22,1);distance=max(b-a for a,b in zip(low,high))*8
 camera=Camera([center[k]+back[k]*distance for k in range(3)],back,focal=8);projected=project(model,tris,camera)
 x0,y0,x1,y1=bounds(projected);ss=2;W,H=w*ss,h*ss
 scale=min(W*.92/max(.001,x1-x0),H*.88/max(.001,y1-y0))
 rgb,alpha=raster(model,projected,W,H,scale,W/2-(x0+x1)*scale/2,H/2+(y0+y1)*scale/2)
 return downsample(rgb,alpha,W,H,ss),w,h

def main(models,output):
 os.nice(15);output.mkdir(parents=True,exist_ok=True)
 for weapon,name in WEAPONS.items():
  px,w,h=render(models/('w_'+name+'.mdl'));write_png(str(output/('weapon_%d.png'%weapon)),px,w,h)
  print(json.dumps({'weapon':weapon,'model':name}),flush=True)
if __name__=='__main__':main(*map(Path,sys.argv[1:]))
