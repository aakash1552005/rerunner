"""Pluggable HTTP client patchers (requests, aiohttp) coordinated by rerunner.patcher."""

from rerunner.patchers.aiohttp_patcher import install_aiohttp_patch, uninstall_aiohttp_patch
from rerunner.patchers.requests_patcher import install_requests_patch, uninstall_requests_patch

__all__ = [
    "install_aiohttp_patch",
    "install_requests_patch",
    "uninstall_aiohttp_patch",
    "uninstall_requests_patch",
]
