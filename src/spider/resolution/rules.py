from typing import Optional, Tuple
from spider.models.enums import ObservableType, AssertionType

def infer_assertion_type(source_type: ObservableType, target_type: ObservableType) -> Optional[AssertionType]:
    if source_type == ObservableType.DOMAIN and target_type == ObservableType.HOSTNAME:
        return AssertionType.SUBDOMAIN_OF
    elif source_type in (ObservableType.DOMAIN, ObservableType.HOSTNAME) and target_type == ObservableType.IP_ADDRESS:
        return AssertionType.RESOLVES_TO
    elif source_type == ObservableType.IP_ADDRESS and target_type == ObservableType.ASN:
        return AssertionType.BELONGS_TO_ASN
    elif source_type in (ObservableType.IP_ADDRESS, ObservableType.ASN) and target_type == ObservableType.ORGANIZATION:
        return AssertionType.BELONGS_TO_ORG
    elif source_type == ObservableType.IP_ADDRESS and target_type == ObservableType.CIDR:
        return AssertionType.HOSTED_ON
    elif source_type == ObservableType.USERNAME and target_type == ObservableType.ACCOUNT:
        return AssertionType.SHARES_USERNAME
    elif source_type == ObservableType.ACCOUNT and target_type == ObservableType.ACCOUNT:
        return AssertionType.POSSIBLY_SAME_IDENTITY
    elif source_type in (ObservableType.DOMAIN, ObservableType.HOSTNAME) and target_type == ObservableType.CERTIFICATE:
        return AssertionType.USES_CERTIFICATE
    return AssertionType.RELATED_INFRASTRUCTURE
