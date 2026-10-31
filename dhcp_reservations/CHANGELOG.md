# Changelog

## 1.15.0 – 2026-10-31
- Renamed to **IP Manager for UniFi** (sidebar panel: *IP Manager*). Nothing else changes: the add-on slug, the stored versions, views and settings, and the event `clients_reservations_new_device` stay the same.

## 1.14.0 – 2026-10-31
Security hardening after a code review (SAST-style).
- **Certificate pinning** for the UniFi controller: new option `certificate_fingerprint` (SHA-256). At start the add-on logs the controller's fingerprint so it can be copied; with a pin, the connection (and the UniFi login) is only accepted if the certificate matches.
- **CSV exports** (table, comparison, version): cells starting with `=`, `+`, `-`, `@`, tab or CR get a leading `'` so spreadsheets do not execute them as formulas (device hostnames are chosen by the devices themselves). The CSV import removes this prefix again.
- **Ping, port check and Wake on LAN** only accept addresses inside the UniFi networks; the port check no longer follows HTTP redirects when it reads the page title.
- POST requests must be `application/json` (CSRF protection in depth).
- New-device notifications escape Markdown in names, vendors and networks.
- Unexpected errors return a generic message (details in the add-on log); responses carry `X-Content-Type-Options`, `Referrer-Policy` and a Content-Security-Policy for the UI.
- At most 32 requests in parallel and at most 2 pings at a time; the device history caches the versions; the files for known devices and vendors are written under a lock.
- Fix: the issues filter could fail right after a refresh while unknown vendors were being filled in.
- **Better error messages**: the banner now shows a hint what to check (controller address, local account / 2FA, certificate, site) and where to change it.
- **Site**: besides the internal name (usually `default`) the site can now be given by its display name (e.g. “Dream Machine Pro”); with only one site on the controller it is used automatically. Previously a name with spaces caused “URL can't contain control characters”.

## 1.13.2 – 2026-10-31
- IP plan: all networks are always listed; the whole dialog scrolls instead of the network table.
- The blue icon top left now hides and shows the filter pane – on phones as a slide-in menu (hamburger), on desktop to gain room for the table (remembered per browser).
- CleanUp Proposal: *Cancel*, *✕*, Esc and *Close* return to the IP plan.

## 1.13.1 – 2026-10-31
- CleanUp Proposal: tabs **Current / Proposal / Changes** to switch quickly between today's layout and the proposal. *Changes* draws an arrow from every old to the new address, marks the future DHCP pool and plays the moves as an animation (*▶ Play moves*).
- The moves are now listed directly below measure 1 (instead of in a separate tab); *Reconnect* is on by default.
- **Show icons** switch in every IP plan view – the device icon in each cell (remembered per browser).
- Button with a broom icon.

## 1.13.0 – 2026-10-31
- **CleanUp Proposal** (IP plan › *CleanUp Proposal* for the selected network): suggests a tidy layout – fixed IPs in a block at the start (e.g. .2 – .99), the DHCP pool behind it (e.g. .100 – .254), sized from the current number of fixed and dynamic clients.
  - *Proposal* tab: the IP plan after the cleanup (moved addresses highlighted, freed addresses dashed) and the measures, each with a checkbox: move fixed IPs, reconnect affected Wi-Fi clients, change the DHCP pool.
  - Strategies: *Minimal* (only fixed IPs in the future pool, on the gateway or used twice move) or *Grouped by vendor* (renumber in blocks of ten per vendor). The end of the fixed range can be adjusted.
  - *Moves* tab: like Replace subnet – checkbox per device, sortable, hint for devices known to Home Assistant (IP-based integrations may need an update).
  - The DHCP pool is changed in UniFi as the last step and only after a second confirmation. A version is saved before anything changes.

## 1.12.1 – 2026-10-31
- **Ping** in the detail panel (section *Network check*, next to the port check): 4 ICMP echos from Home Assistant's network with replies and min / avg / max round-trip time.
- **Vendor lookup**: the detail panel links the MAC to maclookup.app (*Lookup vendor*, only the vendor prefix is sent); random / private MACs are marked as such instead.
- Empty vendors are filled in the background via macvendors.com (option `vendor_lookup`, default on): only the 3-byte prefix is sent, max. 1 request per second, results are cached in the add-on. Such vendors show “(lookup)” in the table.

