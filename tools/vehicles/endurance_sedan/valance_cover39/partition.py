"""Current-input cover construction: partition. Source provenance is in the private port manifest."""

import copy

import math

import struct

from . import domain as domain07

def exact_patches(reference,exact):
 result=[]
 for index,t in enumerate(reference['triangles']):
  vs=[exact.vector(reference['vertices'][v]) for v in t];a,b,c=vs;n=exact.cross(exact.sub(b,a),exact.sub(c,a))
  if n[1]>=0:continue
  coeff=(-n[0]/n[1],-n[2]/n[1],exact.dot(n,a)/n[1]);planes=[]
  mid=tuple(sum(p[i] for p in vs)/3 for i in range(3))
  for p,q in zip(vs,vs[1:]+vs[:1]):
   e=exact.sub(q,p);axis=(e[2],exact.F(0),-e[0]);d=exact.dot(axis,p)
   if exact.dot(axis,mid)<d:axis=tuple(-v for v in axis);d=-d
   if exact.dot(axis,mid)<=d:raise ValueError('Degenerate projected carrier')
   planes.append((axis,d))
  result.append(dict(index=index,points=vs,coeff=coeff,planes=planes,low=(min(p[0] for p in vs),min(p[2] for p in vs)),high=(max(p[0] for p in vs),max(p[2] for p in vs))))
 return result

def partition(triangle,patches,exact):
 tri=[exact.vector(p) for p in triangle];remaining=[(tri,None)]
 low=(min(p[0] for p in tri),min(p[2] for p in tri));high=(max(p[0] for p in tri),max(p[2] for p in tri))
 for r in patches:
  if any(low[i]>r['high'][i] or high[i]<r['low'][i] for i in range(2)):continue
  todo=[]
  for poly,owner in remaining:
   hit,out=exact.partition(poly,r['planes']);todo.extend((p,owner) for p in out)
   if not hit:continue
   if owner is None:todo.append((hit,r));continue
   a,b,c=owner['coeff'];aa,bb,cc=r['coeff']
   # Keep the actual lowest-Y face wherever projected native faces overlap.
   inside,outside=exact.partition(hit,[((a-aa,exact.F(0),b-bb),cc-c)])
   if inside:todo.append((inside,r))
   todo.extend((p,owner) for p in outside)
  remaining=todo
  if len(remaining)>10000:raise ValueError('Finite carrier partition unresolved')
 return remaining
