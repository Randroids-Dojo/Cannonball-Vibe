"""Small deterministic CPU BVH for finite triangle closest-point queries."""
import heapq
import numpy as np

def closest(p,a,b,c):
    ab=b-a;ac=c-a;ap=p-a;d1=ab@ap;d2=ac@ap
    if d1<=0 and d2<=0:return a,(1.,0.,0.)
    bp=p-b;d3=ab@bp;d4=ac@bp
    if d3>=0 and d4<=d3:return b,(0.,1.,0.)
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:
        v=d1/(d1-d3);return a+v*ab,(1-v,v,0.)
    cp=p-c;d5=ab@cp;d6=ac@cp
    if d6>=0 and d5<=d6:return c,(0.,0.,1.)
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:
        w=d2/(d2-d6);return a+w*ac,(1-w,0.,w)
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:
        w=(d4-d3)/((d4-d3)+(d5-d6));return b+w*(c-b),(0.,1-w,w)
    denominator=va+vb+vc
    if denominator<=0:raise ValueError('Invalid finite triangle')
    v=vb/denominator;w=vc/denominator;return a+ab*v+ac*w,(1-v-w,v,w)

class Tree:
    def __init__(self,xyz,labels=None):
        self.xyz=np.asarray(xyz,dtype=np.float64);self.labels=labels;self.nodes=[]
        lo=self.xyz.min(axis=1);hi=self.xyz.max(axis=1);center=(lo+hi)/2
        def build(ids):
            index=len(self.nodes);self.nodes.append(None);low=lo[ids].min(axis=0);high=hi[ids].max(axis=0)
            if len(ids)<=8:entry=(low,high,None,None,ids.tolist())
            else:
                axis=int(np.argmax(np.ptp(center[ids],axis=0)));order=ids[np.argsort(center[ids,axis],kind='stable')];mid=len(ids)//2
                entry=(low,high,build(order[:mid]),build(order[mid:]),None)
            self.nodes[index]=entry;return index
        build(np.arange(len(self.xyz)))
    def nearest(self,point):
        point=np.asarray(point,dtype=np.float64);best=float('inf');answer=None;queue=[(0.,0)]
        while queue:
            bound,index=heapq.heappop(queue)
            if bound>best:break
            lo,hi,a,b,ids=self.nodes[index]
            if ids is not None:
                for ti in ids:
                    p,w=closest(point,*self.xyz[ti]);d=float((point-p)@(point-p))
                    if d<best:best=d;answer=(ti,p,w)
            else:
                for child in(a,b):
                    low,high,*_=self.nodes[child];gap=np.maximum(0.,np.maximum(low-point,point-high));d=float(gap@gap)
                    if d<=best:heapq.heappush(queue,(d,child))
        return best**.5,*answer
