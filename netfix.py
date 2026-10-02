# -*- coding: utf-8 -*-
"""인터넷 연결을 IPv4로 먼저 하도록 설정.
사무실 네트워크가 IPv6를 제대로 지원하지 않으면 파이썬은 IPv6 연결을 20초 정도 기다린 뒤에야
IPv4로 넘어갑니다(브라우저는 동시에 시도해서 빠름). 구글·카페24 모두 IPv4로 잘 연결되므로 IPv4만 씁니다."""
import socket

_done = False


def prefer_ipv4():
    global _done
    if _done:
        return
    try:
        import urllib3.util.connection as uc
        uc.allowed_gai_family = lambda: socket.AF_INET
    except Exception:
        pass
    _done = True
