"""ScreenReceipt: a scam-screening agent on the OpenMinion 0.1 SDK.

Deterministic tools collect the facts, a judge (model via OpenMinion, or a
documented offline rule judge) returns a typed verdict, and every run is
sealed into a hash-chained receipt that anyone can re-verify offline.
"""

__version__ = "0.1.0"
