"""Scenario layer: product-on-DST wiring, one module per app.

A scenario module exposes ``main(**kwargs) -> coroutine``; the generic
launcher (dst.main) discovers and runs it. Scenario code
patches the app's I/O seams (broker, sockets) to DST systems and runs
the real product code unmodified on the virtual clock.
"""
