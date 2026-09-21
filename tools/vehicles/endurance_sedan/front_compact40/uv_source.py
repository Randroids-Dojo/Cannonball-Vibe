"""Finite source-corner lookup tests the actual interpolated point field.

A distant corner of a source triangle does not define the field at the queried
point. Eligibility therefore checks the complete actual geometric face and the
normal interpolated at its finite closest point, then measures the resulting
new triangle's complete native field separately.
"""
import heapq
import numpy as np
from .bvh import Tree
class OrientedTree(Tree):
 def __init__(self,target):
  super().__init__(np.asarray(target["vertices"])[np.asarray(target["triangles"])])
  raw=np.cross(self.xyz[:,1]-self.xyz[:,0],self.xyz[:,2]-self.xyz[:,0]);self.normal=raw/np.linalg.norm(raw,axis=1)[:,None]
  self.fields=np.asarray(target["normal_corner_targets"],dtype=float)
from .bvh import closest

class LocalTree(OrientedTree):
    def nearest_sheet(self,point,normal):
        point=np.asarray(point,dtype=float);normal=np.asarray(normal,dtype=float);best=float('inf');answer=None;queue=[(0.,0)]
        while queue:
            bound,index=heapq.heappop(queue)
            if bound>best:break
            lo,hi,a,b,ids=self.nodes[index]
            if ids is not None:
                for fi in ids:
                    if float(self.normal[fi]@normal)<.75:continue
                    q,w=closest(point,*self.xyz[fi]);n=np.asarray(w)@self.fields[fi];size=float(np.linalg.norm(n))
                    if size<1e-12 or float(n@normal)/size<.10:continue
                    d=float((point-q)@(point-q))
                    if d<best:best=d;answer=(fi,q,w)
            else:
                for child in(a,b):
                    low,high,*_=self.nodes[child];gap=np.maximum(0.,np.maximum(low-point,point-high));d=float(gap@gap)
                    if d<=best:heapq.heappush(queue,(d,child))
        if answer is None:raise ValueError('No actual compatible finite source point field')
        return best**.5,*answer
