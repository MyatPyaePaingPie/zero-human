---
type: reference
status: active
created: 2026-08-15
---
# hcom cross-device relay (two Macs, same wifi)

Set up 2026-08-15. Broker runs on this Mac (mosquitto via brew services), password auth,
port 1883, LAN only. hcom payloads are additionally end-to-end encrypted (XChaCha20-Poly1305).

## This Mac (broker + relay owner)
- Broker: `mqtt://10.143.213.12:1883` (LAN IP of en0; changes if DHCP reassigns)
- Broker password: keychain `security find-generic-password -s hcom-relay-broker -w`
- Config: `/opt/homebrew/etc/mosquitto/mosquitto.conf`, users in `hcom.passwd`
- Manage: `brew services restart|stop mosquitto`
- Relay token: `hcom relay token` (treat like an SSH key; never paste into files)

## Other Mac (one-time)
```
brew install aannoo/hcom/hcom          # or: pipx install hcom
hcom relay connect <token> --password <broker password>
hcom relay                             # expect: connected, 2 devices
```

## Every Claude Code terminal, either machine
```
hcom start            # join, get a name (agent can also run this itself)
hcom list             # who is online
hcom send "@name ..." # or plain text broadcast
hcom listen           # block until a message arrives
hcom                  # TUI dashboard
```
Also: `hcom claude --device <name>` launches a Claude session on the other machine.

## Security notes
- Enrolling a device = full trust (a peer can drive/launch/kill agents). Only these two Macs.
- Leak response: `hcom relay off --all`, then `hcom relay new` and re-enroll.
- If the LAN IP changes: `hcom relay new --broker mqtt://<new-ip>:1883 --password ...` and reconnect.
