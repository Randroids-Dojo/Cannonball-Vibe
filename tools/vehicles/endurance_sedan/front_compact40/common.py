import math
import numpy as np
from .bvh import Tree
ROLES=("LOD0_FrontBumper","LOD0_FrontFender_L","LOD0_FrontFender_R")
def unit(v):
 v=np.asarray(v,dtype=float);l=float(np.linalg.norm(v))
 if not math.isfinite(l)or l<1e-14:raise ValueError("Invalid target direction")
 return (v/l).tolist()
def receiver_tree(actual,receivers):
    low=np.min(np.concatenate([np.asarray(r['vertices'])for r in actual.values()]),axis=0)-.08
    high=np.max(np.concatenate([np.asarray(r['vertices'])for r in actual.values()]),axis=0)+.08
    xyz=[];labels=[]
    for n,r in sorted(receivers.items()):
        if n in actual or not n.startswith('LOD0_')or r.get('properties',{}).get('source_preview_only',False):continue
        ps=np.asarray(r['vertices'])[np.asarray(r['triangles'],dtype=int)];keep=np.flatnonzero(np.all(ps.max(axis=1)>=low,axis=1)&np.all(ps.min(axis=1)<=high,axis=1));xyz.extend(ps[keep]);labels.extend((n,int(i))for i in keep)
    return Tree(xyz),labels
