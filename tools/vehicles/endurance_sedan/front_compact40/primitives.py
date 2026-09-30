"""Explicit original return-plane/cap provenance through real front stages."""
import math,copy
import numpy as np

def unit(v):
 v=np.asarray(v,dtype=float);return v/np.linalg.norm(v)
def primitive(ps,tag=0,strength=0):
 p=np.asarray(ps);n=unit(np.cross(p[1]-p[0],p[2]-p[0]));axis=int(np.argmax(abs(n)))
 if abs(n[axis])>1-1e-9:return {'kind':'original_plane','normal':[float(np.sign(n[axis]))if i==axis else 0. for i in range(3)],'point':ps[0]}
 if tag==1 and strength==16384:return {'kind':'original_formed_cap'}
 return {'kind':'generated_finite_transition'}
def derive(construction):
 c=construction['front_form27']['field_packet']['core'];initial=c['initial'];a=initial['physical']['attributes'];tag=a['cb_fascia_cap'][2];strength=a['__mod_weightednormals_faceweight'][2];domains=[]
 for i,t in enumerate(initial['triangles']):
  d=primitive([initial['physical']['vertices'][v]for v in t['vertices']],tag[t['face']],strength[t['face']]);d['initial_triangle']=i;d['initial_marker']=tag[t['face']];d['initial_strength']=strength[t['face']];d['deformations']=[];domains.append(d)
 for st in c['stages']:
  if st['stage']in('bend','lamp'):
   for d in domains:d['deformations'].append(st['stage'])
  elif st['stage']in('planar','rear_planar'):
   axis=2 if st['stage']=='planar'else 1;removed={i for q in st['proof']['components']for i in q['old_faces']};domains=[d for i,d in enumerate(domains)if i not in removed]
   for q in st['proof']['components']:
    sign=q['normal_z'if axis==2 else'normal_y'];d={'kind':'original_plane','normal':[float(sign)if i==axis else 0. for i in range(3)],'deformations':[],'authored_stage':st['stage']};domains.extend(copy.deepcopy(d)for _ in q['new_triangles'])
  else:
   old=domains;domains=[]
   for e,t in zip(st['proof']['owners'],st['after']['triangles']):
    if e['kind']in('retained_exact','retained_subdivided','subdivided_interpolated')and not e.get('authored_rear_closure_field'):d=copy.deepcopy(old[e['reference_face']])
    else:
     ps=[st['after']['physical']['vertices'][v]for v in t['vertices']];d={'kind':'final_manufactured_plane','normal':unit(np.cross(np.asarray(ps[1])-ps[0],np.asarray(ps[2])-ps[0])).tolist(),'deformations':[],'authored_stage':'inlet','owner_kind':e['kind']}
    domains.append(d)
  if len(domains)!=len(st['after']['triangles']):raise ValueError('Incomplete actual primitive lineage')
 return domains

def smooth(t):
 t=max(0.,min(1.,t));return t*t*t*(10+t*(-15+6*t)),30*t*t*(1-t)*(1-t)if 0<t<1 else 0.
def rising(v,a,b):
 f,d=smooth((v-a)/(b-a));return f,d/(b-a)
def bend(p):
 x,y,z=p
 if y<=2.230:return np.array(p),np.eye(3)
 weight,derivative=rising(y,2.230,2.400);dz=z-.550;old=math.sqrt(3.457**2-dz*dz);new=math.sqrt(.950**2-dz*dz);delta=3.457*-1+old+.950-new;delta_z=dz/new-dz/old;d=1-delta*derivative;e=-delta_z*weight
 fade,xd=rising(abs(x),.580,.730);xgate=1-fade;xd=-xd*(1 if x>=0 else-1);fade,zd=rising(z,.340,.650);upper=1-fade;upper_derivative=-zd;lower,ld=rising(z,.205,.300);zg=upper*lower;zd=upper_derivative*lower+upper*ld;w,wd=rising(y,2.230,2.260);amount=.115
 a=1-amount*(xgate+x*xd)*w*zg;b=-amount*x*xgate*wd*zg;c=-amount*x*xgate*w*zd
 return np.array([x-amount*x*xgate*w*zg,y-delta*weight,z]),np.array([[a,b,c],[0,d,e],[0,0,1.]])
def lamp(p):
 x,y,z=p;s=1 if x>=0 else-1;lx,ld=rising(abs(x),.34,.40);ux,ud=rising(abs(x),.870,.950);gx=lx*(1-ux);dx=s*(ld*(1-ux)-lx*ud);gy,dy=rising(y,2.015,2.055);lz,ld=rising(z,.615,.671);uz,ud=rising(z,.817,.835);gz=lz*(1-uz);dz=ld*(1-uz)-lz*ud;w=gx*gy*gz;gradient=np.array([dx*gy*gz,gx*dy*gz,gx*gy*dz]);amount=-.22*(z-.744)+.08*(abs(x)-.635);da=np.array([.08*s,0,-.22]);d=gradient*amount+da*w;J=np.eye(3);J[2]+=d
 return np.array([x,y,z+w*amount]),J
def map_point(p,stages):
 p=np.asarray(p);J=np.eye(3)
 for stage in stages:
  p,A=(bend if stage=='bend'else lamp)(p);J=A@J
 return p,J

def scalar_inverse(value,fun,lo,hi):
 if not fun(lo)<=value<=fun(hi):raise ValueError(('Source primitive inverse bracket',value,lo,hi,fun(lo),fun(hi)))
 for _ in range(64):
  mid=(lo+hi)/2
  if fun(mid)<value:lo=mid
  else:hi=mid
 return (lo+hi)/2

def target(p,domain):
 stages=domain['deformations'];q=np.asarray(p,dtype=float).copy()
 # Both native construction maps are triangular and strictly monotone in
 # their scalar inverse coordinates. Solve those real coordinates directly;
 # do not depend on an unconstrained multivariate Newton starting point.
 for stage in reversed(stages):
  if stage=='lamp':
   x,y,z=q;q[2]=scalar_inverse(z,lambda v:lamp((x,y,v))[0][2],z-.10,z+.10)
  else:
   x,y,z=q
   yy=scalar_inverse(y,lambda v:bend((x,v,z))[0][1],y-.001,y+.30)
   xx=scalar_inverse(x,lambda v:bend((v,yy,z))[0][0],-2.,2.);q=np.array([xx,yy,z])
 out,J=map_point(q,stages);residual=float(np.linalg.norm(out-p))
 if residual>1e-10:raise ValueError(('Incomplete actual primitive inverse',p.tolist(),q.tolist(),residual))
 if domain['kind']=='original_formed_cap':
  x,y,z=q;width=.825;n=unit([.45*x*abs(x)/width**3,1.,(z-.550)/math.sqrt(3.457**2-(z-.550)**2)])
 else:n=np.asarray(domain['normal'])
 return unit(np.linalg.solve(J.T,n)),q,residual
