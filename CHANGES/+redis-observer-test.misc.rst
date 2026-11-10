Synchronize the post-commit Redis ownership-loss regression with the observation
hook and protect its whole revocation sequence against cancellation, without
relying on a 20 ms I/O deadline or incidental lease expiry under CI load.
