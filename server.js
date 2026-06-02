#!/usr/bin/env node
// Local dev server — uses only Node built-ins, no npm install required.
// Usage: node server.js [port]
//   conda run -n maple-2025 node server.js

const http = require('http');
const fs = require('fs');
const path = require('path');

const portArg = process.argv.slice(2).find(a => a.startsWith('--port='))?.split('=')[1]
  ?? process.argv.find(a => /^\d+$/.test(a));
const PORT = parseInt(portArg || '8080', 10);
const ROOT = __dirname;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
};

const server = http.createServer((req, res) => {
  let urlPath = req.url.split('?')[0];
  if (urlPath === '/') urlPath = '/index.html';

  const filePath = path.join(ROOT, urlPath);

  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not found: ' + urlPath);
      return;
    }
    const ext = path.extname(filePath);
    const ct = MIME[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': ct });
    res.end(data);
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`MA Lobbying Explorer dev server running at http://localhost:${PORT}/`);
  console.log('Press Ctrl+C to stop.');
});
