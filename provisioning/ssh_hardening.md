# SSH hardening for a HYDRA-UMC CM5

1. Confirm that a named administrator can connect using an SSH key.
2. Keep a local console available during the first change.
3. Set `PasswordAuthentication no` and `PermitRootLogin no` only after the
   key login has succeeded.
4. Restart SSH and verify a second key-based session before closing the first.

Do not store private keys, Wi-Fi credentials or user passwords in this
repository, configuration fixtures, logs or screenshots.
