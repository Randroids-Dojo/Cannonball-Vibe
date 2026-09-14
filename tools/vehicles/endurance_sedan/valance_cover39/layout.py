"""Current-input cover construction: layout. Source provenance is in the private port manifest."""

from collections import defaultdict, Counter

from . import partition as form09

def cross2(a,b):return a[0]*b[1]-a[1]*b[0]

def sub2(a,b):return (a[0]-b[0],a[1]-b[1])

def boundary(polygons):
 # Subdivide every directed planar edge at all actual same-patch endpoints.
 # No geometric tolerance or small positive-area removal is used.
 points=set(p for poly in polygons for p in poly);edges=Counter()
 for poly in polygons:
  for a,b in zip(poly,poly[1:]+poly[:1]):
   e=sub2(b,a)
   if e==(0,0):continue
   axis=0 if e[0] else 1
   line=[p for p in points if min(a[0],b[0])<=p[0]<=max(a[0],b[0]) and min(a[1],b[1])<=p[1]<=max(a[1],b[1]) and cross2(sub2(p,a),e)==0]
   line.sort(key=lambda p:(p[axis]-a[axis])/e[axis])
   for p,q in zip(line,line[1:]):
    if edges[(q,p)]:edges[(q,p)]-=1
    else:edges[(p,q)]+=1
 outgoing=defaultdict(list)
 for (a,b),count in edges.items():
  if count:
   if count!=1:raise ValueError('Overlapping reference layout face')
   outgoing[a].append(b)
 if any(len(v)!=1 for v in outgoing.values()):raise ValueError('Ambiguous patch boundary degree')
 result=[]
 while outgoing:
  first=min(outgoing);poly=[first];v=outgoing.pop(first)[0]
  while v!=first:
   poly.append(v)
   if v not in outgoing:raise ValueError('Open finite patch boundary')
   v=outgoing.pop(v)[0]
  if len(poly)<3 or sum(cross2(a,b) for a,b in zip(poly,poly[1:]+poly[:1]))==0:raise ValueError('Degenerate union patch')
  result.append(poly)
 return result

def layout(valance,reference,front,exact):
 patches=form09.exact_patches(reference,exact);groups=defaultdict(list);counts=Counter()
 for i in sorted(front):
  t=[valance['vertices'][v] for v in valance['triangles'][i]]
  for poly,owner in form09.partition(t,patches,exact):
   if owner is None:raise ValueError('Missing finite front carrier')
   points=[(p[0],p[2]) for p in poly]
   if sum(cross2(a,b) for a,b in zip(points,points[1:]+points[:1]))==0:raise ValueError('Degenerate front projection')
   groups[owner['index']].append(points);counts[owner['index']]+=1
 result=[]
 for owner,polys in sorted(groups.items()):
  for poly in boundary(polys):result.append(dict(reference_triangle=owner,xz=poly))
 return result,counts
