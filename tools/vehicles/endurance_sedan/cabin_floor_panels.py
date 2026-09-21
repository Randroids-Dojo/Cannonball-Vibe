"""Original fitted cabin floor recesses and separately editable mounting pads."""

from . import floor_panels as floor
from . import geometry as geo


def build(body, collection, lod, mats):
    """Apply revision14 after front-floor/pillar operations and before LODs.

    Freeze the valid evaluated input exactly once, preserving its loop triangles
    and corner attributes. Only the two pockets remove body geometry; bounded
    cleanup protects every original vertex and does not refair outer surfaces.
    """
    geo.repair_triangulation(body)
    floor.freeze(body)
    original = [vertex.co.copy() for vertex in body.data.vertices]
    for side in (-1, 1):
        pocket = geo.box('CabinTrayRecess', (side*.446, -.271, .0212),
                         (.389, 1.723, .2424), None, collection, radius=0)
        geo.boolean(body, pocket)
        floor.remove(pocket)
        for index, (x, y) in enumerate(((.628, -.90), (.628, -.20),
                                        (.35, .45), (.56, .45))):
            pad = geo.box(f'LOD0_CabinTrayMount_{side}_{index}',
                          (side*x, y, .14115), (.012, .012, .0025),
                          mats['trim'], collection, lod, radius=0)
            pad['maximum_lod'] = 0
            pad['mounted_component'] = 'LOD0_CabinUndertray_'+str(side)
            pad['mounting_body'] = 'LOD0_StructuralBody'
            pad['assembly_boundary'] = (
                '12mm square finite mounting pad; lower face Z.1399 seats on '
                'tray and upper face Z.1424 seats on the actual recess; '
                'zero solid intrusion beyond the existing1 micrometer encoding guard')
    cleanup = floor.clean_new_slivers(body, original)
    floor.coat_cut_faces(body, mats['paint'])
    geo.repair_triangulation(body)
    body['cabin_tray_pocket_cleanup_vertices'] = len(cleanup)
