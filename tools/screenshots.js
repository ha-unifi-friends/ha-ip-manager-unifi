// README screenshots with a fictional demo network (mocked API): node tools/screenshots.js docs/screenshots-new
const { chromium } = require('playwright');
const fs = require('fs');
const OUT = process.argv[2] || './out';
fs.mkdirSync(OUT, { recursive: true });
const html = fs.readFileSync(require('path').join(__dirname, '..', 'dhcp_reservations_beta/app/static/index.html'), 'utf8').replace(/__ADDON_VERSION__/g, '2.1.0');
const now = Math.floor(Date.now() / 1000), day = 86400;

const nets = [
  { id: 'n1', name: 'Management', vlan: null, subnet: '192.168.1.0/24', gateway: '192.168.1.1', dhcp_start: '192.168.1.100', dhcp_stop: '192.168.1.199', dhcp_enabled: true, purpose: 'corporate', lease_time: 86400 },
  { id: 'n2', name: 'Trusted', vlan: 10, subnet: '192.168.10.0/24', gateway: '192.168.10.1', dhcp_start: '192.168.10.100', dhcp_stop: '192.168.10.199', dhcp_enabled: true, purpose: 'corporate', lease_time: 86400 },
  { id: 'n3', name: 'Services', vlan: 20, subnet: '192.168.20.0/24', gateway: '192.168.20.1', dhcp_start: '192.168.20.100', dhcp_stop: '192.168.20.199', dhcp_enabled: true, purpose: 'corporate', lease_time: 86400 },
  { id: 'n4', name: 'IoT', vlan: 30, subnet: '192.168.30.0/24', gateway: '192.168.30.1', dhcp_start: '192.168.30.100', dhcp_stop: '192.168.30.199', dhcp_enabled: true, purpose: 'corporate', lease_time: 86400 },
  { id: 'n5', name: 'Guest', vlan: 40, subnet: '192.168.40.0/24', gateway: '192.168.40.1', dhcp_start: '192.168.40.10', dhcp_stop: '192.168.40.250', dhcp_enabled: true, purpose: 'guest', lease_time: 86400 },
];
const netOf = ip => nets.find(n => ip.startsWith(n.subnet.split('.').slice(0, 3).join('.') + '.'))?.id || '';
let seq = 0;
const macFor = (pfx, rnd) => { seq++; const h = n => n.toString(16).padStart(2, '0'); return rnd ? `${['86', '5a', 'b6', '82', 'fa', '46'][seq % 6]}:${h(seq * 7 % 256)}:${h(seq * 13 % 256)}:aa:${h(seq)}:0${seq % 10}` : `${pfx}:aa:${h(seq)}:0${seq % 10}`; };
const AP = {}, SW = {};
const devices = [
  ['Gateway', 'UDR', 'gateway', '192.168.1.1', '70:a7:41:10:00:01', null],
  ['USW Rack', 'USL16LPB', 'switch', '192.168.1.2', '6c:63:f8:10:00:02', 'Gateway'],
  ['USW Office', 'US8P60', 'switch', '192.168.1.3', '74:ac:b9:10:00:03', 'USW Rack'],
  ['AP Living', 'U7PROXG', 'ap', '192.168.1.4', '90:41:b2:10:00:04', 'USW Rack'],
  ['AP Office', 'U6PLUS', 'ap', '192.168.1.5', 'e0:63:da:10:00:05', 'USW Office'],
  ['AP Garage', 'U6MESH', 'ap', '192.168.1.6', '18:e8:29:10:00:06', 'USW Rack'],
  ['AP Garden', 'U6MESH', 'ap', '192.168.1.7', '18:e8:29:10:00:07', 'AP Garage'],
];
const clients = [];
for (const [name, model, kind, ip, mac, up] of devices) {
  const u = devices.find(d => d[0] === up), wl = name === 'AP Garden';
  clients.push({ mac, name, hostname: model, device_name: name, device_model: model, device_kind: kind, is_device: true, known: true, online: true, ip, network_id: 'n1', oui: 'Ubiquiti Inc', conn: wl ? 'wifi' : 'wired', wired: !wl, uplink: u ? u[0] : '', sw_mac: u && !wl ? u[4] : '', up_mac: u ? u[4] : '', up_wireless: wl, use_fixedip: false, first_seen: now - 400 * day, last_seen: now });
  if (kind === 'ap') AP[name] = mac; if (kind === 'switch' || kind === 'gateway') SW[name] = mac;
}
let port = { 'USW Rack': 3, 'USW Office': 2, 'Gateway': 2 };
// [name, hostname, ip, fixed (true | other ip | false), conn ('w:<switch>' | 'f:<ap>' | 'teleport'), oui, opts]
const C = (name, host, ip, fixed, conn, oui, o = {}) => {
  const wired = conn.startsWith('w:'), wifi = conn.startsWith('f:'), up = conn.slice(2);
  const c = { mac: o.mac || macFor(o.pfx || 'd4:5d:64', o.rnd), name, hostname: host, ip, network_id: netOf(ip), oui, known: true, online: o.off ? false : true, conn: wired ? 'wired' : wifi ? 'wifi' : 'teleport', wired, uplink: wired || wifi ? up : '', use_fixedip: !!fixed, fixed_ip: fixed === true ? ip : fixed || '', fixed_network_id: fixed ? netOf(fixed === true ? ip : fixed) : '', first_seen: now - (o.age ?? 300) * day, last_seen: o.off ? now - 3 * day : now, note: o.note || '' };
  if (wired) { c.sw_mac = SW[up]; c.port = o.port ?? port[up]++; }
  if (wifi) { c.ap_mac = AP[up]; c.essid = o.ssid || (c.network_id === 'n5' ? 'Guest' : c.network_id === 'n4' ? 'Home-IoT' : 'Home'); c.signal = -55; }
  if (o.vno) { c.vno_enabled = true; c.vno_id = o.vno; }
  clients.push(c); return c;
};
C('NAS', 'nas', '192.168.1.10', true, 'w:USW Rack', 'Synology', { pfx: '00:11:32' });
C('NVR', 'nvr', '192.168.1.11', true, 'w:USW Rack', 'Ubiquiti Inc', { pfx: '60:22:32' });
C('Printer Office 2F', 'BRN3C2AF4', '192.168.1.20', '192.168.1.25', 'f:AP Office', 'Brother', { pfx: 'c8:94:02' });
C('UPS', '', '192.168.1.21', true, 'w:USW Rack', 'APC', { pfx: '00:c0:b7', off: true });
C('Office PC', 'office-pc', '192.168.10.20', true, 'w:USW Office', 'ASUSTek', { pfx: 'd4:5d:64' });
C('Living Room TV', 'Samsung-TV', '192.168.10.30', true, 'f:AP Living', 'Samsung', { pfx: 'a0:d0:5b' });
C('PlayStation', 'PS5', '192.168.10.31', true, 'w:USW Rack', 'Sony', { pfx: 'd4:f7:d5' });
C('MacBook Pro Anna', 'Annas-MacBook-Pro', '192.168.10.120', false, 'f:AP Office', '', { rnd: true });
C('iPhone Anna', 'iPhone', '192.168.10.121', false, 'f:AP Living', '', { rnd: true });
C('iPhone Ben', 'Bens-iPhone', '192.168.10.122', false, 'f:AP Living', '', { rnd: true, age: 3 });
C('iPad Kids', 'iPad-Kids', '192.168.10.123', false, 'f:AP Living', '', { rnd: true });
C('Work Laptop', 'work-mbp', '192.168.10.124', false, 'f:AP Office', 'Apple, Inc.', { pfx: 'f8:4d:89' });
C('Home Assistant', 'homeassistant', '192.168.20.5', true, 'w:USW Rack', 'Raspberry Pi', { pfx: '88:a2:9e' });
C('Pi-hole', 'pihole', '192.168.20.6', true, 'w:USW Rack', 'Raspberry Pi', { pfx: 'dc:a6:32' });
C('Proxmox', 'pve', '192.168.20.7', true, 'w:USW Rack', 'Intel', { pfx: '3c:ec:ef' });
C('Robot Vacuum', 'roborock-vacuum', '192.168.20.44', true, 'f:AP Living', 'Roborock', { pfx: 'b0:4a:39' });
C('Hue Bridge', 'Philips-hue', '192.168.20.62', true, 'w:USW Office', 'Signify', { pfx: 'ec:b5:fa' });
C('Solar Inverter', 'inverter', '192.168.20.64', true, 'f:AP Garage', 'Fox ESS', { pfx: 'd4:27:87' });
C('Wallbox', 'wallbox', '192.168.20.67', true, 'w:USW Rack', 'Easee', { pfx: 'b0:81:84', port: 12 });
C('Sonos Kitchen', 'Sonos-Kitchen', '192.168.20.87', true, 'f:AP Living', 'Sonos', { pfx: '54:2a:1b' });
C('Sonos Living', 'Sonos-Living', '192.168.20.88', true, 'f:AP Living', 'Sonos', { pfx: '54:2a:1b' });
C('AV Receiver', 'Denon-AVR', '192.168.20.95', '192.168.20.12', 'w:USW Rack', 'Denon', { pfx: '00:05:cd' });
C('Doorbell', 'doorbell', '192.168.30.13', true, 'f:AP Garage', 'Ubiquiti Inc', { pfx: '68:d7:9a' });
C('Kitchen Light', 'shellyplus1pm-7c2c67', '192.168.30.50', true, 'f:AP Living', 'Shelly', { pfx: '7c:2c:67' });
C('Hallway Light', 'shelly1pmmini-7c2c68', '192.168.30.51', true, 'f:AP Living', 'Shelly', { pfx: '7c:2c:67' });
C('Bathroom Fan', 'shellyplus1-ac1518', '192.168.30.52', true, 'f:AP Living', 'Shelly', { pfx: 'ac:15:18', off: true });
C('Energy Meter', 'shellypro3em-2cbcbb', '192.168.30.60', true, 'w:USW Rack', 'Shelly', { pfx: '2c:bc:bb' });
C('Thermostat', 'esphome-thermostat', '192.168.30.70', true, 'f:AP Living', 'Espressif', { pfx: '68:c6:3a' });
C('Plant Sensor', 'plant-sensor', '192.168.30.71', true, 'f:AP Garden', 'Espressif', { pfx: 'e4:b0:63' });
C('Garage Door', 'garage-door', '192.168.30.72', true, 'f:AP Garage', 'Espressif', { pfx: 'cc:7b:5c' });
C('Weather Station', 'weather', '192.168.30.73', true, 'f:AP Garden', 'Espressif', { pfx: '58:ce:2a' });
C('Front Camera', 'cam-front', '192.168.30.87', true, 'w:USW Rack', 'Hikvision', { pfx: '20:f4:1b' });
C('Bedroom Switch', 'shelly1mini-d0cf13', '192.168.30.104', false, 'f:AP Living', 'Shelly', { pfx: 'd0:cf:13' });
C('Smart Plug Dryer', 'wlan0', '192.168.30.140', false, 'f:AP Garage', 'Tuya', { pfx: 'a8:80:55', age: 2 });
C('Air Purifier', 'zhimi-airpurifier', '192.168.30.141', false, 'f:AP Living', 'Xiaomi', { pfx: 'b8:e9:37' });
C('ESP Desk Lamp', 'desk-lamp', '192.168.30.142', false, 'f:AP Office', 'Espressif', { pfx: '84:f3:eb' });
C('Galaxy-S24', '', '192.168.40.12', false, 'f:AP Living', '', { rnd: true });
C('iPhone', '', '192.168.40.13', false, 'f:AP Living', '', { rnd: true });
clients.push({ mac: '', key: 'teleport:1', name: "Anna's Laptop (Teleport)", hostname: '', ip: '192.168.2.2', network_id: '', conn: 'teleport', online: true, known: true, oui: '', first_seen: now - 30 * day, last_seen: now });
const byName = n => clients.find(c => c.name === n);
const mac = n => byName(n).mac;

