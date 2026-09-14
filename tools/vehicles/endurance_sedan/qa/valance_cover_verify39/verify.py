"""Current-source numerical orchestration; caller owns all I/O and source locks."""
from . import contracts, fields, opposed, rays, contacts


def verify(actual_rows,actual_fields,requested,companion,*,references,providers):
    rows,base,roles,partition=contracts.validate(actual_rows,actual_fields,requested,companion,references,providers)
    names=contracts.NAMES;receiver=contracts.RECEIVER
    targets=fields.native_targets(actual_fields,requested,providers.field)
    protected_receiver=fields.receiver(actual_fields[receiver],companion['before'][receiver],providers.field)
    outside=fields.protected(actual_fields[names[0]],requested[names[0]],base,companion['finite_field_domains'],providers)
    stock=opposed.stock(actual_fields[names[0]],requested[names[0]],roles,providers)
    visibility=rays.check(actual_fields[names[0]],actual_fields[receiver],providers.geometry)
    finite=contacts.finite(actual_fields,requested,providers)
    resting=contacts.rest(rows,finite['finite_joints'],providers)
    sections={'native_requested_fields':targets,'protected_receiver_fields':protected_receiver,
              'complete_outside_fields':outside,'stock':stock,'pocket_rays':visibility,
              'mounting':finite,'rest':resting}
    return {'schema':'source-valance-cover39.verification.v1',
            'status':'passed' if all(p['status']=='passed' for p in sections.values()) else 'failed',
            'policy':contracts.POLICY,'policy_sha256':contracts.digest(contracts.POLICY),
            'requested_sha256':contracts.digest(requested),'finite_joints':finite['finite_joints'],
            'complete_outer_facet_partition':partition,
            **sections,'source_triangle_delta':1350-324,
            'separate_mandatory':['Global self/normal/containment','Six-opening continuous all-mode pair coverage',
                                  'Tire and wiper motion','Final LOD and whole-source budgets','Independent appearance and human gates'],
            'source_saved':False,'exported':False,'rendered':False,'human_approval_reference':None}
