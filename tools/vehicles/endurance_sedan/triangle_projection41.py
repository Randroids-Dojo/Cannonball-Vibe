"""Double-precision plane/edge distance with exact projected containment."""
from fractions import Fraction
import math
def sub(a,b):return tuple(float(x)-float(y) for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def unit(n):
 length=math.hypot(*n)
 if length==0:raise ValueError('Degenerate original triangle')
 return tuple(x/length for x in n)
def closest(point,triangle):
 a,b,c=triangle;n=unit(cross(sub(b,a),sub(c,a)))
 d=dot(sub(point,a),n);hit=tuple(float(point[i])-n[i]*d for i in range(3))
 axis=max(range(3),key=lambda i:abs(n[i]));dims=[i for i in range(3) if i!=axis]
 exact=lambda p:tuple(Fraction(float(p[i])) for i in dims)
 x,y,z,p=[exact(v) for v in (*triangle,hit)]
 turn=lambda a,b,c:(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
 orientation=turn(x,y,z)
 if not orientation:raise ValueError('Degenerate projected source triangle')
 sign=1 if orientation>0 else -1
 if all(sign*turn(u,v,p)>=0 for u,v in ((x,y),(y,z),(z,x))):return hit
 candidates=[]
 for a,b in zip(triangle,triangle[1:]+triangle[:1]):
  delta=sub(b,a);t=max(0.,min(1.,dot(sub(point,a),delta)/dot(delta,delta)))
  hit=tuple(float(a[i])+t*delta[i] for i in range(3));candidates.append((math.dist(point,hit),hit))
 return min(candidates,key=lambda item:item[0])[1]