// firewall: zone-based, like UniFi Network 9
const Z = [
  { id: 'zi', name: 'Internal', key: 'internal', network_ids: ['n1', 'n2'] }, { id: 'ze', name: 'External', key: 'external', network_ids: [] },
  { id: 'zg', name: 'Gateway', key: 'gateway', network_ids: [] }, { id: 'zv', name: 'Vpn', key: 'vpn', network_ids: [] },
  { id: 'zh', name: 'Hotspot', key: 'hotspot', network_ids: ['n5'] }, { id: 'zd', name: 'Dmz', key: 'dmz', network_ids: [] },
  { id: 'zs', name: 'Services', key: '', network_ids: ['n3'] }, { id: 'zo', name: 'IoT', key: '', network_ids: ['n4'] },
];
let pi = 0;
const pol = (name, action, sz, dz, extra = {}) => ({ id: 'p' + (++pi), name, action, enabled: true, logging: false, predefined: false, index: 10000 + pi, protocol: 'all', ip_version: 'BOTH', connection_state_type: 'ALL', source: { zone_id: sz, matching_target: 'ANY' }, destination: { zone_id: dz, matching_target: 'ANY' }, hits: Math.floor(Math.random() * 90000), ...extra });
const dev = (zone, names) => ({ zone_id: zone, matching_target: 'CLIENT', client_macs: names.map(mac) });
const FWD = { available: true, fetched_at: now, zones: Z, groups: [], networks: {}, policies: [
  pol('Allow IoT → Home Assistant', 'ALLOW', 'zo', 'zs', { destination: dev('zs', ['Home Assistant']) }),
  pol('Allow IoT DNS → Pi-hole', 'ALLOW', 'zo', 'zs', { destination: { ...dev('zs', ['Pi-hole']), port_matching_type: 'SPECIFIC', port: '53' }, protocol: 'udp' }),
  pol('Block IoT → Services', 'BLOCK', 'zo', 'zs'),
  pol('Block IoT → Internal', 'BLOCK', 'zo', 'zi'),
  pol('Block cameras → Internet', 'BLOCK', 'zo', 'ze', { source: dev('zo', ['Front Camera', 'Doorbell']) }),
  pol('Allow Internal → Services', 'ALLOW', 'zi', 'zs'),
  pol('Allow Internal → IoT', 'ALLOW', 'zi', 'zo'),
  pol('Allow Services → IoT', 'ALLOW', 'zs', 'zo'),
  pol('Block Services → Internal', 'BLOCK', 'zs', 'zi', { destination: { zone_id: 'zi', matching_target: 'NETWORK', network_ids: ['n2'] } }),
  pol('Block Invalid Traffic', 'BLOCK', 'zi', 'ze', { predefined: true, index: 30000, connection_state_type: 'CUSTOM', connection_states: ['INVALID'] }),
  pol('Allow All Traffic', 'ALLOW', 'zi', 'ze', { predefined: true, index: 30010 }),
  pol('Allow All Traffic', 'ALLOW', 'zs', 'ze', { predefined: true, index: 30010 }),
  pol('Allow All Traffic', 'ALLOW', 'zo', 'ze', { predefined: true, index: 30010 }),
  pol('Allow All Traffic', 'ALLOW', 'zh', 'ze', { predefined: true, index: 30010 }),
  pol('Block All Traffic', 'BLOCK', 'zh', 'zi', { predefined: true, index: 30020 }),
  pol('Allow All Traffic', 'ALLOW', 'zi', 'zi', { predefined: true, index: 30010 }),
  pol('Allow All Traffic', 'ALLOW', 'zs', 'zs', { predefined: true, index: 30010 }),
  pol('Allow All Traffic', 'ALLOW', 'zo', 'zo', { predefined: true, index: 30010 }),
  pol('Allow All Traffic', 'ALLOW', 'zh', 'zh', { predefined: true, index: 30010 }),
] };