## 1.12.0 – 2026-10-31
- **Open ports** in the detail panel: *Check ports* tests about 30 common TCP ports (FTP, SSH, Telnet, HTTP/HTTPS and typical web UI ports such as 5000/5001, 8080, 8123, 8443, MQTT, RTSP, SMB, RDP, VNC, printers …) on demand, from Home Assistant's network. Web ports become links (with the page title); the result is stored per device.
- New issues *Telnet open* / *FTP open* and the filter *Issues › Insecure ports*.
- The check runs in small, slowed-down batches and only one device at a time, so UniFi IDS/IPS does not see a port scan burst.

## 1.11.0 – 2026-10-31
- **IP plan** (header): utilization per network (subnet, DHCP pool, fixed IPs in/outside the pool, dynamic leases, free addresses outside the pool, utilization bar) and an address grid per network – fixed IP in use / not in use, dynamic, conflict, gateway, free in pool, free. Click a device to open it, or a free address to reserve it.
- **New-device notifications**: the add-on checks every 2 minutes for MACs it has never seen and creates a Home Assistant notification plus the event `clients_reservations_new_device` (for your own automations). Options `notify_new_devices` (default on), `notify_networks` (names or VLAN IDs, empty = all) and `notify_random_mac` (default off). On the first start all current devices are learned silently.
- **Duplicates**: new issues *Duplicate name* and *Duplicate DNS name*; filter *Issues › Duplicates (IP / name / DNS)*.
- **Export hosts file** (Actions): fixed IPs with their local DNS record and a host name derived from the device name – for `/etc/hosts`, Pi-hole or AdGuard.
- **Network rules** (Actions): e.g. *Vendor contains “Espressif” → IoT*. Devices that match a rule but sit in another network get the issue *Expected in …*; filter *Issues › Wrong network*.
- **Wake on LAN** button in the detail panel for offline wired devices (via Home Assistant's `wake_on_lan` service if set up, plus a magic packet to the subnet broadcast and the device IP).
- New sidebar filter **Inactive**: not seen for more than 30 / 90 / 365 days, or never seen – combine with *Reservation › With fixed IP* to find stale reservations.

## 1.10.0 – 2026-10-31
- **Reconnect** (UniFi *kick-sta*): online Wi-Fi clients whose IP changes can be disconnected briefly so they request the new IP right away.
  - Edit: *Reconnect device after saving* (on by default) when the new fixed IP differs from the device's current IP. Wired devices show that they take the new IP at their next DHCP renewal.
  - Replace subnet and CSV import / restore: *Reconnect N Wi-Fi clients afterwards* in the footer (off by default); the preview shows per row whether the device will be reconnected. Clients are reconnected one per second; the table refreshes after about 20 s.
- Preview tables (CSV import, restore, replace subnet, names from HA, compare) can be **sorted by clicking a column header**; click again to reverse.

## 1.9.8 – 2026-10-31
- Detail panel: the *Edit reservation* button is replaced by **Open `http://<IP>`** (plus *HTTPS*), which opens the device's web interface in a new tab. It uses the current IP when the device is online, otherwise the fixed IP. Editing stays on the *Settings* tab.

## 1.9.7 – 2026-10-31
- **History** in the detail panel: for each device a timeline of what changed and in which version (name, note, fixed IP + network, AP lock, local DNS; IP and network moves in grey), plus the changes made since the latest version.

## 1.9.6
- Bulk dialogs (CSV import, restore, replace subnet, names from HA) now say in the footer that a version of the current settings is saved first, so every bulk change can be undone via *Versions › Restore*.

## 1.9.5
- Baseline filter simplified: one entry *Changed since …* per version (new devices + changed name, note, fixed IP, AP lock or DNS), for the baseline (★) and the latest versions, max. 5. IP or network moves alone do not count.
- Fix: an active baseline filter no longer hides all rows while the versions are still loading.

## 1.9.4
- The *Baseline* filter is always shown: with an explicit baseline it offers *New since …* and *Known at baseline*; otherwise *New since …* for each of the 5 latest versions; without versions a short hint.

## 1.9.3
- *Daily automatic version* moved from the Versions dialog to the add-on configuration (`daily_version`, default on).

## 1.9.2
- Fix: *Compare* reported every fixed IP without a stored network as changed (e.g. "192.168.1.23 → 192.168.1.23 · Management"). The reservation network is now resolved the same way on both sides; this also fixes already saved versions.
- New option *Keep automatic versions (days)* (`auto_version_retention_days`, default 30) in the add-on configuration.

## 1.9.1
- Replace subnet: dropdowns with the known networks above *From subnet* (with number of fixed IPs) and *To subnet*; picking a target network also sets *Target network*. Placeholders now read “e.g. …”.

## 1.9.0
- **Versions**: save the table as a version (manual, optional *Daily automatic version*, and always automatically *Before …* every bulk action: CSV import, replace subnet, names from HA, restore). Automatic versions are kept 30 days, manual / pinned / baseline until deleted. Rename, pin, delete, download as CSV.
- **Compare** a version with the current table or two versions with each other: new devices (with first seen, vendor, network, random-MAC hint and “same hostname as a removed device – probably a new MAC”), removed, changed (name, note, fixed IP, AP lock, DNS), IP changed and moved network. Export the comparison as CSV; *Open* jumps to the device.
- **Restore** a version through the import preview (checkbox per row); choose names, fixed IPs, notes, AP lock, DNS and re-creating forgotten clients. Devices added after the version are left untouched.
- **Baseline**: mark a version as baseline → sidebar filter *New since …* / *Known at baseline*. New column *First seen*.
- Header: *Names from HA*, *Replace subnet*, *Import CSV* and *Export CSV* are grouped under an **Actions** menu; on narrow screens the buttons show icons only.

## 1.8.1
- Fix: read the Home Assistant API token also from the s6 environment store (Names from HA failed with "API not available").

## 1.8.0
- **Inline edit** (toggle in the header): edit Name and Fixed IP directly in the table. Enter / ↑ / ↓ move to the next row, Esc reverts, an empty Fixed IP removes the reservation. The network is taken from the IP.
- **Names from HA**: proposes names from the Home Assistant device registry (matched by MAC), with preview, checkbox per row and “near match” for devices whose Wi-Fi/Ethernet MAC differ in the last byte. The add-on now has access to the Home Assistant API for this.
- Built-in view *DHCP Reservations* now includes *Last seen*.
- *Last seen*: “Never” when the controller has no timestamp; older than 24 h shown as YYYY-MM-DD.

## 1.7.0
- Renamed to **Clients & Reservations**; the count reads "Devices" (UniFi devices are included).
- **Views** (SharePoint-style): built-in *All* and *DHCP Reservations* (MAC, Name, Fixed IP, IP; only clients with a fixed IP). Save changes, save as new view, rename, delete, discard changes, set default. A view stores visible columns, column order, column filters, sidebar filters and sort. Views are stored in the add-on, so they are shared across browsers and devices.
- Dates in YYYY-MM-DD format (table, detail panel with exact last-seen time, CSV export).
- **Replace subnet**: move all fixed IPs from one subnet to another while keeping the host part (e.g. 192.168.30.x → 192.168.31.x), with preview, checkbox per row and checks for missing target network, gateway address, existing reservations and duplicates.

## 1.6.0
- Columns can be reordered by dragging the column header directly (a short click still sorts).

## 1.5.1
- Gateway shows "Internet (WAN)" as connection instead of its WAN port.

## 1.5.0
- UniFi devices (access points, switches, gateway) now show their real status, IP, network and uplink port (read from `stat/device`); they were shown as offline before. New sidebar filter *Type: Clients / UniFi devices*.
- Device pictures from Ubiquiti's fingerprint catalogue (same as the UniFi UI), with the built-in icon as fallback.
- Column order can be changed in *Customize columns* by dragging the grip (or arrow keys on the grip); remembered per browser, *Restore* resets it.

## 1.4.0
- Header bar at the top (deliberate deviation from UniFi): client count, last update, Refresh, Columns, Import CSV, Export CSV, Add reservation.
- Customize columns: show/hide each column (All, Restore, Done), remembered per browser. Also reachable from the sidebar.

## 1.3.0
- Everything in English: UI, messages, configuration, documentation.
- CSV export uses English column names; the import accepts both English and the German names from 1.2.

## 1.2.0
- CSV import with preview (new / change / unchanged / error), checkbox per row incl. select all, template download.
- Export also contains the local DNS record; an exported file can be re-imported unchanged.

## 1.1.0
- Look & feel modelled on UniFi Network: filter sidebar with counts, detail panel (overview/settings), dark/light.
- Connection type column (WiFi / Wired / Teleport), switch port for wired devices, WiFi SSID.
- Locked to access point: show, filter, set/clear; issue when a device is not on its locked AP.
- VLAN override is shown.

## 1.0.0
- First version: sortable/filterable table, edit, new, remove reservation, forget client, CSV export.
