"""Unsaved document pocket with complete local console mounting proof.

Uses the existing production finite-surface helpers; no report/source paths.
"""
import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from endurance_sedan.qa import finish_interfaces as finite


def _bounds(vertices):
    return ([min(v[i] for v in vertices) for i in range(3)],
            [max(v[i] for v in vertices) for i in range(3)])


def _mesh(name,vertices,faces,material,collection,parent):
    data=bpy.data.meshes.new(name+'Mesh');data.from_pydata(vertices,[],faces);data.update()
    bm=bmesh.new();bm.from_mesh(data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(data);bm.free()
    data.materials.append(material)
    layer=data.uv_layers.new(name='SurfaceMeters')
    for polygon in data.polygons:
        axes=[i for i in range(3) if i!=max(range(3),key=lambda i:abs(polygon.normal[i]))]
        for loop in polygon.loop_indices:
            point=data.vertices[data.loops[loop].vertex_index].co
            layer.data[loop].uv=(point[axes[0]]/.25,point[axes[1]]/.25)
    obj=bpy.data.objects.new(name,data);collection.objects.link(obj);obj.parent=parent;obj.matrix_world=Matrix.Identity(4)
    obj['lod_index']=0;obj['uv_meters_per_repeat']=.25
    return obj


def _ring(x0,x1,y0,y1,z):return [(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)]


def local_mount(console_row, y0, y1, z0, mount_top, complete_top):
    """Check every console triangle over the whole holder/binder/band YZ domain.

    For a bounded closed console, every positive-X solid interval terminates
    on its boundary. Bounding every clipped boundary fragment therefore bounds
    all console solid in this prism. No first-chart or global-width shortcut.
    """
    finite.validate_row(console_row['name'], console_row)
    planes=[(np.array([0.,1.,0.]),y0),(np.array([0.,-1.,0.]),-y1),
            (np.array([0.,0.,1.]),z0),(np.array([0.,0.,-1.]),-complete_top)]
    fragments=[]
    for index, tri in enumerate(finite.triangles(console_row)):
        inside,_=finite.partition(list(tri),planes)
        if inside:
            fragments.append({'triangle':index,'vertices_m':[p.tolist() for p in inside]})
    if not fragments:raise ValueError('Missing complete local console boundary')
    cx=max(p[0] for fragment in fragments for p in fragment['vertices_m'])
    if abs(cx-.1395)>1e-6:raise ValueError('Local console mounting plane or outward intrusion changed')
    patch=finite.polygon_mesh([np.array([(cx,y0,z0),(cx,y1,z0),(cx,y1,mount_top),(cx,y0,mount_top)])],
                             'DocumentPocketCompleteMountPatch')
    support=finite.surface_cover(patch,console_row)
    if support['status']!='passed':raise ValueError('Complete console mounting patch unsupported: '+str(support))
    return cx, {'mount_plane_x_m':cx,'footprint_yz_m':[[y0,z0],[y1,mount_top]],
                'whole_assembly_yz_m':[[y0,z0],[y1,complete_top]],
                'complete_console_triangles_checked':len(console_row['triangles']),
                'clipped_boundary_fragments':fragments,'maximum_console_x_in_whole_assembly_prism_m':cx,
                'complete_mount_support':support,'status':'passed_local_mount_and_nonintrusion'}


def build(binder=None,console=None,pocket_material=None,retainer_material=None):
    """Rotate original binder and add a finite stowed pocket/retaining band.

    Returns (three objects, engineering dictionary). Never opens, saves,
    exports or renders a source. Call once on a fresh native source.
    """
    binder=binder or bpy.data.objects['LOD0_CrewLogBinder'];console=console or bpy.data.objects['LOD0_CenterConsole']
    pocket_material=pocket_material or bpy.data.materials['Material_Leather']
    retainer_material=retainer_material or bpy.data.materials['Material_Rubber']
    if any(n in bpy.data.objects for n in ('LOD0_CrewDocumentPocket','LOD0_CrewDocumentRetainer')):
        raise ValueError('Document storage trial already exists')
    bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
    data=bpy.data.meshes.new_from_object(binder.evaluated_get(deps),preserve_all_data_layers=True,depsgraph=deps)
    points=[binder.matrix_world@v.co for v in data.vertices];lo,hi=_bounds(points)
    if any(abs(hi[i]-lo[i]-value)>1e-6 for i,value in enumerate((.25,.32,.029))) or lo[0]<.28 or lo[2]<.50:
        bpy.data.meshes.remove(data);raise ValueError('Expected original horizontal binder envelope')
    cy,cz=(lo[1]+hi[1])*.5,(lo[2]+hi[2])*.5
    moved=[Vector((.1595+point.z-cz,-.10+point.y-cy,.385+hi[0]-point.x)) for point in points]
    ml,mh=_bounds(moved)
    console_eval=console.evaluated_get(deps);cm=console_eval.to_mesh()
    try:
        cm.calc_loop_triangles()
        row={'name':console.name,'vertices':[list(console_eval.matrix_world@v.co) for v in cm.vertices],
             'triangles':[list(t.vertices) for t in cm.loop_triangles],'properties':{}}
        # Cast the intended patch boundaries exactly as native pocket vertices.
        y0,y1,z0,zt,zc=(float(np.float32(v)) for v in (ml[1]-.0036,mh[1]+.0036,ml[2]-.0035,.557,mh[2]+.0024))
        cx,mount=local_mount(row,y0,y1,z0,zt,zc)
    except BaseException:
        bpy.data.meshes.remove(data);raise
    finally:console_eval.to_mesh_clear()
    old_normals=[tuple(n.vector) for n in data.corner_normals]
    for vertex,point in zip(data.vertices,moved):vertex.co=point
    data.update();data.normals_split_custom_set([(n[2],n[1],-n[0]) for n in old_normals])
    binder.modifiers.clear();binder.data=data;binder.matrix_world=Matrix.Identity(4)
    lo,hi=_bounds([v.co for v in data.vertices]);ix0,ix1=lo[0]-.0012,hi[0]+.0012;iy0,iy1=lo[1]-.0012,hi[1]+.0012
    x0,x1,y0,y1,z0,z1=cx,ix1+.0024,iy0-.0024,iy1+.0024,lo[2]-.0035,.557
    vertices=_ring(x0,x1,y0,y1,z0)+_ring(x0,x1,y0,y1,z1)+_ring(ix0,ix1,iy0,iy1,lo[2])+_ring(ix0,ix1,iy0,iy1,z1)
    faces=[(3,2,1,0),(8,9,10,11)]
    for i in range(4):
        j=(i+1)%4;faces.extend([(i,j,j+4,i+4),(i+8,i+12,j+12,j+8),(i+4,j+4,j+12,i+12)])
    collection=binder.users_collection[0];parent=binder.parent
    pocket=_mesh('LOD0_CrewDocumentPocket',vertices,faces,pocket_material,collection,parent)
    plo,phi=_bounds([v.co for v in pocket.data.vertices]);sx0,sx1,t=cx+.0012,phi[0],.0024;zi=hi[2];sz0=phi[2]
    outline=[(sx0,sz0),(sx0,zi+t),(sx1,zi+t),(sx1,sz0),(sx1-t,sz0),(sx1-t,zi),(sx0+t,zi),(sx0+t,sz0)]
    vertices=[(x,y,z) for y in (-.110,-.090) for x,z in outline]
    faces=[tuple(reversed(range(8))),tuple(range(8,16))]+[(i,(i+1)%8,(i+1)%8+8,i+8) for i in range(8)]
    retainer=_mesh('LOD0_CrewDocumentRetainer',vertices,faces,retainer_material,collection,parent)
    binder['storage_pose']='Stowed upright in console-right document pocket under removable retaining band'
    pocket['manufacturing_form']='Open receiving pocket with actual bottom and four closed side walls'
    retainer['manufacturing_form']='Separate U retaining band with two full rim feet and fitted top bearing patch'
    return [binder,pocket,retainer],{'binder_original_dimensions_m':[.25,.32,.029],
                                  'receiving_nominal_side_gap_m':.0012,'bottom_m':lo[2],'pocket_top_m':phi[2],
                                  'binder_top_m':hi[2],'binder_exposed_height_m':hi[2]-phi[2],
                                  'nominal_triangle_delta':56,'local_console_mount':mount,
                                  'scope':'Static stowed storage; no load or accessibility approval'}