// traffic between devices for the graph
const edges = [];
const E = (a, b, ab, ba, p, svc) => edges.push({ a: a === 'internet' ? 'internet' : mac(a), b: b === 'internet' ? 'internet' : mac(b), ab, ba, flows: 40, blocked: 0, ports: [{ proto: 'TCP', port: p, service: svc, bytes: ab + ba, flows: 40, blocked: 0 }], domains: b === 'internet' ? ['api.example.com'] : [], ips: [], a_zone: '', b_zone: '', a_net: '', b_net: '' });
for (const n of ['Kitchen Light', 'Hallway Light', 'Energy Meter', 'Thermostat', 'Plant Sensor', 'Garage Door', 'Weather Station', 'Bedroom Switch', 'Air Purifier', 'ESP Desk Lamp', 'Smart Plug Dryer', 'Hue Bridge', 'Solar Inverter', 'Wallbox', 'Sonos Kitchen', 'Sonos Living', 'AV Receiver', 'Robot Vacuum', 'Front Camera', 'Doorbell']) E('Home Assistant', n, 4e5 + (n.length * 7e4), 2e5, 80, 'HTTP');
for (const n of ['Office PC', 'MacBook Pro Anna', 'iPhone Anna', 'iPhone Ben', 'iPad Kids', 'Living Room TV', 'Home Assistant', 'Proxmox']) E(n, 'Pi-hole', 3e4, 6e4, 53, 'DNS');
E('Office PC', 'NAS', 4e9, 2e8, 445, 'SMB'); E('MacBook Pro Anna', 'NAS', 2e9, 1e8, 445, 'SMB'); E('Proxmox', 'NAS', 9e8, 1e8, 2049, 'NFS');
E('Front Camera', 'NVR', 5e9, 1e7, 554, 'RTSP'); E('Doorbell', 'NVR', 2e9, 1e7, 554, 'RTSP');
E('Living Room TV', 'internet', 1e8, 8e9, 443, 'HTTPS'); E('MacBook Pro Anna', 'internet', 1e9, 6e9, 443, 'HTTPS'); E('Sonos Living', 'internet', 3e8, 2e9, 443, 'HTTPS'); E('Home Assistant', 'internet', 2e8, 4e8, 443, 'HTTPS');

