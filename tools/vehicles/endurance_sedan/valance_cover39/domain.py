"""Current-input cover construction: domain. Source provenance is in the private port manifest."""

import math

def sub(a,b):return tuple(x-y for x,y in zip(a,b))

def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])

def dot(a,b):return sum(x*y for x,y in zip(a,b))

def validate(row):
 if type(row) is not dict or not all(k in row for k in ('vertices','triangles')):raise ValueError('Complete current native mesh required')
 if not row['vertices'] or not row['triangles']:raise ValueError('Empty mesh')
 for p in row['vertices']:
  if len(p)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in p):raise ValueError('Finite native points required')
 seen=set()
 for t in row['triangles']:
  if len(t)!=3 or len(set(t))!=3 or any(type(v) is not int or v<0 or v>=len(row['vertices']) for v in t):raise ValueError('Invalid native triangle')
  key=tuple(sorted(t))
  if key in seen:raise ValueError('Duplicate native face')
  seen.add(key)
  a,b,c=[row['vertices'][v] for v in t]
  if dot(cross(sub(b,a),sub(c,a)),cross(sub(b,a),sub(c,a)))==0:raise ValueError('Degenerate native face')

def projected_carrier(reference):
 validate(reference);result=[]
 for i,ids in enumerate(reference['triangles']):
  a,b,c=[reference['vertices'][v] for v in ids];n=cross(sub(b,a),sub(c,a))
  if n[1]>=0:continue
  # Outward rear surface is the lowest Y on the complete actual finite patch.
  # No radial/analytic reconstruction or historical face labels are accepted.
  result.append(dict(index=i,points=[a,b,c],xz=[[p[0],p[2]] for p in (a,b,c)],
   y_coefficients=[-n[0]/n[1],-n[2]/n[1],dot(n,a)/n[1]]))
 if not result:raise ValueError('Missing rear-facing native carrier')
 return result

def rear_y(x,z,patch):
 hits=[]
 for r in patch:
  a,b,c=r['xz'];ab=(b[0]-a[0],b[1]-a[1]);ac=(c[0]-a[0],c[1]-a[1]);ap=(x-a[0],z-a[1])
  det=ab[0]*ac[1]-ab[1]*ac[0]
  u=(ap[0]*ac[1]-ap[1]*ac[0])/det;v=(ab[0]*ap[1]-ab[1]*ap[0])/det
  if min(u,v,1-u-v)>=-1e-12:
   aa,bb,cc=r['y_coefficients'];hits.append((aa*x+bb*z+cc,r['index']))
 if not hits:raise ValueError('Native rear carrier projection does not cover point')
 return min(hits)
