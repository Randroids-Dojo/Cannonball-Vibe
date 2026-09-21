"""Native Bfont cap-derived portable static display atlas; explicit new UVs."""
import hashlib,math,struct,zlib
import bpy,bmesh
import numpy as np

LABELS=(('LOD0_NavigationTitle','MERIDIAN',.018,(32,32)),
        ('LOD0_ClimateSetpoint_-0.143','20',.014,(32,300)),
        ('LOD0_ClimateSetpoint_0.143','20',.014,(32,300)),
        ('LOD0_RadioDisplay','CREW  01',.011,(328,300)))
WIDTH=2048;HEIGHT=512;DENSITY=16384;SUPERSAMPLE=4
COLOR=(.5,.65,.75)

def cap(mesh):
    mesh.calc_loop_triangles()
    points=[tuple(v.co) for v in mesh.vertices]
    top=max(p[2] for p in points)
    triangles=[]
    for tri in mesh.loop_triangles:
        ps=[points[i] for i in tri.vertices]
        if all(p[2]==top for p in ps):
            area=(ps[1][0]-ps[0][0])*(ps[2][1]-ps[0][1])-(ps[1][1]-ps[0][1])*(ps[2][0]-ps[0][0])
            if area<=0:raise ValueError('Reversed/degenerate native front cap')
            triangles.append(ps)
    if not triangles:raise ValueError('No actual front-cap triangles')
    return triangles,[(min(p[i] for p in points),max(p[i] for p in points)) for i in range(3)]

def canonical(triangles):
    return sorted(min(tuple(tuple(p) for p in tri[i:]+tri[:i]) for i in range(3)) for tri in triangles)

def independent(text,size):
    curve=bpy.data.curves.new('AtlasIndependentBfont','FONT')
    curve.body=text;curve.size=size;curve.align_x='CENTER';curve.align_y='CENTER'
    curve.extrude=.00012;curve.resolution_u=3
    obj=bpy.data.objects.new('AtlasIndependentBfont',curve)
    bpy.context.scene.collection.objects.link(obj)
    for other in bpy.context.selected_objects:other.select_set(False)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    bpy.ops.object.convert(target='MESH');obj.select_set(False)
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data);bm.free();obj.data.update()
    result=cap(obj.data);mesh=obj.data
    bpy.data.objects.remove(obj,do_unlink=True)
    if mesh.users==0:bpy.data.meshes.remove(mesh)
    return result