// what the browser saw a few days ago: two devices are new since, one fixed IP changed, one device is gone
const warnOf = () => '';
const seen = { t: Date.now() - 3 * day * 1000, fw: null, dev: {} };
for (const c of clients) if (c.mac && !['iPhone Ben', 'Smart Plug Dryer'].includes(c.name)) seen.dev[c.mac] = [c.name, c.use_fixedip ? (c.name === 'Thermostat' ? '192.168.30.69' : c.fixed_ip) : '', warnOf(c)];
seen.dev['11:22:33:aa:99:01'] = ['Old Tablet', '', ''];

const lang = 'en';
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1720, height: 1000 }, deviceScaleFactor: 2, locale: 'en-US', colorScheme: 'dark' });
  const pg = await ctx.newPage();
  pg.on('pageerror', e => console.log('PAGEERROR', e.message));
  await pg.addInitScript(([s]) => { if (!sessionStorage.getItem('init')) { sessionStorage.setItem('init', '1'); localStorage.clear(); localStorage.setItem('dhcpres.lang', '"en"'); localStorage.setItem('dhcpres.topoIcon', '"unifi"'); } }, [0]);
  await pg.route('**/*', r => {
    const u = r.request().url();
    if (u.endsWith('/') || u.includes('index.html')) return r.fulfill({ body: html, contentType: 'text/html' });
    if (u.includes('/i18n/')) return r.fulfill({ json: {} });
    if (u.includes('api/snapshot')) return r.fulfill({ json: { networks: nets, aps: Object.entries(AP).map(([name, mac]) => ({ name, mac })), switches: {}, clients, fetched_at: now } });
    if (u.includes('api/relations')) return r.fulfill({ json: { available: true, from: Date.now() - 864e5, to: Date.now(), flows: 5000, truncated: false, nodes: {}, edges, suspicious: [] } });
    if (u.includes('api/suspicious')) return r.fulfill({ json: { available: true, suspicious: [] } });
    if (u.includes('api/firewall')) return r.fulfill({ json: FWD });
    if (u.includes('api/history/')) return r.fulfill({ json: { versions: [] } });
    if (u.includes('api/versions') && !u.includes('api/versions/')) return r.fulfill({ json: { versions: [], settings: {} } });
    return r.fulfill({ json: {} });
  });
  const W = t => pg.waitForTimeout(t);
  const shot = async name => { await W(300); await pg.screenshot({ path: `${OUT}/${name}.png` }); console.log('shot', name); };
  await pg.goto('http://demo.local/'); await W(2000);
  // the first visit stored what the browser sees – make it look like a visit 3 days ago
  await pg.evaluate(([news, th, t]) => { const s = JSON.parse(localStorage.getItem('dhcpres.seenState')); s.t = t; for (const m of news) delete s.dev[m]; s.dev[th][1] = '192.168.30.69'; s.dev['11:22:33:aa:99:01'] = ['Old Tablet', '', '']; localStorage.setItem('dhcpres.seenState', JSON.stringify(s)); }, [[mac('iPhone Ben'), mac('Smart Plug Dryer')], mac('Thermostat'), Date.now() - 3 * day * 1000]);
  await pg.reload(); await W(2000);

  // 1 List with the change box
  await pg.click('[data-rt="cards"]'); await W(800); await shot('list');
  // 2 Tree
  await pg.click('[data-rt="tree"]'); await W(1000);
  await pg.evaluate(() => document.querySelectorAll('#topoTree details').forEach(d => d.open = true)); await W(300); await shot('tree');
  // 3 Graph
  await pg.click('[data-rt="topo"]'); await W(4500); await shot('graph');
  // 4 Multi-select with firewall matrix (table)
  await pg.click('[data-rt="list"]'); await W(800);
  await pg.click('[data-ms="1"]'); await W(300);
  for (const n of ['Office PC', 'iPad Kids', 'Home Assistant', 'NAS', 'Kitchen Light', 'Front Camera', 'Thermostat']) { await pg.click(`#tbody tr[data-k="${mac(n)}"]`); await W(150); }
  await W(500);
  const cell = await pg.$('#paneSel td.sm-c.sm-part, #paneSel td.sm-c.sm-block'); if (cell) { await cell.click(); await W(400); }
  await shot('multi-select');
  await pg.click('[data-ms="0"]'); await W(500);
  // 5 Firewall test in the device details
  await pg.click(`#tbody tr[data-k="${mac('Kitchen Light')}"]`); await W(800);
  await pg.click('#simPickBtn'); await W(600); await shot('firewall-test-target');
  await pg.click(`#simToBody [data-simto="dev:${mac('Home Assistant')}"]`); await W(200); await pg.click('#simToOk'); await W(300);
  await pg.click('#simGo'); await W(600);
  await pg.$eval('#simDev', e => e.scrollIntoView({ block: 'center' })); await shot('firewall-test');
  // 6 Fixed IP: pick a free address
  await pg.click(`#tbody tr[data-k="${mac('ESP Desk Lamp')}"]`); await W(700);
  await pg.click('#tabEdit'); await W(300);
  await pg.check('#fFixed'); await W(300);
  await pg.click('#btnPickIp'); await W(800); await shot('ip-picker');
  await pg.keyboard.press('Escape'); await W(300);
  // 7 Firewall zone matrix
  await pg.click('#dClose'); await W(300); await pg.click('[data-vw="fw"]'); await W(1500); await shot('firewall');
  await b.close();
})();
