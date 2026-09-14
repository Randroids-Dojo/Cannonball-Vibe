"""Continuous bounds on actual wiper rubber against the actual glass skin.

Run with pinned Blender's Python for NumPy; no scene is opened/saved/rendered.
Input geometry and rigid drivers are bound to the same saved-source hash.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

GUARD = 1e-6


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trig_bounds(c, a, b, theta0, theta1):
    """Exact real-arithmetic extrema of c+a*cos(theta)+b*sin(theta)."""
    low, high = sorted((theta0,theta1))
    vl = c+a*math.cos(low)+b*math.sin(low)
    vh = c+a*math.cos(high)+b*math.sin(high)
    mn, mx = np.minimum(vl,vh), np.maximum(vl,vh)
    at_min = np.where(vl <= vh,low,high)
    at_max = np.where(vl >= vh,low,high)
    phase = np.arctan2(b,a)
    radius = np.hypot(a,b)
    theta_max = phase+np.ceil((low-phase)/math.tau)*math.tau
    theta_min = phase+math.pi+np.ceil((low-phase-math.pi)/math.tau)*math.tau
    inside_max = theta_max <= high
    inside_min = theta_min <= high
    return (np.where(inside_min,c-radius,mn), np.where(inside_max,c+radius,mx),
            np.where(inside_min,theta_min,at_min), np.where(inside_max,theta_max,at_max))


class Motion:
    def __init__(self, vertices, contract, parameter='wiper'):
        self.vertices = np.asarray(vertices,dtype=float)
        self.parameter = parameter
        self.pivot = np.asarray(contract['pivot_source_m'],dtype=float)
        self.axis = np.asarray(contract['axis_source'],dtype=float)
        self.axis /= np.linalg.norm(self.axis)
        self.factor = contract['factor_rad']
        rel = self.vertices-self.pivot
        parallel = np.outer(rel@self.axis,self.axis)
        self.constant = self.pivot+parallel
        self.cosine = rel-parallel
        self.sine = np.cross(self.axis,self.cosine)

    def at(self, fraction, indices=None):
        idx = slice(None) if indices is None else indices
        theta = self.factor*fraction
        return self.constant[idx]+self.cosine[idx]*math.cos(theta)+self.sine[idx]*math.sin(theta)

    def bounds(self, axes, interval=(0.,1.), indices=None):
        idx = slice(None) if indices is None else indices
        axes = np.asarray(axes,dtype=float)
        return trig_bounds(self.constant[idx]@axes.T,self.cosine[idx]@axes.T,self.sine[idx]@axes.T,
                           self.factor*interval[0],self.factor*interval[1])


def outer_glass_skin(mesh, approximate_normal):
    vertices = np.asarray(mesh['vertices'],dtype=float)
    triangles = np.asarray(mesh['triangles'],dtype=int)
    projected = vertices@approximate_normal
    # Two actual skins are separated by ~4.5 mm; retain only outer-plane vertices.
    outer = np.flatnonzero(projected >= projected.max()-.001)
    center = vertices[outer].mean(axis=0)
    _,_,basis = np.linalg.svd(vertices[outer]-center,full_matrices=False)
    normal = basis[-1]
    if normal@approximate_normal < 0:
        normal *= -1
    dots = vertices[outer]@normal
    assert dots.max()-dots.min() < 2e-7, 'Actual outer glass is not planar within the declared numeric allowance.'
    front = triangles[np.isin(triangles,outer).all(axis=1)]
    crosses = np.cross(vertices[front[:,1]]-vertices[front[:,0]],vertices[front[:,2]]-vertices[front[:,0]])
    orientations = crosses@normal
    assert np.all(orientations>0) or np.all(orientations<0)
    if np.all(orientations<0):
        front = front[:,::-1]
    edges = {}
    for tri in front:
        for a,b in zip(tri,np.roll(tri,-1)):
            edges.setdefault(tuple(sorted((int(a),int(b)))),[]).append((int(a),int(b)))
    assert all(len(items) in (1,2) for items in edges.values())
    assert len(set(front.flat))-len(edges)+len(front) == 1, 'Outer skin must be one topological disk.'
    boundary = [items[0] for items in edges.values() if len(items)==1]
    links = dict(boundary)
    assert len(links)==len(boundary) and set(links)==set(links.values())
    ordered, current = [],boundary[0][0]
    for _ in boundary:
        ordered.append(current);current=links[current]
    assert current==ordered[0] and len(set(ordered))==len(boundary), 'Boundary must be one cycle.'
    axes, constants = [],[]
    for a,b in boundary:
        axis = np.cross(normal,vertices[b]-vertices[a]);axis /= np.linalg.norm(axis)
        axes.append(axis);constants.append(float(axis@vertices[a]))
    axes,constants = np.asarray(axes),np.asarray(constants)
    convexity = np.min(vertices[outer]@axes.T-constants)
    assert convexity >= -GUARD, 'Boundary is not the expected convex aperture; no convex-hull substitution allowed.'
    return {'normal':normal,'d_min':float(dots.min()),'d_max':float(dots.max()),
            'edge_axes':axes,'edge_constants':constants,'outer_vertices':outer,
            'front_triangles':front,'boundary':boundary,'planarity_span_m':float(dots.max()-dots.min()),
            'minimum_outer_vertex_edge_margin_m':float(convexity)}


def plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(type(value).__name__)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--geometry',type=Path,required=True)
    parser.add_argument('--motion-contract',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args=parser.parse_args(argv)
    assert not args.output.exists()
    source_sha=sha(args.source)
    geometry=json.loads(gzip.decompress(args.geometry.read_bytes()))
    contract=json.loads(args.motion_contract.read_text(encoding='utf8'))
    assert geometry['source_sha256']==contract['source_sha256']==source_sha
    assert contract['status']=='passed' and contract['source_unchanged']
    mesh=geometry['meshes']; motions={row['name']:row for row in contract['wipers']}
    assert set(motions)=={'Wiper_L','Wiper_R'}
    normal=np.asarray(motions['Wiper_L']['axis_source']);normal/=np.linalg.norm(normal)
    glass=outer_glass_skin(mesh['LOD0_Windshield'],normal)
    results=[]
    for name,driver in motions.items():
        row=mesh['LOD0_'+name+'Rubber']; vertices=np.asarray(row['vertices'],dtype=float)
        rest=np.asarray(driver['rest_world_matrix'],dtype=float)
        inverse=np.linalg.inv(rest)
        local=(np.c_[vertices,np.ones(len(vertices))]@inverse.T)[:,:3]
        bottom=np.flatnonzero(local[:,2] <= local[:,2].min()+2e-7)
        assert len(bottom)>=4
        # Every selected point belongs to the actual evaluated lower surface.
        triangles=np.asarray(row['triangles'],dtype=int)
        bottom_triangles=triangles[np.isin(triangles,bottom).all(axis=1)]
        assert len(bottom_triangles)>=2 and set(bottom_triangles.flat)==set(bottom)
        # Connected projected surface guarantees every longitudinal coordinate
        # between its extrema has a contact point, not just two isolated ends.
        reached={int(bottom[0])}
        while True:
            larger=set(reached)
            for tri in bottom_triangles:
                if reached.intersection(map(int,tri)):larger.update(map(int,tri))
            if larger==reached:break
            reached=larger
        assert reached==set(map(int,bottom))
        physical_span=float(np.ptp(local[:,0])); patch_span=float(np.ptp(local[bottom,0]))
        guaranteed_fraction=(patch_span-2*GUARD)/physical_span
        motion=Motion(vertices,driver)
        mn,mx,at_mn,at_mx=motion.bounds([glass['normal']],indices=bottom)
        low_index,high_index=int(np.argmin(mn[:,0])),int(np.argmax(mx[:,0]))
        gap_low=float(mn.min()-glass['d_max']-GUARD)
        gap_high=float(mx.max()-glass['d_min']+GUARD)
        edge_min,_,edge_at,_=motion.bounds(glass['edge_axes'],indices=bottom)
        margin=edge_min-glass['edge_constants']
        i,j=np.unravel_index(np.argmin(margin),margin.shape)
        edge_low=float(margin[i,j]-GUARD)
        passed=gap_low>=0 and gap_high<=.002 and edge_low>0 and guaranteed_fraction>=.90
        hardware=[]
        for child in driver['rigid_descendants']:
            if child not in mesh or child==row['name']:continue
            support=Motion(mesh[child]['vertices'],driver).bounds([glass['normal']])[0].min()
            hardware.append({'name':child,'continuous_separating_plane_gap_m':float(support-glass['d_max']-GUARD),
                             'required_m':.001,'passed':bool(support-glass['d_max']-GUARD>=.001)})
        passed &= all(item['passed'] for item in hardware)
        results.append({'name':name,'status':'passed' if passed else 'failed',
                        'actual_axis_source':motion.axis,'pivot_source_m':motion.pivot,'factor_rad':motion.factor,
                        'continuous_fraction_domain':[0.,1.],'actual_rubber_vertices':len(vertices),
                        'actual_bottom_vertices':bottom.tolist(),'actual_bottom_triangles':bottom_triangles,
                        'actual_bottom_local_z_range_m':[float(local[bottom,2].min()),float(local[bottom,2].max())],
                        'physical_longitudinal_span_m':physical_span,'flat_contact_patch_span_m':patch_span,
                        'guaranteed_blade_length_fraction':guaranteed_fraction,'required_fraction':.90,
                        'guarded_glass_normal_clearance_m':[gap_low,gap_high],
                        'required_glass_normal_clearance_m':[0.,.002],
                        'minimum_guarded_projected_aperture_edge_margin_m':edge_low,
                        'clearance_lower_witness':{'vertex':int(bottom[low_index]),'fraction':float(at_mn[low_index,0]/motion.factor)},
                        'clearance_upper_witness':{'vertex':int(bottom[high_index]),'fraction':float(at_mx[high_index,0]/motion.factor)},
                        'aperture_witness':{'vertex':int(bottom[i]),'boundary_edge':glass['boundary'][j],
                                            'fraction':float(edge_at[i,j]/motion.factor)},
                        'other_hardware_to_glass_plane':hardware})
    result={'task_id':'P1-018','milestone':'M5','utc':datetime.now(timezone.utc).isoformat(),
            'source_sha256':source_sha,'source_unchanged':sha(args.source)==source_sha,
            'inputs':[{'path':str(path.resolve()),'sha256':sha(path)} for path in (args.source,args.geometry,args.motion_contract,Path(__file__))],
            'numpy_version':np.__version__,'numeric_guard_m':GUARD,
            'glass':{k:v for k,v in glass.items() if k not in ('edge_axes','edge_constants')},
            'wipers':results,'status':'passed' if all(r['status']=='passed' for r in results) else 'failed',
            'method':'Rodrigues rigid trajectories reduce every point/plane or aperture half-plane projection to c+a cos(theta)+b sin(theta). Endpoints and all in-domain derivative roots give full continuous extrema. Actual outer triangles form one convex planar disk. Actual flat rubber patch vertices bound every patch triangle by convexity.',
            'limits':['This proves the declared 0–2 mm actual flat-rubber/glass clearance and >=90% physical blade length over the full saved scalar domain. It does not certify cleaning force or dynamic rubber deformation.',
                      'The one-micrometer guard covers retained geometry/plane numerical slack; actual driver binding and native matrix errors remain in the input motion contract.',
                      'Other fixed/moving assembly contacts and runtime update behavior require separate evidence. No final full-vehicle or human approval is implied.'],
            'human_approval_reference':None}
    args.output.write_text(json.dumps(result,indent=2,default=plain)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'status':result['status'],'source_sha256':source_sha,
                      'wipers':[{k:row[k] for k in ('name','status','guaranteed_blade_length_fraction','guarded_glass_normal_clearance_m','minimum_guarded_projected_aperture_edge_margin_m')} for row in results]}))
    raise SystemExit(0 if result['status']=='passed' else 1)


if __name__=='__main__':main()
