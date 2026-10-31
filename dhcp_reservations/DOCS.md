# Clients & Reservations

Shows every known UniFi client with MAC, name, fixed IP and VLAN in one table, styled like
UniFi Network › Client Devices. Every column can be sorted (click the header) and filtered
(row below the header); the sidebar adds UniFi-style filters with counts.

## Features

- **Edit:** click a row → detail panel → *Settings*: name, note, fixed IP (network/VLAN + IP),
  lock to access point, local DNS record. Changing the network suggests a free IP outside the DHCP pool.
- **New reservation:** also for a MAC the controller has never seen.
- **Remove:** either remove only the reservation (the device stays known) or forget the client entirely.
- **Connection type:** WiFi / Wired / Teleport (Teleport via the controller's v2 API), switch port for wired devices.
- **Locked to AP:** shown, filterable and editable.
- **Issues:** IP outside its network, duplicate IP, device currently has a different IP,
  reservation inside the DHCP pool, random MAC (e.g. iOS "Private Wi-Fi Address"),
  not on the locked AP, VLAN override.
- **Header bar:** View selector, Refresh, Columns, Versions, Inline edit, Actions (Names from HA, Replace subnet, Import CSV, Export CSV) and Add reservation.
- **Versions:** *Versions* in the header. *Save version* stores the table (names, notes, fixed IPs, AP locks, DNS records and,
  for information, current IP, network, first/last seen) in `/data/versions/` – part of Home Assistant backups. A version is
  also saved automatically before every bulk action, and once a day (option `daily_version`, default on). Automatic versions
  are kept for `auto_version_retention_days` (default 30); manual, pinned and baseline versions until deleted.
  - *Compare* shows new devices, removed devices, changed fields, IP changes and network moves against the current table or
    between two versions. New devices with the same hostname as a removed one are flagged as probably the same device with a new MAC.
  - *Restore* runs like a CSV import from the version (preview, checkbox per row, chosen fields) and leaves devices that were
    added later untouched. A version of the current state is saved first.
  - *History* in the detail panel (Overview) shows, per device, a timeline of the changes and the version that first contains them, plus what changed since the latest version.
  - The sidebar filter *Baseline* is always there: *Changed since …* for the baseline (★, set via *Set baseline*) and the
    latest versions (max. 5). It lists devices that are new or whose name, note, fixed IP, AP lock or DNS record changed.
- **Inline edit:** switch it on in the header to edit Name and Fixed IP directly in the table. A change is saved when you leave the field
  (Enter / ↑ / ↓ jump to the next row, Esc reverts). An empty Fixed IP removes the reservation; the network is derived from the IP.
- **Names from HA:** reads the Home Assistant device registry (devices with a MAC connection) and proposes the name you gave the
  device in Home Assistant, otherwise the integration's device name. Devices known only via the UniFi integration are skipped.
  Preview with checkbox per row; “near match” covers devices whose MAC differs only in the last byte (separate Wi-Fi/Ethernet MAC).
- **Views:** like SharePoint views. A view stores the visible columns, their order, column filters, sidebar filters and sort.
  Built-in: *All* and *DHCP Reservations* (MAC, Name, Fixed IP, IP, Last seen – clients with a fixed IP). Use the view menu to
  save changes, save as a new view, rename, delete, discard changes or set the default view. Views are stored in the
  add-on (`/data/views.json`) and shared by every browser.
- **Replace subnet:** moves every fixed IP of a source subnet to the same host address in a target subnet
  (e.g. `192.168.30.0/24` → `192.168.31.0/24`; shorthand `192.168.31` works too). The target network must exist in UniFi.
  The preview flags rows that cannot be moved (no target network, gateway address, IP already reserved, duplicate in the
  source) and lets you pick rows. Devices take the new address at their next DHCP renewal or reconnect.
- **Customize columns:** show, hide and reorder columns (drag a column header in the table, or the grip in the Columns panel); remembered in the browser.
- **UniFi devices:** access points, switches and the gateway are listed with live status, IP and uplink (filter *Type*).
- **Issue “In DHCP pool”:** the fixed IP lies inside the network's DHCP range. UniFi accepts this, but keeping fixed IPs outside the pool avoids conflicts with an address that was already leased before the reservation, and keeps the pool size meaningful.
- **Reconnect:** when a fixed IP changes, online Wi-Fi clients can be reconnected (UniFi *kick-sta*) so they take the new IP right away – a checkbox in the edit panel (on by default) and in Replace subnet / CSV import / restore (off by default, one client per second). Wired and offline devices take the new IP at their next DHCP renewal.
- **Sorting in previews:** click a column header in any preview table to sort; click again to reverse.
- **CSV export** of the current filtered view.
- **CSV import (bulk):** Actions → *Import CSV*. Required column `MAC`; optional `Name`, `Note`,
  `Fixed IP`, `Reservation VLAN` (name or VLAN ID, empty = derived from the IP), `Reserved` (yes/no),
  `Locked to AP` (AP name or "no"), `Local DNS`. Empty cells leave values unchanged. A preview lists
  every change with a checkbox per row (plus *select all*); rows with errors (invalid MAC/IP, duplicate IP,
  IP outside the network, unknown AP) are never applied. An exported file can be re-imported as is.
  German column names from version 1.2 are still accepted.

## Configuration

| Option | Description |
|---|---|
| `unifi_host` | IP of the gateway, e.g. `192.168.1.1` |
| `username` / `password` | Local UniFi account with permission to edit clients |
| `site` | Usually `default` |
| `verify_ssl` | Keep `false` while the gateway uses a self-signed certificate |
| `daily_version` | Save one version of the table per day (default on) |
| `auto_version_retention_days` | Days to keep automatic versions (daily / before bulk actions), default 30 |

Use a dedicated local UniFi account for this add-on rather than sharing one with another
integration, so the sessions don't log each other out.

The UI is only reachable through Home Assistant (Ingress); no port is exposed.
