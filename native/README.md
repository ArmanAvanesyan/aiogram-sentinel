# aiogram-cmds-native

Optional CPU-only profile resolution, resolved-command validation, batch payloads
and compatible SHA256 fingerprints. ABI 1 is paired with aiogram-cmds 0.3.
The companion has no dependency on the base package and calls neither Python
translators nor Telegram. It never handles async coordination or side effects.

The base distribution remains pure Python and defaults to `engine="python"`.
This native distribution is a release candidate: publication is gated on measured
benefit, parity, supported-platform wheels and explicit release review. Missing
or incompatible companions raise before effects; there is no implicit fallback.
