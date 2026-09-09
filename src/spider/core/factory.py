import logging
from typing import Optional
from spider.service.service import SpiderService

# Real Providers
from spider.providers.native.dns import NativeDnsAdapter
from spider.providers.native.rdap import NativeRdapAdapter
from spider.providers.native.ct import NativeCertificateTransparencyAdapter
from spider.providers.native.web import NativeWebMetadataAdapter
from spider.providers.native.public_profiles import PublicProfilesAdapter
from spider.providers.native.gravatar import GravatarPublicProfileAdapter
from spider.providers.subfinder.adapter import SubfinderAdapter
from spider.providers.metabigor.adapter import MetabigorAdapter
from spider.providers.spiderfoot.adapter import SpiderFootAdapter
from spider.providers.maigret.adapter import MaigretAdapter
from spider.providers.uncover.adapter import UncoverAdapter
from spider.providers.browser.coccoc import CocCocBrowserAdapter
from spider.providers.whatismyip import WhatIsMyIPAdapter

# Fake Providers (Test Mode Only)
from spider.providers.fake.provider_a import FakeProviderA
from spider.providers.fake.provider_b import FakeProviderB

logger = logging.getLogger(__name__)

def create_spider_service(
    mode: str = "production",
    db_path: Optional[str] = None,
    artifacts_dir: Optional[str] = None
) -> SpiderService:
    """
    Production Composition Root for SPIDER OSINT Platform.
    Enforces that Fake Providers never enter the production pipeline.
    """
    service = SpiderService(db_path=db_path, artifacts_dir=artifacts_dir)

    if mode == "production":
        # Register ONLY verified, real OSINT providers
        service.provider_manager.register_adapter(NativeDnsAdapter())
        service.provider_manager.register_adapter(NativeRdapAdapter())
        service.provider_manager.register_adapter(NativeCertificateTransparencyAdapter())
        service.provider_manager.register_adapter(NativeWebMetadataAdapter())
        service.provider_manager.register_adapter(SubfinderAdapter())
        service.provider_manager.register_adapter(MetabigorAdapter())
        service.provider_manager.register_adapter(SpiderFootAdapter())
        service.provider_manager.register_adapter(MaigretAdapter())
        service.provider_manager.register_adapter(PublicProfilesAdapter())
        service.provider_manager.register_adapter(GravatarPublicProfileAdapter())
        service.provider_manager.register_adapter(UncoverAdapter())
        service.provider_manager.register_adapter(CocCocBrowserAdapter())
        service.provider_manager.register_adapter(WhatIsMyIPAdapter())
        logger.info("SPIDER Service initialized in PRODUCTION mode.")
    elif mode == "test":
        # Test mode allows fake providers
        service.provider_manager.register_adapter(FakeProviderA())
        service.provider_manager.register_adapter(FakeProviderB())
        service.provider_manager.register_adapter(NativeDnsAdapter())
        service.provider_manager.register_adapter(NativeRdapAdapter())
        service.provider_manager.register_adapter(NativeCertificateTransparencyAdapter())
        service.provider_manager.register_adapter(NativeWebMetadataAdapter())
        service.provider_manager.register_adapter(SubfinderAdapter())
        service.provider_manager.register_adapter(MetabigorAdapter())
        service.provider_manager.register_adapter(SpiderFootAdapter())
        service.provider_manager.register_adapter(MaigretAdapter())
        service.provider_manager.register_adapter(UncoverAdapter())
        service.provider_manager.register_adapter(WhatIsMyIPAdapter())
        logger.info("SPIDER Service initialized in TEST mode.")
    else:
        raise ValueError(f"Unknown SPIDER service mode: {mode}. Must be 'production' or 'test'.")

    return service
