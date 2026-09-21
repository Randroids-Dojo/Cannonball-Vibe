"""Actual-input rear-channel construction primitive."""
import math, itertools
from collections import Counter, defaultdict
import numpy as np
from .vectors import sub, dot, cross, f32

def plane_miter(p,normals,anchors,depth=.00125,fixed_y=None):
 p=np.array(p);A=np.array(normals);b=np.array([np.dot(n,np.array(a)-p)-depth for n,a in zip(A,anchors)]);target=-depth*np.mean(A,axis=0);candidates=[]
 if fixed_y is not None:
  delta_y=fixed_y-p[1];B=A[:,[0,2]];rhs=b-A[:,1]*delta_y;goal=target[[0,2]];valid=[]
  if max(B@goal-rhs)<=1e-10:valid.append((0.,goal,()))
  for count in range(1,min(2,len(B))+1):
   for active in itertools.combinations(range(len(B)),count):
    a=B[list(active)];gram=a@a.T
    if abs(np.linalg.det(gram))<1e-16:continue
    q=goal-a.T@np.linalg.solve(gram,a@goal-rhs[list(active)])
    if max(B@q-rhs)<=1e-10:valid.append((float(np.dot(q-goal,q-goal)),q,active))
  if not valid:raise ValueError('No positive-stock common planar end section')
  _,xz,active=min(valid,key=lambda x:x[0]);delta=np.array([xz[0],delta_y,xz[1]])
  q=f32(p+delta);q[1]=fixed_y;stock=-A@(np.array(q)-p)+b+depth
  return q,{'active':active,'diagonal_m':float(np.linalg.norm(delta)),'minimum_incident_stock_m':float(min(stock)),'maximum_incident_stock_m':float(max(stock)),'common_end_y_m':fixed_y}

 for count in range(1,min(3,len(A))+1):
  for active in itertools.combinations(range(len(A)),count):
   a=A[list(active)];gram=a@a.T
   if abs(np.linalg.det(gram))<1e-16:continue
   q=target-a.T@np.linalg.solve(gram,a@target-b[list(active)])
   if max(A@q-b)<=1e-10:candidates.append((float(np.dot(q-target,q-target)),q,active))
 if not candidates:raise ValueError('No finite actual plane miter')
 _,delta,active=min(candidates,key=lambda x:x[0]);q=f32(p+delta);stock=-A@(np.array(q)-p)+b+depth
 return q,{'active':active,'diagonal_m':float(np.linalg.norm(delta)),'minimum_incident_stock_m':float(min(stock)),'maximum_incident_stock_m':float(max(stock))}

def closest_double(p,a,b,c):
    ab=sub(b,a);ac=sub(c,a);ap=sub(p,a);d1=dot(ab,ap);d2=dot(ac,ap)
    if d1<=0 and d2<=0:return a
    bp=sub(p,b);d3=dot(ab,bp);d4=dot(ac,bp)
    if d3>=0 and d4<=d3:return b
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:
        t=d1/(d1-d3);return [a[k]+t*ab[k]for k in range(3)]
    cp=sub(p,c);d5=dot(ab,cp);d6=dot(ac,cp)
    if d6>=0 and d5<=d6:return c
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:
        t=d2/(d2-d6);return [a[k]+t*ac[k]for k in range(3)]
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:
        t=(d4-d3)/(d4-d3+d5-d6);return [b[k]+t*(c[k]-b[k])for k in range(3)]
    den=va+vb+vc
    if den<=0:raise ValueError('Degenerate double native receiver')
    u=vb/den;v=vc/den;return [a[k]+u*ab[k]+v*ac[k]for k in range(3)]
