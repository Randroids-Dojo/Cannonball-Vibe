"""Current input front construction, with no file or Blender IO.

This version extends native870 with complete actual original outer-skin class
inputs. Complete fit, lower budget and final source approval remain separate.
"""
import math,copy,json
from .common import ROLES
from .policy import POLICY
from .guide import extract_legacy_guide
from .geometry import build as reduce_geometry
from .fitted import build as fit_field
from .manufactured import apply as manufactured_fields
from .features import derive as feature_domains
from .formed import apply as formed_fields
RECEIVERS=tuple('LOD0_SplitterMount_'+str(i)for i in range(4))
FIELDS=('vertices','triangles','triangle_materials','materials','triangle_loops','normals','uvs')

def validate_row(row,name):
 if type(row)is not dict or row.get('name',name)!=name:raise ValueError('Wrong native input role')
 for k in FIELDS:
  if k not in row:raise ValueError(('Missing actual native field',name,k))
 v=row['vertices'];ts=row['triangles'];ls=row['triangle_loops'];ns=row['normals'];uv=row['uvs'];mi=row['triangle_materials']
 if not v or not ts or len(ts)!=len(ls)or len(ts)!=len(mi)or set(uv)!={'SurfaceMeters'}:raise ValueError('Incomplete native geometry or chart domain')
 if any(len(p)!=3 or any(type(x)not in(int,float)or not math.isfinite(x)for x in p)for p in v+ns):raise ValueError('Nonfinite native point/direction')
 if any(len(t)!=3 or any(type(i)is not int or i<0 or i>=len(v)for i in t)or len(set(t))!=3 for t in ts):raise ValueError('Invalid actual native triangle')
 if any(len(t)!=3 or any(type(i)is not int or i<0 or i>=len(ns)for i in t)for t in ls):raise ValueError('Invalid actual native loops')
 if any(type(i)is not int or i<0 or i>=len(row['materials'])for i in mi):raise ValueError('Invalid actual material index')
 if any(len(values)!=len(ns)or any(len(u)!=2 or not all(math.isfinite(x)for x in u)for u in values)for values in uv.values()):raise ValueError('Invalid actual UV domain')

def build(actual_rows,contract=None):
 if type(actual_rows)is not dict or set(actual_rows)!=set(ROLES):raise ValueError('Exactly three actual front panels required')
 if type(contract)is not dict or set(contract)!={'schema','receivers','legacy_guide','policy'}or contract['schema']!='front-compact40-input.v1':raise ValueError('Explicit locked shipping input contract required')
 if contract['policy']!=POLICY or set(contract['receivers'])!=set(RECEIVERS):raise ValueError('Current front policy/receiver contract differs')
 for n,r in actual_rows.items():validate_row(r,n)
 for n,r in contract['receivers'].items():validate_row(r,n)
 context=contract['legacy_guide']
 if type(context)is not dict or context.get('schema')!='front-compact40-legacy-guide.v1' or any(set(context[k])!=set(ROLES)for k in('guides','domains','actual_before_panels')):raise ValueError('Incomplete historical guide record')
 for n,r in actual_rows.items():
  if any(r[k]!=context['actual_before_panels'][n][k]for k in FIELDS):raise ValueError(('Guide is not bound to actual completed legacy panel',n))
 if len(context['primitive_domains'])!=len(actual_rows[ROLES[0]]['triangles']):raise ValueError('Incomplete manufactured primitive lineage')
 result=reduce_geometry(actual_rows,contract['receivers'],plane_error=POLICY['local_collapse_plane_residual_m'])
 proof={}
 for n,p in result['parts'].items():
  p['normal_corner_targets'],proof[n]=fit_field(actual_rows[n],p,context['guides'][n],context['domains'][n])
 result['guide_field_proof']=proof
 result['manufactured_field_proof']=manufactured_fields(actual_rows,result['parts'],context['primitive_domains'],proof)
 result['formed_perimeter_field_proof']=formed_fields(actual_rows,result['parts'],context['primitive_domains'],proof)
 result['feature_domains']=feature_domains(result['parts'],proof,result['manufactured_field_proof'])
 result['schema']='front-compact40-output.v1';result['policy']=copy.deepcopy(POLICY)
 result['front_triangles']=sum(len(r['triangles'])for r in result['parts'].values())
 result['acceptance']='Complete original-skin field on exact829 geometry; native/visual and complete physical/lower budget/source approval remain pending'
 return result