def raster(triangles,bounds,origin):
    width=math.ceil((bounds[0][1]-bounds[0][0])*DENSITY)
    height=math.ceil((bounds[1][1]-bounds[1][0])*DENSITY)
    mask=np.zeros((height*SUPERSAMPLE,width*SUPERSAMPLE),dtype=np.bool_)
    for tri in triangles:
        ps=np.asarray([[(p[i]-bounds[i][0])*DENSITY*SUPERSAMPLE for i in (0,1)] for p in tri],dtype=np.float64)
        lo=np.maximum(np.floor(ps.min(axis=0)-.5).astype(int),0)
        hi=np.minimum(np.ceil(ps.max(axis=0)-.5).astype(int)+1,[width*SUPERSAMPLE,height*SUPERSAMPLE])
        if (hi<=lo).any():continue
        x,y=np.meshgrid(np.arange(lo[0],hi[0])+.5,np.arange(lo[1],hi[1])+.5)
        inside=np.ones(x.shape,dtype=np.bool_)
        for a,b in zip(ps,np.roll(ps,-1,axis=0)):
            inside&=((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])>=0)
        mask[lo[1]:hi[1],lo[0]:hi[0]]|=inside
    alpha=np.rint(mask.reshape(height,SUPERSAMPLE,width,SUPERSAMPLE).mean(axis=(1,3))*255).astype(np.uint8)
    if not np.any(alpha):raise ValueError('Empty raster glyph')
    ox,oy=origin
    if ox<32 or oy<32 or ox+width+32>WIDTH or oy+height+32>HEIGHT:raise ValueError('Atlas padding/extent overflow')
    return alpha,{'origin_pixels':list(origin),'size_pixels':[width,height],
                  'nonzero_pixels':int(np.count_nonzero(alpha)),
                  'coverage_area_m2':float(alpha.sum(dtype=np.uint64)/(255*DENSITY**2)),
                  'native_area_m2':sum(((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2 for a,b,c in triangles)}

def png(rgba):
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    rows=b''.join(b'\0'+row.tobytes() for row in rgba[::-1])
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',WIDTH,HEIGHT,8,6,0,0,0))+chunk(b'sRGB',b'\0')+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b'')

def srgb(value):return 12.92*value if value<=.0031308 else 1.055*value**(1/2.4)-.055

def apply(output):
    prepared=[];cells={};rgba=np.zeros((HEIGHT,WIDTH,4),dtype=np.uint8)
    rgba[:,:,:3]=np.rint(np.asarray([srgb(v) for v in COLOR])*255).astype(np.uint8)
    for name,text,size,origin in LABELS:
        obj=bpy.data.objects[name]
        if obj.type!='MESH' or obj.get('maximum_lod')!=0 or obj.get('source_preview_only') or obj.modifiers:raise ValueError('Wrong actual static label domain')
        if [m.name for m in obj.data.materials]!=['Material_CabinLettering']:raise ValueError('Material input drift')
        triangles,bounds=cap(obj.data);reference,refbounds=independent(text,size)
        if canonical(triangles)!=canonical(reference) or bounds!=refbounds:raise ValueError('Native actual cap differs from independently constructed Bfont '+name)
        alpha,metrics=raster(triangles,bounds,origin)
        if origin in cells:
            if not np.array_equal(alpha,cells[origin]):raise ValueError('Shared text cell coverage differs')
        else:
            ox,oy=origin;height,width=alpha.shape
            if np.any(rgba[oy:oy+height,ox:ox+width,3]):raise ValueError('Overlapping atlas cells')
            rgba[oy:oy+height,ox:ox+width,3]=alpha;cells[origin]=alpha
        prepared.append((obj,triangles,bounds,origin,metrics))
    encoded=png(rgba)
    if encoded!=png(rgba.copy()):raise ValueError('Repeated atlas encoding differs')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(encoded)
    image=bpy.data.images.load(str(output.resolve()),check_existing=False)
    image.name='Meridian_StaticLabels_v26';image.colorspace_settings.name='sRGB';image.alpha_mode='STRAIGHT'
    image.pack();image.filepath_raw='//textures/Meridian_StaticLabels_v26.png'
    for item in image.packed_files:item.filepath=image.filepath_raw
    image['provenance']='Actual Blender Bfont cap outlines; literal original project labels; atlas03.py. Bfont copyright 2001-2002 NaN Holding BV, GPL-2.0-or-later; final rights review open.'
    image['texels_per_meter']=DENSITY;image['transparent_cell_padding_pixels']=32
    material=bpy.data.materials['Material_CabinLettering'].copy();material.name='Material_CabinLetteringAtlas'
    shader=material.node_tree.nodes['Principled BSDF']
    tex=material.node_tree.nodes.new('ShaderNodeTexImage');tex.name='Original static Bfont label atlas';tex.image=image
    tex.interpolation='Linear';tex.extension='CLIP'
    links=material.node_tree.links;links.new(tex.outputs['Color'],shader.inputs['Base Color'])
    links.new(tex.outputs['Color'],shader.inputs['Emission Color']);links.new(tex.outputs['Alpha'],shader.inputs['Alpha'])
    material.surface_render_method='DITHERED'
    material['provenance']='Original static project text from Blender bundled Bfont, packed sRGB RGBA atlas, linear alpha coverage'
    material['static_label_atlas']=True;material['cv_shader']='standard'
    proofs=[]
    for obj,triangles,bounds,origin,metrics in prepared:
        xmin,xmax=bounds[0];ymin,ymax=bounds[1];zmin,zmax=bounds[2]
        points=[(x,y,z) for x in (xmin,xmax) for y in (ymin,ymax) for z in (zmin,zmax)]
        faces=[(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)]
        mesh=bpy.data.meshes.new(obj.name+'StaticLabelPatch');mesh.from_pydata(points,[],faces);mesh.update();mesh.materials.append(material)
        layer=mesh.uv_layers.new(name='StaticLabelAtlas')
        for face in mesh.polygons:
            front=all(mesh.vertices[i].co.z==zmax for i in face.vertices)
            for index in face.loop_indices:
                vertex=mesh.vertices[mesh.loops[index].vertex_index].co
                layer.data[index].uv=((origin[0]+(vertex.x-xmin)*DENSITY)/WIDTH,(origin[1]+(vertex.y-ymin)*DENSITY)/HEIGHT) if front else (.5/WIDTH,.5/HEIGHT)
        mesh.update();old=obj.data;obj.data=mesh
        if old.users==0:bpy.data.meshes.remove(old)
        obj['lettering_provenance']='Original label from Blender bundled Bfont; cap-derived static atlas; exact text in static_label_text'
        obj['static_label_text']=next(text for name,text,_,_ in LABELS if name==obj.name)
        obj['uv_texels_per_meter']=DENSITY
        if 'uv_meters_per_repeat' in obj:del obj['uv_meters_per_repeat']
        mesh.calc_loop_triangles()
        assert len(mesh.loop_triangles)==12
        proofs.append({'name':obj.name,'bounds_local_m':bounds,'independent_native_cap_triangles_exact':len(triangles),
                       'triangles_after':12,'new_representation':'closed source-bounds patch, visible front atlas only',**metrics})
    return {'labels':proofs,'atlas_sha256':hashlib.sha256(encoded).hexdigest(),'encoded_bytes':len(encoded),
            'width':WIDTH,'height':HEIGHT,'texels_per_meter':DENSITY,'supersampling_per_axis':SUPERSAMPLE,
            'mip_residency_rgba8_bytes':math.ceil(WIDTH*HEIGHT*4*4/3),'deterministic_png_repeat_exact':True,
            'material':material.name,'color_space':'sRGB','alpha':'straight, linear coverage','bpy_image_packed_bytes':len(image.packed_file.data)}
