"""Reusable pieces shared by converters, the filter and the model datasets.

Split by what they touch, so a new converter for a new dataset can pick up the
whole pipeline without copying anything:

``serde``    parquet row <-> :class:`schemas.SFTSample`
``parquet``  locating input shards, streaming rows, streaming writes, readback checks
``render``   chat-template rendering, token counting, loss-mask checks

Nothing here is model-specific: no default model, no default chat template. Those
belong to the caller, because the whole point is that a second model family needs
only a second dataset class.
"""
